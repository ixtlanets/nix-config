# 01 — `goar-team`: provisioning bundle, host baseline, DR-инвентарь, runbook

Status: ready-for-agent
Blocked by: none
Created: 2026-10-13

## Goal

Добавить в репозиторий всё, что нужно для идемпотентного развёртывания нового
VLESS+Reality узла `goar-team` (Ubuntu 24.04 VPS), не выполняя развёртывание здесь.
Итог — набор артефактов, которые оркестратор запускает по SSH после того, как VM создана
и оплачена.

## Context

- Полный spec: `.scratch/goar-team/spec.md` — прочитать целиком.
- Аналоги для подражания:
  - `hosts/london/ubuntu/host-baseline/{apply.sh,README.md}` — идемпотентный host baseline.
  - `scripts/reality-user.py` — управление пользователями reality-ezpz.
  - `docs/proxy-setup.md` — существующая документация Frankfurt/London.
- Узел — Ubuntu VPS, **не** NixOS: не добавлять в `nixosConfigurations`.
- `secrets/**` под git-crypt. Всё, что попадает в `secrets/proxy/goar-team/**`, будет
  зашифровано автоматически (`.gitattributes` уже покрывает `secrets/proxy/**`).

## Deliverables

### 1. `hosts/goar-team/ubuntu/provision/`

- `provision.sh` — идемпотентный скрипт, запускается **локально** и работает по SSH
  на целевом хосте (паттерн `hosts/london/ubuntu/host-baseline/apply.sh`).
  Переменные окружения: `REMOTE` (обязателен, напр. `root@<IP>`), опционально
  `SSH_KEY`, `REALITY_DOMAIN` (default `www.google.com`), `REALITY_PORT` (default `443`).
  Шаги (каждый идемпотентен):
  1. Проверка ОС (Ubuntu) и наличия `docker`, `docker compose`, `tailscale`, `jq`.
  2. Установка Docker Engine + Compose plugin, если отсутствуют (официальный скрипт).
  3. Установка `reality-ezpz` в `/opt/reality-ezpz` **только если каталога нет**;
     при первом развёртывании — с `--transport tcp --domain "$REALITY_DOMAIN" --port "$REALITY_PORT"`.
  4. Деплой `scripts/reality-user.py` как `/opt/reality-ezpz/reality-user` (chmod +x),
     обновлять при изменении.
  5. Установка и подключение Tailscale (если не подключён) — команда подключения
     печатается, ключ передаётся через `TAILSCALE_AUTHKEY` (опционально; без ключа шаг
     пропускается с явным предупреждением, не падает).
  6. Проверка, что контейнер `reality-ezpz-engine-1` поднят; вывод статуса.
  Скрипт **не** трогает Frankfurt, не пушит, не удаляет существующее состояние.
- `README.md` — что делает скрипт, какие шаги остаются за человеком (создание VM, оплата,
  Tailscale auth key), как проверить результат.

### 2. `hosts/goar-team/ubuntu/host-baseline/`

- `apply.sh` — скопировать/адаптировать идемпотентный паттерн London: 2 ГиБ `/swapfile`,
  маскировка `fwupd-refresh.timer`. Дефолт `REMOTE=root@<IP>` через переменную окружения.
- `README.md` — по образцу London.

### 3. `secrets/proxy/goar-team/README.md`

Инвентарь DR-бандла (зашифрован автоматически): перечень ожидаемых файлов
(`config`, `engine.conf`, `docker-compose.yml`, `users`, `notes.md`), что обязательно
сохранять при восстановлении (REALITY `private_key`, `short_id`, UUIDs, версия образа
`gzxhwq/sing-box:1.13.5`), и правило обновлять бандл после изменений. По образцу
`secrets/proxy/frankfurt/README.md`.

### 4. `docs/goar-team-vless-node.md`

Короткий runbook:
- роль узла (чистый VLESS, без London/WireGuard);
- порядок: создать VM (Hosting-VDS, Франкфурт #2, HVDS-4G-EU, Ubuntu 24.04) → оплатить →
  зафиксировать IP → `provision.sh` → `host-baseline/apply.sh` → Tailscale → снять
  REALITY-идентичность и `users` в DR-бандл;
- что делает человек, что скрипт;
- отличия от Frankfurt (нет London-роутинга, нет `wg0`, своя REALITY-идентичность).

### 5. `docs/proxy-setup.md`

Добавить секцию про `goar-team` в том же стиле, что Frankfurt/London: назначение,
хост/порт, что не входит (London/WireGuard), ссылка на runbook. Не переписывать
существующие секции.

### 6. `tests/goar-team-provision.sh`

Shell-тест в стиле `tests/vless-configs.sh`: проверяет, что артефакты существуют,
`provision.sh` исполняем, содержит защиту от повторной установки reality-ezpz
(проверка наличия `/opt/reality-ezpz`), и что `secrets/proxy/goar-team/README.md`
перечисляет обязательные для восстановления поля. Тест не должен требовать сети.

## Acceptance criteria

- [ ] `hosts/goar-team/ubuntu/provision/provision.sh` существует, исполняем, `bash -n` проходит.
- [ ] Скрипт идемпотентен по построению: повторная установка reality-ezpz пропускается,
      если `/opt/reality-ezpz` уже есть; установка Docker пропускается, если `docker` есть.
- [ ] `hosts/goar-team/ubuntu/host-baseline/apply.sh` существует, исполняем, `bash -n` проходит,
      повторяет гарантии London (атомарный swap, отказ от не-swap, дубли fstab).
- [ ] `secrets/proxy/goar-team/README.md` перечисляет `config`, `engine.conf`,
      `docker-compose.yml`, `users` и требование сохранить REALITY-идентичность.
- [ ] `docs/goar-team-vless-node.md` существует и описывает порядок развёртывания.
- [ ] В `docs/proxy-setup.md` добавлена секция `goar-team`, существующие секции не изменены.
- [ ] `tests/goar-team-provision.sh` существует, исполняем, `bash -n` проходит, `bash tests/goar-team-provision.sh` зелёный.
- [ ] `git diff --check` чистый.
- [ ] Ни один существующий файл Frankfurt/London не изменён.

## Constraints

- READ-ONLY против прода: никаких подключений к Frankfurt/London/новой VM, никаких
  установок на живые хосты. Только файлы в репозитории.
- Не выполнять `git push`, не переключать ветки, не трогать другие worktree.
- Не использовать исключённые пакеты скиллов (например `superpowers`).
- Не коммитить plaintext-секреты в незашифрованные пути.
- Идемпотентность обязательна: скрипты проектируются для повторного запуска.

## Comments

- 2026-10-13: тикет создан, baseline `73df79c` на ветке `feature/goar-team`.
