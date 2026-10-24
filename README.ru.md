# llama-k8s

**Русский** · [English](README.md)

Явное развёртывание приватного llama.cpp через Docker Compose либо K3s с одним server и дополнительными agents. Оператор задаёт inventory, версии, ресурсы, секреты и management network.

**Статус: кандидат исправлений, не подтверждённая production-установка.** Есть переносимые тесты запуска, adapter и шаблонов, Ansible syntax-check. Живой K3s/GPU inference, сборка image, reboot и установка на VPS для этой редакции не выполнялись.

## Что исправлено

- Включена проверка SSH host key; ssh-keyscan не используется как источник доверия.
- Push больше не развёртывает серверы: CI выполняет проверки, deployment запускается вручную по полному reviewed SHA.
- Runtime задаётся явно: compose или k3s, без скрытого выбора и kubeadm.
- Ansible требует заранее выбранный image по digest, один GGUF и явные ограничения ресурсов.
- Compose публикует только 127.0.0.1:8081, Kubernetes — только ClusterIP.
- Контейнеры работают non-root, с read-only filesystem/models, без capabilities и с лимитами.
- В K3s разделены server/agent; API привязан к приватному адресу, token/config/kubeconfig закрыты правами.
- Чужой K3s не принимается под управление, неявный upgrade и смена роли server/agent запрещены.
- В entrypoint нет eval; команда выполняется через массив аргументов и exec, без двух неуправляемых процессов.
- HTTP adapter требует ключ, ограничивает запросы и проверяет реальную готовность backend.

## Профили

| Профиль | Подготовить заранее | Результат |
|---|---|---|
| Compose | Выделенный Linux, Docker Compose, читаемый GGUF, reviewed image | Приватный CPU inference или подготовленный GPU |
| K3s infrastructure | Приватная сеть/firewall, версия и checksum бинарника, token | Один server и agents; не HA |
| K3s workload | Работающий K3s, заполненный PVC, image; GPU plugin при необходимости | Одна приватная inference deployment |

Управляющий хост — твой физический компьютер. Ansible подключается по SSH к имеющимся management addresses, в том числе через уже работающую VPN. Есть local connection. Эта редакция не арендует VPS, не выпускает VPN-профили, не создаёт DNS и внешний TLS gateway.

Две машины не дают HA control plane. Для разных стран можно выбрать независимые установки; общий кластер требует отдельной схемы отказов и хранения.

## Требования

- Target: Debian 12/13 либо Ubuntu 22.04/24.04, amd64, systemd, Python 3, become и явное подтверждение выделенного хоста.
- Controller: Python 3.11+, ansible-core 2.19.3, SSH и проверенный known_hosts; отдельный venv.
- Для Compose Docker/Compose уже установлены. Автоматического изменения глобальных Docker/NVIDIA configs нет.
- Для K3s уже работают приватные интерфейсы и маршруты, firewall провайдера и хоста настроен под выбранную сеть.
- Image поддерживает UID 10001, read-only root, writable /tmp и llama-server arguments. В image нужен curl для Compose healthcheck.
- GGUF должен помещаться в RAM/VRAM и иметь подходящую лицензию. VPS не подразумевает NVIDIA GPU. По умолчанию CPU.

Старые common/docker/nvidia/kubeadm/build/conversion файлы сохранены как исторические материалы, но новый site.yml их не вызывает. Это не принятые сценарии deployment. Автоконвертация и компиляция на арендованном сервере намеренно исключены из основного пути.

## Локальные проверки

```bash
python3 -m venv .venv
.venv/bin/pip install ansible-core==2.19.3 PyYAML==6.0.2 Jinja2==3.1.6 -r requirements-adapter.txt
.venv/bin/python -m unittest discover -s tests -v
bash -n entrypoint.sh
cd ansible
../.venv/bin/ansible-playbook -i inventory/production/hosts.ini playbooks/site.yml --syntax-check
```

Syntax-check не меняет удалённые узлы. Адреса examples — placeholders: копируйте inventory в private storage и заменяйте значения.

## Compose с управляющего компьютера

Создай private inventory с группой llama_nodes и vars на основе ansible/examples/vars.yml. Задай:

- llama_dedicated_host: true только для выбранной выделенной машины;
- llama_runtime: compose;
- llama_image с @sha256 и 64 hex-символами;
- llama_model_name — один существующий GGUF под llama_models_path;
- явные threads/context/CPU/memory; llama_gpu по умолчанию false.

Ключи, рабочие inventory и секреты остаются вне Git. Проверь SSH fingerprint доверенным способом:

```bash
cd ansible
ansible -i "$HOME/.config/llama/hosts.yml" llama_nodes -m ansible.builtin.ping
ansible-playbook -i "$HOME/.config/llama/hosts.yml" playbooks/site.yml \
  -e "@$HOME/.config/llama/vars.yml" -K
```

