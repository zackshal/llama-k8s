# Развёртывание и границы исправлений

**Русский** · [English](deployment.en.md)

Это новый явный путь site.yml. Старые роли автоматической установки Docker/NVIDIA/kubeadm/конвертации не используются. Существующий production cluster не мигрируется этой редакцией автоматически.

## Управляющий компьютер

Сохрани private inventory/vars вне Git, проверь host keys через консоль провайдера, используй SSH agent или --private-key. Не отключай StrictHostKeyChecking. Sudo запрашивается через -K; для CI нужен заранее ограниченный подход к become на выделенных узлах. Не публикуй private vars в issues.

Локальная сеть и VPN должны уже давать маршрут к management addresses. SSH и VPN — разные уровни. Отключать внешний SSH до проверки туннеля, второй сессии и recovery console нельзя.

## Compose

1. На target уже есть рабочий Docker Compose plugin; модель скопирована под /srv/llama/models и читается UID/GID 10001.
2. Image выбран по digest, поддерживает llama-server CLI, curl healthcheck и non-root read-only запуск.
3. Inventory имеет llama_nodes. Приватные vars основаны на ansible/examples/vars.yml; llama_dedicated_host=true разрешает изменения именно этого выделенного хоста.
4. Выполняются ping, syntax-check и site.yml из корня ansible. Playbook не превращает --check в полноценный проверенный deployment plan.
5. Ожидается реальный /health модели. Проверь отдельным ограниченным completion, затем повторный playbook: работающий контейнер не должен без причины рестартовать.

API доступен только через loopback. Для доступа с controller можно использовать проверенный SSH tunnel:

```bash
ssh -N -L 18081:127.0.0.1:8081 operator@your-management-host
```

Затем http://127.0.0.1:18081/health. Публичный доступ требует отдельного TLS gateway/auth/limits, который эта редакция не создаёт.

## K3s infrastructure

Поддерживается один server и 0+ agents, не HA. Inventory ansible/examples/two-nodes.yml показывает группы/host vars; адреса и wg0 заменяются реально существующими. Укажи llama_runtime=k3s, llama_manage_k3s=true, llama_enable_workload=false.

До запуска:

- точная проверенная llama_k3s_version, не latest;
- llama_k3s_sha256 для amd64 binary из соответствующего релиза, полученный и проверенный доверенным способом;
- приватные node IP, server API bind, server URL https://PRIVATE_IP:6443 и flannel interface;
- приватный llama_k3s_token в Vault/private vars, без вывода в shell arguments;
- llama_network_prepared=true только после проверки management reachability/firewall и отсутствия конфликтов CIDR;
- между узлами разрешены требуемые выбранной конфигурацией K3s соединения. Для Flannel VXLAN UDP/8472 не публикуется в Интернет; API/служебные соединения ограничены management/cluster peers. Сверь текущую официальную таблицу портов, не открывай всё по шаблону;
- одна и та же версия/cluster configuration/token для группы узлов; секрет первоначального подключения и CA bootstrap доверяются только через проверенный management transport.

Playbook отказывается принимать чужой K3s, автоматически менять версию или server/agent role. Создаётся service llama-k3s, а не vendor k3s. Ключевой конфиг /etc/rancher/k3s/config.yaml и join-token имеют 0600; administrative kubeconfig 0600. TLS SAN включает private bind address, local kubectl направляется на него. Проверяется API readiness и Ready каждого ожидаемого узла.

K3s устанавливает собственный containerd/CNI и меняет сетевое поведение хоста. Его надо испытывать на выделенной машине с out-of-band console. Поставщик VPS должен поддерживать нужные kernel/cgroup/container возможности. Этот patch не подтверждает такую совместимость.

## K3s workload

Namespace llama создаётся при попытке deployment, затем требуется существующий PVC. Поэтому выполняй инфраструктуру отдельно, создай namespace/PVC, заполни модель и только потом включай workload. Admission policy version задаётся явно, например v1.X по выбранному Kubernetes minor. Для заранее созданного namespace должны сохраняться совместимые Restricted labels.

PVC выбирается llama_pvc. Нужны доступ UID/GID 10001 и storage, подходящий выбранному node scheduling. Локальный volume не является репликацией. Одна replica/Recreate допускает downtime при замене. GPU-профиль требует установленного device plugin и RuntimeClass nvidia; эти компоненты не ставятся неявно.

Image и модель проверяются отдельно. Readiness — upstream /health; liveness использует TCP, чтобы длительная загрузка модели не вызывала немедленный restart. NetworkPolicy допускает вход из llama_gateway_namespace, egress закрыт. Не создавай workload в privileged namespace для обхода policy.

## Обновление и восстановление

Для image upgrade сохрани прежний digest и Compose/manifests; deploy по одной площадке с проверкой реального inference. При отказе верни прежний reviewed digest и повтори explicit deployment. Автоматический rollback/транзакционность не реализованы.

Upgrade K3s этой редакцией блокируется: сначала нужны datastore/token backup, совместимость версий и отдельный tested upgrade playbook. Удаление кластера/PVC/моделей не автоматизировано. uninstall должен иметь отдельный план хранения/удаления данных; не используй rm -rf cluster data как диагностику.

Для полноценной приёмки нужны cold install, repeat run, reboot, недоступный registry, ошибочный image/model, потеря VPN/узла, завершение контейнера и восстановление. В текущей среде проверены переносимые tests и syntax, не эти живые сценарии.
