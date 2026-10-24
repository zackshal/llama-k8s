import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]


def template(path, **variables):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters['to_json'] = json.dumps
    return env.from_string((ROOT/path).read_text()).render(**variables)


class RuntimeTests(unittest.TestCase):
    def test_arguments_remain_literal_and_exec_preserves_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory)/'injected'
            value = f'$(touch {marker}); echo injected'
            probe = 'import json,os,sys; print(json.dumps({"pid":os.getpid(),"args":sys.argv[1:]}))'
            with subprocess.Popen(
                ['bash', str(ROOT/'entrypoint.sh'), '-c', probe, '--prompt', value],
                env={**os.environ, 'LLAMA_SERVER_PATH': str(Path(sys.executable).resolve()),
                     'MCP_ENABLED': '0'},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ) as process:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                result = json.loads(stdout)
                self.assertEqual(result['pid'], process.pid)
                self.assertEqual(result['args'], ['--prompt', value])
            self.assertFalse(marker.exists())

    def test_invalid_numeric_setting_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'test.gguf').write_text('GGUF')
            result = subprocess.run(['bash', str(ROOT/'entrypoint.sh')],
                env={**os.environ, 'LLAMA_SERVER_PATH': '/bin/echo', 'MCP_ENABLED': '0',
                     'MODEL_DIR': str(root), 'MODEL_NAME': 'test.gguf', 'THREADS': '2;id'},
                capture_output=True)
            self.assertNotEqual(result.returncode, 0)


class ManifestTests(unittest.TestCase):
    def variables(self, gpu=False):
        return dict(llama_image='registry.example/llama@sha256:'+'a'*64,
            llama_model_name='test.gguf', llama_models_path='/srv/llama/models',
            llama_gpu=gpu, llama_threads=2, llama_context=2048, llama_memory='4Gi',
            llama_compose_memory='4g', llama_cpus='2', llama_pvc='models-pvc',
            llama_pod_security_version='v1.34', llama_gateway_namespace='llama-gateway')

    def test_compose_cpu_and_gpu_are_private_bounded_and_read_only(self):
        for gpu in (False, True):
            document = yaml.safe_load(template('ansible/roles/llama-deploy/templates/docker-compose.yml.j2', **self.variables(gpu)))
            service = document['services']['llama-server']
            self.assertEqual(service['ports'], ['127.0.0.1:8081:8081'])
            self.assertTrue(service['read_only'])
            self.assertTrue(service['volumes'][0]['read_only'])
            self.assertEqual(service['user'], '10001:10001')
            self.assertEqual('deploy' in service, gpu)
            self.assertIn('mem_limit', service)

    def test_kubernetes_manifest_security_and_complete_resource_set(self):
        base = ROOT/'ansible/roles/llama-deploy/templates'
        resources = yaml.safe_load((base/'kustomization.yaml').read_text())['resources']
        for gpu in (False, True):
            rendered = {}
            for name in resources:
                source = name+'.j2' if name == 'deployment.yaml' else name
                rendered[name] = yaml.safe_load(template(str((base/source).relative_to(ROOT)), **self.variables(gpu)))
            pod = rendered['deployment.yaml']['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertTrue(pod['securityContext']['runAsNonRoot'])
            self.assertEqual('runtimeClassName' in pod, gpu)
            self.assertEqual(rendered['service.yaml']['spec']['type'], 'ClusterIP')
            self.assertEqual(rendered['network-policy.yaml']['spec']['egress'], [])
            self.assertEqual(rendered['namespace.yaml']['metadata']['labels']['pod-security.kubernetes.io/enforce'], 'restricted')
            self.assertEqual(pod['containers'][0]['readinessProbe']['httpGet']['path'], '/health')

    def test_server_and_agent_configs_have_distinct_roles_without_inline_token(self):
        for node in ('fi01', 'ee01'):
            values = dict(inventory_hostname=node, groups={'k3s_server': ['fi01']},
                llama_k3s_node_ip='10.66.0.11', llama_k3s_flannel_iface='wg0',
                llama_k3s_api_bind='10.66.0.11', llama_k3s_cluster_cidr='10.42.0.0/16',
                llama_k3s_service_cidr='10.43.0.0/16', llama_k3s_server_url='https://10.66.0.11:6443')
            config = yaml.safe_load(template('ansible/roles/k3s/templates/config.yaml.j2', **values))
            unit = template('ansible/roles/k3s/templates/k3s.service.j2', **values)
            self.assertNotIn('token', config)
            self.assertEqual(config['token-file'], '/etc/rancher/k3s/join-token')
            self.assertEqual('server' in config, node == 'ee01')
            self.assertIn('ExecStart=/usr/local/bin/k3s '+('server' if node == 'fi01' else 'agent'), unit)
            self.assertNotIn('--disable-agent', unit)
            if node == 'fi01':
                self.assertEqual(config['write-kubeconfig-mode'], '0600')


class AdapterTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('adapter', ROOT/'mcp_adapter.py')
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        key_file = Path(self.temp.name)/'key'; key_file.write_text('a'*40); key_file.chmod(0o600)
        env = patch.dict(os.environ, {'LLAMA_ADAPTER_KEY_FILE': str(key_file), 'LLAMA_URL': 'http://127.0.0.1:8081'})
        env.start(); self.addCleanup(env.stop)
        session = patch.object(self.module.requests, 'Session'); self.session = session.start().return_value
        self.addCleanup(session.stop)
        self.client = self.module.create_app().test_client()
        self.auth = {'Authorization': 'Bearer '+'a'*40}

    def test_missing_auth_denies_completion_before_upstream_request(self):
        self.assertEqual(self.client.post('/complete', json={'prompt': 'hello'}).status_code, 401)
        self.session.post.assert_not_called()

    def test_readiness_reflects_backend_failure(self):
        self.session.get.side_effect = self.module.requests.ConnectionError('private backend details')
        result = self.client.get('/health', headers=self.auth)
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b'private backend', result.data)

    def test_generation_limits_and_oversized_body(self):
        for data in ({'prompt': 'x', 'max_tokens': 99999}, {'prompt': []}, {'prompt': 'x', 'temperature': float('nan')}, {'prompt': 'x', 'max_tokens': True}):
            self.assertEqual(self.client.post('/complete', headers=self.auth, json=data).status_code, 400)
        result = self.client.post('/complete', headers=self.auth, json={'prompt': 'x'*70000})
        self.assertEqual(result.status_code, 413)
        self.session.post.assert_not_called()

    def test_valid_request_has_bounded_timeouts_and_no_redirects(self):
        self.session.post.return_value = Mock(status_code=200, json=lambda: {'content': 'ok'})
        result = self.client.post('/complete', headers=self.auth, json={'prompt': 'hello'})
        self.assertEqual(result.json, {'content': 'ok'})
        self.assertEqual(self.session.post.call_args.kwargs['timeout'], (3, 120))
        self.assertFalse(self.session.post.call_args.kwargs['allow_redirects'])

    def test_errors_hide_upstream_details(self):
        self.session.post.side_effect = self.module.requests.ConnectionError('secret URL and credentials')
        result = self.client.post('/complete', headers=self.auth, json={'prompt': 'hello'})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn(b'secret', result.data)

    def test_unicode_authorization_is_a_denial_not_an_exception(self):
        self.assertEqual(self.client.get('/health', headers={'Authorization': 'Bearer неверно'}).status_code, 401)


if __name__ == '__main__':
    unittest.main()
