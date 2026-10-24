# Следующий проект: управляемый VPS/VPN fleet

**Русский** · [English](fleet-roadmap.en.md)

Это ТЗ следующего этапа, а не работающие функции данной редакции.

## Цель

Управление арендованными Linux VPS из физически доступного основного компьютера. Идемпотентное добавление/обновление/отзыв узлов, несколько VPN-профилей, журналирование административных действий, контроль состояния/безопасности и независимые backups. LLM inference — опциональное приложение; GPU не является требованием VPN-сервера.

## Разделение ответственности

- Controller: private inventory, доверенные host keys, secret store, release lock, план изменений и аудит выполнения.
- Node base: поддерживаемая ОС, отдельный оператор, SSH policy, time sync, обновления, scoped firewall, ротация журналов.
- Management VPN: устойчивый приватный канал controller ↔ nodes, отдельный от пользовательского трафика.
- User transports: отдельные AmneziaWG и Xray modules с явными совместимыми версиями клиента/сервера; sing-box выбирается как поддерживаемый клиент/маршрутизатор для конкретного транспорта.
- Observability: OPLA-compatible telemetry, Zabbix host provisioning и alert routing. Основной компьютер может управлять fleet, но не должен быть единственной always-on точкой мониторинга, если он выключается.
- Applications: Compose или опциональный K3s; inference выбирается отдельно. VPN host services не нужно автоматически помещать в privileged Kubernetes pods.

Не считать любой WireGuard client совместимым с любой версией AmneziaWG. Не обещать, что sing-box поддерживает все transport/version комбинации: нужна проверяемая матрица и native AmneziaWG client там, где требуется. Xray — engine, VLESS/REALITY и другие сочетания задаются отдельными профилями, а не случайной смесью имён.

## Контракт профиля и lifecycle

Manifest описывает node/site, runtime, management route, transport profile, release/checksum, ключи по ссылке, клиентские ограничения, DNS/routing/IPv6 policy и monitoring/backup endpoint. Секреты не попадают в Git, QR-коды, публичные artifacts или логи.

Будущий controller: validate → plan → apply serially → verify → record; отдельные rotate, revoke, backup, restore и retire. Это проект интерфейса, ещё не команды.

Каждый client получает собственные ключи/ID и профиль, который можно адресно отозвать. Повторный apply не генерирует новые ключи без намеренной rotation. При ротации учитывается период перекрытия и проверка доставки нового профиля. QR/URI/config считаются credential-bearing data.

Audit фиксирует оператора, node, время, release/manifest hashes, action/result и факт ротации без ключей и полного трафика. Сбор browsing history/полезной нагрузки по умолчанию не нужен. Определяются retention и доступ к журналам. «Без логов вообще» не обещается при включённом административном аудите.

## Приёмка

Первичный bootstrap с консолью, доверенные fingerprints, восстановление SSH при отказе management VPN; выпуск/отзыв двух независимых клиентов; reboot; DNS/IPv6 leak checks; MTU/UDP/TCP fallback по профилю; недоступность одной страны; rollback обновления; encrypted backup и восстановление. Сам факт открытого порта или успешного handshake не заменяет проверку маршрута, DNS и реального клиентского трафика.

Провайдер, домены, ОС, бюджет и требования доступности выбираются до первого реального deployment. Защита от volumetric DDoS требует upstream возможностей; XDP хоста не расширяет пропускную способность канала.
