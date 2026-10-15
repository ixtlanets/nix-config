# Spec: узел `goar-team` — отдельная точка выхода VLESS для команды Гоар

## Goal

Развернуть независимый VLESS+Reality сервер `goar-team` (Hosting-VDS, Франкфурт #2,
HVDS-4G-EU) и подготовить в репозитории всё, чтобы:

1. провижн узла был идемпотентным скриптом, который оркестратор запускает по SSH;
2. клиентские конфиги для команды (iOS/Android, macOS, Windows) генерировались из
   проверенных шаблонов;
3. состояние узла было восстановимо из DR-бандла.

Узел нужен как замена умершего стороннего VPN команды Гоар (до ~10 человек + 1-3 доп.).
Срочность высокая. Независимость от существующего Frankfurt обязательна: своя
REALITY-идентичность, своя судьба при блокировке.

## Decisions (зафиксированы в grilling 2026-10-13)

- Провайдер/локация: Hosting-VDS, **Франкфурт #2** (та же локация, что Frankfurt).
- План: **HVDS-4G-EU** — 2 vCPU / 4 ГБ / 35 ГБ NVMe / 4 ТБ трафика, €6.89/мес.
- ОС: **Ubuntu 24.04 LTS** (как Frankfurt: `reality-ezpz` + Docker проверены на ней).
- Роль узла: **только чистый VLESS+Reality**. Без London-роутинга, без WireGuard-хаба
  `wg0` (они нужны только для host-to-host задач владельца).
- REALITY: **своя новая идентичность** (новые private/public key, short_id, service_path).
  Камуфляж остаётся `www.google.com`, transport TCP, порт 443.
- Доступ: **только IP**, без домена.
- Tailscale: **завести в tailnet** для админ-доступа.
- Host baseline: **2 ГиБ swap + маскировка `fwupd-refresh.timer` + firewall (22/80/443)**.
- Provisioning: **идемпотентный скрипт + короткий runbook**; скрипт запускает оркестратор.
- Раздача конфигов: **файлы/QR по человеку**.
- Текущие юзеры Гоар на Frankfurt (`goar`, `Goar4`) **остаются работать как есть**.
- Имя узла в репо: **`goar-team`**; DR-бандл `secrets/proxy/goar-team/`,
  клиентские конфиги `secrets/vless/goar-team-*.json`.

## Constraints

- Репозиторий локальный по push? Нет: `origin = git@github.com:ixtlanets/nix-config.git`,
  но **Codex не пушит**; коммиты локальные на feature-ветке.
- `secrets/**` под git-crypt (`.gitattributes`: `secrets/proxy/**`, `secrets/vless/**`).
  Секреты не попадают в открытые `docs/**`.
- Frankfurt **не трогать** без явной необходимости (AGENTS.md про London; тот же принцип
  для Frankfurt: не менять и не перезапускать существующий узел).
- Идемпотентность: повторный запуск provisioning не ломает уже настроенный узел.
- Не коммитить plaintext-секреты в незашифрованные пути.
- `nixosConfigurations` не трогаем: узел — Ubuntu VPS, как `london`.

## Ground truth (проверено 2026-10-13)

- Frankfurt: Ubuntu 24.04.4 LTS, kernel 6.8, Docker 29.3.0, Compose v5.1.1,
  `/opt/reality-ezpz/`, контейнер `reality-ezpz-engine-1`, образ `gzxhwq/sing-box:1.13.5`.
- Frankfurt: ufw **inactive**; порты открыты правилами Docker + `iptables` (INPUT ACCEPT,
  `-A INPUT -p udp --dport 51820 -j ACCEPT`); swap **0 B**; `PermitRootLogin yes`.
- Frankfurt Tailscale сейчас `Logged out` (узлы tailnet не в сети с Frankfurt).
- London baseline-паттерн: `hosts/london/ubuntu/host-baseline/{apply.sh,README.md}` —
  идемпотентный скрипт: swap-файл атомарно, `root:root 0600`, отказ от не-swap/дублей
  fstab; маскировка `fwupd-refresh.timer`; не трогает сервисы.
- Помощник пользователей: `scripts/reality-user.py` (add/list/show, валидирует
  `sing-box check`, делает бэкапы, **не** перезапускает контейнер). Дефолтный образ в
  нём — `gzxhwq/sing-box:1.8.14`; на Frankfurt фактически `1.13.5`.
- Формы клиентских конфигов (проверенные шаблоны):
  - мобильные (SFI 1.14): `secrets/vless/goar4-iphone.json` — typed-DNS, jsDelivr rule-set
    + `download_detour: direct` + `dns-bootstrap`;
  - macOS GUI: `secrets/vless/m1max-gui.json` — legacy-DNS;
  - Windows: `secrets/vless/windows-throne.json` — TUN `throne-tun`, `block` outbound.
- VLESS-outbound форма: `type vless`, `flow xtls-rprx-vision`, `packet_encoding xudp`,
  `server_port 443`, `tls.reality{enabled,public_key,short_id}`, `server_name www.google.com`,
  `utls{fingerprint chrome}`.
- Тесты: `tests/vless-configs.sh` (jq-проверка bootstrap rule-set) — образец для нового теста.

## Out of scope

- Перенос текущих юзеров Гоар с Frankfurt.
- London-роутинг и WireGuard-хаб на новом узле.
- Автоматический заказ VM через API провайдера (проверять не будем).
- Любые изменения на Frankfurt.
- Генерация реальных клиентских конфигов с боевыми UUID — это отдельный тикет
  (02), он ждёт, пока VM создана и REALITY-идентичность сгенерирована.

## Deliverables (ticket 01)

1. `hosts/goar-team/ubuntu/provision/` — идемпотентный provisioning-скрипт + README.
2. `hosts/goar-team/ubuntu/host-baseline/` — swap + fwupd-маскировка (паттерн London).
3. `secrets/proxy/goar-team/README.md` — инвентарь DR-бандла (зашифрован).
4. `docs/goar-team-vless-node.md` — короткий runbook (что делает человек, что скрипт).
5. Секция про `goar-team` в `docs/proxy-setup.md`.
6. `tests/goar-team-provision.sh` — проверка структуры/идемпотентности артефактов.

## Deliverables (ticket 02, blocked by 01 + живой VM)

Клиентские конфиги `secrets/vless/goar-team-{ios,android,macos,windows}.json` из
проверенных шаблонов с боевыми значениями нового узла + тест формы.
