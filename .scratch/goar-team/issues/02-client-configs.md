# 02 — `goar-team`: клиентские конфиги команды из проверенных шаблонов

Status: ready-for-human
Blocked by: 01 (provision bundle), плюс живая VM создана и REALITY-идентичность сгенерирована
Created: 2026-10-13

## Goal

Сгенерировать клиентские sing-box-конфиги для команды Гоар против нового узла
`goar-team`, переиспользуя проверенные шаблоны форм. Каждый конфиг — на одно устройство,
раздача файлом/QR.

## Blocked by

- Тикет 01: нужны артефакты провижна и структура DR-бандла.
- Живой узел: нужны фактические `server` (IP), `public_key`, `short_id` нового узла —
  они появляются только после развёртывания VM и генерации новой REALITY-идентичности.
  До этого тикет остаётся заблокированным; конфиги с боевыми значениями не пишутся.

## Deliverables

- `secrets/vless/goar-team-ios.json` — форма как `goar4-iphone.json`
  (typed-DNS, jsDelivr rule-set + `download_detour: direct` + `dns-bootstrap`).
- `secrets/vless/goar-team-android.json` — та же мобильная форма (SFI/Android sing-box).
- `secrets/vless/goar-team-macos.json` — форма как `m1max-gui.json` (legacy-DNS, sing-box GUI).
- `secrets/vless/goar-team-windows.json` — форма как `windows-throne.json`
  (TUN `throne-tun`, `block` outbound, без `auto_redirect`).
- Расширить `tests/vless-configs.sh` (или добавить `tests/goar-team-configs.sh`): проверка,
  что мобильные конфиги используют jsDelivr + `download_detour: direct` + `dns-bootstrap`,
  а outbound содержит новый `server`/`public_key`/`short_id` (значения передаются аргументом
  или берутся из DR-бандла).

## Acceptance criteria

- [ ] Каждый из четырёх конфигов существует и валиден JSON.
- [ ] Мобильные конфиги следуют форме `goar4-iphone.json` (jsDelivr + direct + dns-bootstrap).
- [ ] macOS-конфиг следует форме `m1max-gui.json`.
- [ ] Windows-конфиг следует форме `windows-throne.json`.
- [ ] Все конфиги указывают на новый узел (свой `server`, `public_key`, `short_id`), а не на Frankfurt.
- [ ] Тест формы зелёный.
- [ ] `git diff --check` чистый.

## Constraints

- READ-ONLY против прода.
- Не переиспользовать UUID других устройств: у каждого устройства свой VLESS-юзер,
  заводится через `reality-user add <name>` на новом узле.
- Секреты — только в `secrets/vless/**` (под git-crypt).

## Comments

- 2026-10-13: тикет создан как заблокированный; ждёт тикет 01 и живую VM.
