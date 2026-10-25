# llama-k8s

[Русский](README.ru.md) · **English**

Explicit deployment of a private llama.cpp service with Docker Compose or a single-server K3s cluster and optional agents. The operator controls inventory, releases, resources, secrets and management connectivity.

**Status: laboratory-accepted CPU Compose/K3s paths; production deployment remains unverified.** Source commit `b1d965b` passed real inference, repeat deployment, isolation and reboot recovery in a separate delivery lab. GPU inference, a custom image build and end-to-end VPS installation remain unverified. See [acceptance evidence](docs/acceptance-evidence.en.md) for exact commits, inputs and boundaries.

## What changed

- SSH host-key verification is enabled; no automatic trust from ssh-keyscan.
- Deployments no longer run on every push. Validation runs on push/PR; deployment is manual and selects a full reviewed SHA.
- Runtime must be compose or k3s. There is no silent hardware-based choice or kubeadm installation.
- An immutable prebuilt image is required by Ansible. Model file and resource limits are explicit.
- Compose publishes only 127.0.0.1:8081; Kubernetes exposes ClusterIP only.
- Containers use a non-root UID, read-only root filesystem/model mount, dropped capabilities and bounded resources.
- K3s has explicit server/agent roles and a private API bind. Join tokens/configuration/kubeconfig have private permissions.
- Existing unmanaged K3s installations, implicit upgrades and server/agent role changes are rejected.
- Container startup uses exec/argument arrays, not eval. The image no longer starts two unmanaged processes.
- The optional HTTP adapter requires authentication, bounds input and reports actual backend readiness.

## Scope

| Profile | Prerequisites | Result |
|---|---|---|
| Compose | Supported dedicated host, Docker Compose, readable GGUF, reviewed image | Private CPU or preconfigured-GPU inference |
| K3s infrastructure | Private routed interfaces/firewall, pinned binary/checksum, join token | One server plus optional agents; not HA |
| K3s workload | Working K3s, preloaded PVC, reviewed image; GPU plugin if selected | One private inference deployment |

The controller can be your physical computer. Ansible connects through SSH to existing management addresses, including over an existing VPN. Local connection is also possible. This revision does not create provider accounts, rent VPSs, generate VPN profiles or configure DNS/TLS gateways.

Two rented machines are not an HA control plane. For two countries, independent installations are often simpler; selecting a shared cluster needs an explicit failure/storage design.

## Requirements

- Target: Debian 12/13 or Ubuntu 22.04/24.04, amd64, systemd, Python 3, become access and a dedicated host acknowledgment.
- Controller: Python 3.11+, ansible-core 2.19.3, SSH, trusted known_hosts. Use a private virtual environment.
- Docker/Compose must already exist for Compose. The playbook no longer installs Docker/NVIDIA or modifies their global configuration implicitly.
- K3s requires working private management/node networking and appropriately scoped provider/host firewall rules before installation.
- Images must support UID 10001, a read-only root filesystem, a writable /tmp and llama-server-style arguments. Compose health checks require curl inside the selected image.
- Models need sufficient RAM/VRAM and a valid license. A generic VPS has no implied NVIDIA GPU. CPU is the default.

Legacy common/docker/nvidia/kubeadm/build/conversion files remain for historical reference and are not used by the new site.yml. They are not accepted deployment paths. Automatic model conversion and remote compilation are deliberately excluded from this candidate.

## Local development checks

```bash
python3 -m venv .venv
.venv/bin/pip install ansible-core==2.19.3 PyYAML==6.0.2 Jinja2==3.1.6 -r requirements-adapter.txt
.venv/bin/python -m unittest discover -s tests -v
bash -n entrypoint.sh
cd ansible
../.venv/bin/ansible-playbook -i inventory/production/hosts.ini playbooks/site.yml --syntax-check
```

Syntax-check does not contact or configure target nodes. Example inventories use documentation/private placeholder addresses; copy them to private storage and replace them.

## Compose from the controller

Create a private inventory with llama_nodes and private vars based on ansible/examples/vars.yml. Set:

- llama_dedicated_host: true only for the intended dedicated machine;
- llama_runtime: compose;
- llama_image: a reviewed registry image reference including @sha256 and 64 hexadecimal digits;
- llama_model_name: one GGUF filename already present under llama_models_path;
- explicit threads/context/CPU/memory limits; llama_gpu defaults false.

Store keys, real inventories and secrets outside Git. Verify SSH fingerprints through a trusted channel, then:

```bash
cd ansible
ansible -i "$HOME/.config/llama/hosts.yml" llama_nodes -m ansible.builtin.ping
ansible-playbook -i "$HOME/.config/llama/hosts.yml" playbooks/site.yml \
  -e "@$HOME/.config/llama/vars.yml" -K
```

