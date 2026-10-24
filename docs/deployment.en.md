# Deployment and hardening boundaries

[Русский](deployment.md) · **English**

This is the new explicit site.yml path. Legacy Docker/NVIDIA/kubeadm/conversion roles are not used. Existing production clusters are not automatically migrated.

## Physical controller

Keep inventory/vars outside Git. Verify fingerprints through provider consoles, use an SSH agent or --private-key, and retain host-key checking. -K requests sudo interactively; CI needs a prearranged become policy on dedicated targets. Never post private vars in issues.

VPN routing must already exist. SSH and VPN are separate layers. Do not restrict public SSH before verifying the tunnel, a second session and recovery console.

## Compose

1. Target already has Docker Compose; the GGUF is readable by UID/GID 10001 under the selected existing model directory.
2. The digest-pinned image supports llama-server arguments, curl health checks and non-root read-only operation.
3. Private inventory defines llama_nodes and vars follow ansible/examples/vars.yml. Enable the dedicated-host acknowledgment only for the intended host.
4. Run ping, syntax-check and site.yml from ansible. --check is not a fully validated deployment planner.
5. Wait for actual model /health, test a bounded completion and repeat the playbook without unnecessary container restarts.

Only loopback is published. For controller access:

```bash
ssh -N -L 18081:127.0.0.1:8081 operator@your-management-host
```

Then probe http://127.0.0.1:18081/health. A public TLS/auth/rate-limiting gateway is a separate component not installed here.

## K3s infrastructure

One server and optional agents are supported, not HA. Adapt ansible/examples/two-nodes.yml to real private IPs/interfaces. Set runtime=k3s, manage_k3s=true and enable_workload=false using the full llama_ variable names.

Before applying, provide:

- exact reviewed llama_k3s_version and the matching amd64 binary SHA-256 obtained through a trusted release-verification process;
- private node IPs, private API bind, https://PRIVATE_IP:6443 server URL and a real flannel interface;
- private join token in Vault/private vars, never shell arguments;
- llama_network_prepared=true only after route/firewall/CIDR review;
- scoped K3s peer connectivity. With Flannel VXLAN, UDP/8472 must not be exposed to the Internet. Restrict API/cluster ports to intended peers and review the current official port matrix;
- consistent cluster version/configuration/token across nodes. Initial secret/CA bootstrap relies on a verified management transport.

The role rejects foreign K3s adoption, version changes and role changes. It creates llama-k3s.service, not the vendor k3s service. Config/join token and administrative kubeconfig are private. TLS SAN includes the private bind address; local kubectl uses it. API readiness and every expected node's Ready condition are checked.

K3s installs containerd/CNI and changes host networking. Use a dedicated host and recovery console; verify provider kernel/cgroup/container support. This patch does not prove compatibility with an arbitrary VPS.

## K3s workload

Deployment creates namespace llama before checking the required PVC. Bootstrap infrastructure separately, create namespace/PVC, preload the model, then enable the workload. Set an explicit admission policy minor version matching your Kubernetes release. Existing namespaces must retain compatible Restricted labels.

llama_pvc selects existing storage. UID/GID 10001 must read the model; storage must match scheduling. Local volume is not replicated storage. One replica/Recreate means downtime during replacement. GPU requires a preinstalled device plugin and nvidia RuntimeClass, not implicit host driver changes.

Readiness probes actual model /health; TCP liveness avoids immediate restart during loading. NetworkPolicy allows ingress from the selected gateway namespace and denies egress. Do not bypass policy by using a privileged application namespace.

## Upgrade and recovery

Retain the previous image digest and configuration. Upgrade one site at a time with bounded real inference checks. On failure explicitly redeploy the previous reviewed digest. Automatic rollback and transactional application deployment are not implemented.

K3s upgrades are rejected pending a separate backup/compatibility/upgrade procedure. Preserve datastore and its token. No destructive uninstall/PVC/model cleanup is automated; do not delete cluster data to diagnose failures.

Acceptance still requires cold install, repeat run, reboot, unavailable registry, invalid model/image, VPN/node outage, process termination and restore. This environment exercised portable tests and syntax only.
