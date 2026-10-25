# Проверенные пути Compose и K3s

**Русский** · [English](acceptance-evidence.en.md)

На 25.10.2026 исходный коммит `b1d965b85b5217a4a4ca1c6f0889aee8e6b46da7` прошёл описанную ниже приёмку. Результаты не распространяются автоматически на последующие commits, другие модели или серверы.

В этом коммите исправлены два условия when, ошибочно вложенные в параметры assert. Подготовка и управление приёмкой вынесены в отдельный проект infra-delivery-lab; OPLA не является частью этой поставки.

| Путь | Проверено |
|---|---|
| Compose | Развёртывание CPU server, health 200 и 8 токенов; API закрыт на non-loopback адресе гостя; повторный apply сохраняет container ID/start time; после reboot inference восстановлен |
| K3s | Server/agent Ready, CoreDNS и API на частном интерфейсе; local PV/PVC на agent; реальная генерация из разрешённого namespace на другой ноде; отказ постороннему namespace по ClusterIP и Pod IP |
| Повторение/восстановление K3s | Повторный apply сохраняет контейнер; после reboot agent/server восстановлены inference/изоляция, сохранены PV/PVC и ClusterIP |

Входные данные: `ghcr.io/ggml-org/llama.cpp@sha256:20c4196fc08b459a34ef78aaa05b101333b2fac687e30ec99f37b3c9dc071b44`; `stories260K.gguf`, SHA-256 `047bf46455a544931cff6fef14d7910154c56afbc23ab1c5e56a72e69912c04b`; K3s `v1.36.5+k3s1`.

Доставка: infra-delivery-lab `3fa84355e944c787689ab507e2d6b6f6aec1c82b`; локальный GitLab Self-Managed pipeline 21 / job 68 / runner 2. Это не pipeline GitLab.com. Полный сценарий завершился выключением обеих тестовых ВМ.

Ограничения: tiny-model smoke test не оценивает качество LLM; local PV привязан к agent, server один; production HA, живой egress test, удалённый VPS deployment и автоматический rollback не подтверждены. Публикация этого документа не требует изменения pin принятой рабочей копии `llama-k8s-reviewed`.