It validates configuration before promoting it, reconciles containers without unconditional restarts, retains the previous Compose file and waits for actual model health. Failure leaves evidence/configuration for diagnosis; there is no claim of automatic application rollback.

For local connection use ansible/examples/local-compose.yml as a private inventory template. Local deployment changes the controller itself; it is not a sandbox.

## Local Compose without Ansible

```bash
export LLAMA_IMAGE='your-registry/llama@sha256:REPLACE_WITH_REVIEWED_DIGEST'
export MODEL_NAME='your-model.gguf'
export MODELS_DIR='/absolute/existing/models'
docker compose config --quiet
docker compose up -d --wait --wait-timeout 300
curl --fail http://127.0.0.1:8081/health
```

Replace the placeholder digest. Direct Compose is a CPU baseline. The Ansible GPU option requires preinstalled, tested NVIDIA runtime support. No adapter is published by default.

## K3s: explicit infrastructure then workload

See [deployment](docs/deployment.en.md). Start with llama_enable_workload=false to create/check cluster infrastructure without requiring a model PVC. Use the two-node inventory only after its private interfaces exist. Set exact K3s release and checksum, private server URL, node addresses and a private token. No latest installer or curl-to-shell execution is used.

One server is supported; additional control-plane servers and HA are intentionally rejected rather than silently misconfigured. New nodes are agents. The controller verifies every intended node's Ready condition.

For workload deployment, preload an existing PVC named by llama_pvc in namespace llama, set the admission version to the selected Kubernetes minor version, then enable the workload. UID/GID 10001 must be able to read model files. Storage provisioning and cross-site replication are not automated. Recreate strategy and one replica are explicit; zero-downtime upgrade is not claimed.

Kubernetes traffic is private ClusterIP. NetworkPolicy allows ingress only from the selected gateway namespace and denies workload egress; it requires a network-policy-enforcing CNI. The playbook does not install a public gateway or TLS/authentication service.

## Optional completion adapter

mcp_adapter.py is an HTTP completion adapter, not an implementation of the MCP protocol. Run it separately under a supervisor/Gunicorn, never Flask's development server.

```bash
umask 077
mkdir -p "$HOME/.config/llama"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$HOME/.config/llama/adapter-key"
export LLAMA_ADAPTER_KEY_FILE="$HOME/.config/llama/adapter-key"
export LLAMA_URL=http://127.0.0.1:8081
.venv/bin/gunicorn --bind 127.0.0.1:8082 --workers 1 --timeout 150 'mcp_adapter:create_app()'
```

/livez is public liveness only; /health and /complete require Authorization: Bearer plus the key. Health reflects upstream readiness. Limits include request size, prompt length, token count and upstream timeout; errors do not disclose backend exception details. Put public access behind TLS/auth/rate limiting. Do not log prompts or bearer headers by default.

## Image builds

Dockerfile builds an explicitly selected 40-character llama.cpp SHA. Supply BASE_IMAGE and RUNTIME_IMAGE (reviewed compatible Ubuntu-based image digests), LLAMA_CPP_VERSION, GGML_CUDA=ON/OFF and BUILD_JOBS. CPU is the default. CUDA requires a compatible devel/runtime pair and driver, tested separately. Heavy Python model-conversion packages are not installed into the inference image.

The release build and runtime-image compatibility were not executed here. Publish the resulting image and use its digest after scanning and smoke testing. A digest identifies bytes; it is not a vulnerability audit or signature.

## CI and deployment

Validate runs unit tests and Ansible syntax checks without deployment credentials. Reviewed deployment is workflow_dispatch only, uses a full release SHA, reruns portable validation and requires production environment secrets:

- SSH_PRIVATE_KEY
- SSH_KNOWN_HOSTS (verified fingerprints, not blindly generated)
- DEPLOY_INVENTORY (private YAML inventory)
- DEPLOY_VARS (private configuration; join secret if installing K3s)

Configure production environment reviewers/allowed branches in GitHub yourself; declaring an environment in YAML does not configure approval policy. Deployment uses normal trusted operator code. Fork PRs must never receive production secrets. Controller-first local Ansible remains the preferred initial path.

## Operations and acceptance

See [deployment](docs/deployment.en.md), [fleet roadmap](docs/fleet-roadmap.en.md), and the OPLA project for security/monitoring integration. Before a real deployment: preserve out-of-band access, back up data, test cold installation, repeat-run behavior, reboot, model readiness, failed rollout and recovery. For K3s also back up the datastore and associated token; do not delete a node's data to resolve an upgrade failure.

OPLA XDP is not attached by this project. Do not replace an existing Cilium/BPF program, copy OPLA firewall rules blindly or claim host filtering prevents upstream bandwidth exhaustion.

## License

[MIT](LICENSE). Existing copyright notices are retained. Model and image licenses are separate.