Сначала проверяется candidate config, затем сохраняется предыдущий Compose file, выполняется reconciliation без безусловных рестартов и ожидается model health. При ошибке остаются данные для диагностики; автоматический rollback приложения не заявлен.

Для local connection используй ansible/examples/local-compose.yml как шаблон. Это меняет сам controller, а не изолированную ВМ.

## Compose без Ansible

```bash
export LLAMA_IMAGE='your-registry/llama@sha256:REPLACE_WITH_REVIEWED_DIGEST'
export MODEL_NAME='your-model.gguf'
export MODELS_DIR='/absolute/existing/models'
docker compose config --quiet
docker compose up -d --wait --wait-timeout 300
curl --fail http://127.0.0.1:8081/health
```

Замени digest. Это CPU baseline; GPU через Ansible требует заранее проверенного NVIDIA runtime. Adapter по умолчанию не опубликован.

## K3s: сначала инфраструктура, затем workload

См. [развёртывание](docs/deployment.md). Сначала llama_enable_workload=false: кластер можно подготовить без model PVC. Two-node inventory используется только после настройки приватных интерфейсов. Версия K3s и checksum задаются явно, как private server URL, node addresses и token. Mutable installer/curl-to-shell не используется.

Поддерживается один server. Дополнительные control-plane узлы/HA отклоняются вместо скрытой неверной настройки. Новые узлы — agents, проверяется Ready каждого ожидаемого узла.

Для workload заранее создай/заполни PVC в namespace llama, задай admission version по Kubernetes minor и включи workload. UID/GID 10001 должен читать модели. Storage provisioning и cross-site replication не автоматизированы. Одна replica и Recreate strategy означают, что zero-downtime upgrade не заявлен.

Service — ClusterIP. NetworkPolicy разрешает вход только из указанного gateway namespace и запрещает egress; нужен CNI с поддержкой policy enforcement. Публичный gateway/TLS/auth этим playbook не устанавливается.

## Опциональный HTTP adapter

mcp_adapter.py — HTTP completion adapter, не полноценный MCP server. Запускается отдельно через supervisor/Gunicorn, без Flask development server:

```bash
umask 077
mkdir -p "$HOME/.config/llama"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "$HOME/.config/llama/adapter-key"
export LLAMA_ADAPTER_KEY_FILE="$HOME/.config/llama/adapter-key"
export LLAMA_URL=http://127.0.0.1:8081
.venv/bin/gunicorn --bind 127.0.0.1:8082 --workers 1 --timeout 150 'mcp_adapter:create_app()'
```

/livez — только liveness; /health и /complete требуют Authorization: Bearer с ключом. Health проверяет upstream. Ограничены request size, prompt, tokens и timeout; исключения backend не выдаются клиенту. Для внешнего доступа нужен TLS/auth/rate limiting. Prompts и bearer headers по умолчанию не логируются.

## Сборка образа

Dockerfile требует 40-символьный SHA llama.cpp. Задаются BASE_IMAGE и RUNTIME_IMAGE (reviewed совместимые Ubuntu-based digests), LLAMA_CPP_VERSION, GGML_CUDA=ON/OFF и BUILD_JOBS. CPU — default. CUDA требует совместимых devel/runtime и driver, проверяемых отдельно. Тяжёлые Python-пакеты конвертации не входят в inference image.

Сборка релиза и совместимость runtime image здесь не проверены. После сборки нужны scan и smoke test, затем публикация image по digest. Digest фиксирует содержимое, но не заменяет аудит или подпись.

## CI и deployment

Validate запускает unit/template tests и syntax-check без production secrets. Reviewed deployment — только workflow_dispatch, полный SHA и повторные переносимые проверки. Secrets окружения production:

- SSH_PRIVATE_KEY;
- SSH_KNOWN_HOSTS — проверенные fingerprints;
- DEPLOY_INVENTORY — private YAML;
- DEPLOY_VARS — private vars, включая join secret при установке K3s.

Reviewers и allowed branches production environment нужно настроить в GitHub: одна строка environment в YAML их не создаёт. Fork PR не получает production secrets. Для первой установки предпочтителен локальный Ansible с физического компьютера.

## Эксплуатация и приёмка

См. [deployment](docs/deployment.md), [будущую систему VPS/VPN](docs/fleet-roadmap.md), OPLA для security/monitoring. До реальной установки нужны out-of-band console, backup, cold install, repeat run, reboot, model readiness, failed rollout и recovery. У K3s сохраняются datastore и соответствующий token; очистка данных узла не является способом исправить upgrade.

OPLA XDP этим проектом не присоединяется. Не заменяй чужую Cilium/BPF-программу, не переноси firewall rules вслепую и не считай host filtering защитой от насыщения upstream канала.

## Лицензия

[MIT](LICENSE); copyright сохранён. Лицензии моделей и образов учитываются отдельно.
