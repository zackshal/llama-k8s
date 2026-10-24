# Next project: managed VPS/VPN fleet

[Русский](fleet-roadmap.md) · **English**

This is the next-stage specification, not functionality delivered by this revision.

## Goal

Manage rented Linux VPSs from a physically accessible primary computer. Add/update/revoke nodes idempotently, issue multiple VPN profiles, audit administrative actions, monitor security/availability and retain independent backups. LLM inference is optional; VPN servers do not inherently require GPUs.

## Modules

- Controller: private inventory, verified host keys, secret store, release lock, plan and execution audit.
- Base node: supported OS, operator account, SSH policy, time synchronization, updates, scoped firewall and log rotation.
- Management VPN: private controller-to-node connectivity separate from user traffic.
- User transports: separate AmneziaWG and Xray modules with explicit client/server version compatibility; select sing-box as a supported client/router for a particular transport.
- Observability: OPLA-compatible telemetry, Zabbix provisioning and alerts. The primary PC can administer nodes but should not be the sole always-on monitoring point if it is routinely powered off.
- Applications: Compose or optional K3s; inference is separate. Do not automatically put host VPN services in privileged Kubernetes pods.

Do not assume every WireGuard client supports every AmneziaWG version or sing-box supports every combination. Maintain a tested matrix and use native clients when needed. Xray is an engine; protocol/security combinations are explicit profiles, not interchangeable names.

## Profile contract and lifecycle

Manifest fields include node/site, runtime, management route, transport, pinned release/checksum, secret references, client constraints, DNS/routing/IPv6 policy and monitoring/backup endpoints. Keys and credential-bearing profiles/QRs must not appear in public Git/artifacts/logs.

The proposed controller validates, plans, applies serially, verifies and records results. Rotation, revocation, backup, restore and retirement are separate operations, not existing commands here.

Issue distinct per-client credentials. Reapplying configuration must not regenerate keys without deliberate rotation. Support an overlap/migration period and verify profile delivery. Treat QR/URI/config as credentials.

Audit records operator, node, time, release/manifest hashes, action/result and rotation occurrence without keys or full traffic payload. Browsing history collection is not a default requirement. Define retention/access. Do not promise no logs while maintaining administrative auditing.

## Acceptance

Verify console bootstrap, trusted fingerprints, SSH recovery after management-VPN failure, two independently revocable clients, reboot, DNS/IPv6 leaks, MTU and transport fallback, site outage, upgrade rollback and encrypted backup restore. Open ports and successful handshakes do not establish correct routing, DNS or client data flow.

Select provider, OS, domains, budget and availability goals before real deployment. Host XDP cannot prevent upstream bandwidth saturation; volumetric protection requires upstream support.
