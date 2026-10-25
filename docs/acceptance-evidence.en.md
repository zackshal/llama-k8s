# Accepted Compose and K3s paths

[Русский](acceptance-evidence.md) · **English**

As of 2026-10-25, source commit `b1d965b85b5217a4a4ca1c6f0889aee8e6b46da7` passed the acceptance described here. These results do not automatically apply to later commits, other models or servers.

The commit moves two conditions from assert parameters to task-level when. Acceptance orchestration belongs to the separate infra-delivery-lab project; OPLA is not part of this deployment.

| Path | Verified |
|---|---|
| Compose | CPU deployment, health 200 and 8 tokens; API closed on guest non-loopback address; repeat apply preserves container identity/start time; inference recovers after reboot |
| K3s | Server/agent Ready, CoreDNS and private API binding; agent-local PV/PVC; real cross-node generation from the allowed namespace; denied namespace blocked on ClusterIP and Pod IP |
| K3s recovery | Repeat apply preserves the container; inference/isolation recover after agent/server reboot; PV/PVC and ClusterIP remain |

Inputs: `ghcr.io/ggml-org/llama.cpp@sha256:20c4196fc08b459a34ef78aaa05b101333b2fac687e30ec99f37b3c9dc071b44`; `stories260K.gguf`, SHA-256 `047bf46455a544931cff6fef14d7910154c56afbc23ab1c5e56a72e69912c04b`; K3s `v1.36.5+k3s1`.

Delivery commit: infra-delivery-lab `3fa84355e944c787689ab507e2d6b6f6aec1c82b`; local Self-Managed pipeline 21 / job 68 / runner 2. This was not a GitLab.com pipeline. The complete sequence ended with both test VMs powered off.

Limits: this tiny-model smoke test does not measure LLM quality; the local PV is agent-bound and there is one server. Production HA, live egress testing, remote VPS deployment and automatic rollback are unverified. Publishing this document does not require repinning the accepted `llama-k8s-reviewed` checkout.
