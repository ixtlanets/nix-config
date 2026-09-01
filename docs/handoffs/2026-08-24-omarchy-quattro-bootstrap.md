# Handoff: персональный bootstrap Omarchy Quattro

**Дата:** 2026-08-24
**Состояние:** исследование завершено; реализация не начиналась

## Цель следующей сессии

Спроектировать и, после подтверждения scope, реализовать установку личного
окружения поверх Omarchy Quattro для нескольких ноутбуков. Требуется результат
в духе `nixos-anywhere`, но без строгой фиксации версий: unattended-установка
Omarchy, затем одна команда для пакетов, dotfiles, Hyprland overrides и
секретов.

## Уже зафиксировано

Полное исследование, первичные источники, сравнение с текущей Nix/Home Manager
конфигурацией и риски находятся в:

- [`docs/superpowers/specs/2026-08-24-omarchy-quattro-personal-bootstrap-research.md`](../superpowers/specs/2026-08-24-omarchy-quattro-personal-bootstrap-research.md)

Не пересказывать его в новом плане; использовать как source of truth и
обновлять только если upstream Omarchy изменился.

## Принятые решения

- Omarchy владеет ОС, desktop, пакетными обновлениями, Hyprland defaults и
  desktop integration.
- Репозиторий владеет только дополнительными пакетами, Zsh/Git/GPG/SSH,
  личными dotfiles, Hyprland overrides и опциональными host-specific services.
- Текущий `install.sh` нельзя запускать целиком на Omarchy: он также меняет
  KDE/GNOME, сеть, firewall, sshd, Nix и systemd services. Из него нужно
  извлечь узкий Omarchy user profile.
- Codex/OpenCode по умолчанию оставить штатным lazy mise wrappers Omarchy.
  Явные backend IDs и 24-часовой cooldown — только опциональный режим.
- Не переносить полный Hyprland config. Управлять только
  `~/.config/hypr/input.lua` и `~/.config/hypr/bindings.lua`, которые Quattro
  загружает после defaults.
- Требуемая базовая раскладка: `us,ru`, переключение `Super+Space`. Штатный
  `Super+Space` Omarchy нужно unbind. `Super+D` должен запускать
  `omarchy-menu toggle apps`; при желании полное меню можно назначить на
  `Super+Alt+D`.
- Штатный unattended installer Quattro использует отдельный носитель/образ с
  меткой `cidata`. Он умеет disk/hostname/timezone/keyboard, пользователя,
  Git identity, публичные `authorized_keys` и Tailscale enrollment.
- `cidata` не принимает произвольный post-install script. Поэтому персональный
  bootstrap выполняется второй стадией. На сети, где control path Tailscale
  требует VLESS, для первого подключения нужно использовать LAN SSH и не
  включать Tailscale enrollment в `cidata`.
- Порядок настройки сети обязателен: установить и проверить VLESS, оставить
  тоннель активным во время `tailscale up`, дождаться `BackendState: Running`
  и только после этого использовать Tailscale как транспорт для дальнейшего
  provisioning.
- Приватные SSH/GPG keys не помещать в `cidata`. Передавать после установки по
  защищённому каналу либо получать с hardware token/password manager.
- Для `git-crypt` нужен внешний bootstrap key; закрытый ключ внутри
  заблокированного репозитория не может разблокировать его сам.

## Предлагаемая структура

Имена предварительные:

```text
omarchy/
├── cidata/
│   ├── common/
│   └── <host>/
└── packages/
    ├── required.txt
    └── optional-gui.txt
dotfiles/omarchy/
└── hypr/
    ├── bindings.lua
    └── input.lua
scripts/
├── omarchy-build-cidata.sh
└── omarchy-provision.sh
install-omarchy.sh
```

Возможный workflow:

```text
build cidata for <host>
        ↓
boot official Omarchy ISO + cidata
        ↓
base OS + <user> + authorized_keys
        ↓ LAN SSH
install + start + verify VLESS
        ↓ keep VLESS active
authorize Tailscale and verify BackendState: Running
        ↓
scripts/omarchy-provision.sh <user>@<host>
        ↓
packages + dotfiles + Hyprland + securely delivered secrets + verification
```

## Открытые решения перед реализацией

1. Выбрать один pilot laptop и подтвердить точный install disk. `cidata`
   содержит destructive disk target, поэтому profile нельзя переносить между
   машинами без проверки.
2. Решить, где хранить генерируемые `user_credentials.json`, LUKS passphrase и
   `tailscale_authkey`. Они не должны попадать в Git; output directory должен
   быть gitignored.
3. Выбрать secret bootstrap: hardware token, password manager, отдельный
   `git-crypt export-key` или зашифрованный bundle с одноразовой передачей.
4. Определить минимальный package manifest. Начать с shell/dev essentials,
   Brave и CLI; GUI и host services вынести в отдельные группы.
5. Решить, будет ли bootstrap копировать файлы через `install`, управлять ими
   через Stow или использовать другой dotfile manager. Для двух Hyprland files
   простое идемпотентное копирование достаточно.
6. Bash оставить login/session shell на первом pilot; Zsh запускать как
   интерактивную shell терминала до отдельной проверки login/SSH/session env.

## Критерии готовности pilot

- Повторный запуск provisioner не вносит изменений и не ломает Omarchy.
- `hyprctl reload` успешен, `hyprctl configerrors` пуст.
- `Super+Space` меняет `us/ru`; `Super+D` открывает apps menu.
- Git identity, GPG secret key, SSH aliases/`ProxyJump` и password store
  доступны без раскрытия секретов в логах.
- Brave, Codex/OpenCode и выбранные программы запускаются; у каждого binary
  один владелец.
- `omarchy update` продолжает работать штатно.
- Provisioner проверяет hostname/OS/disk expectations до любых destructive или
  privileged действий.

## Suggested skills

- `research` — только если перед реализацией нужно перепроверить свежую схему
  `cidata` или изменившиеся команды Quattro по первичным источникам.
- `tdd` — для idempotent shell helpers, генератора `cidata`, dry-run и тестов на
  временных каталогах/fake commands.
- `codebase-design` — если user bootstrap начнёт разрастаться в несколько
  профилей и потребуется чёткая граница common/host/secrets.
- `code-review` — перед первым запуском на реальном laptop, особенно для disk,
  LUKS, firewall и secret-handling paths.

## Важные ограничения

- Не запускать rebuild-команды из repository guidelines; это исследование
  Omarchy, а не изменение NixOS host.
- Не менять London proxy/Vaultwarden assets.
- Не встраивать приватные ключи в ISO или `cidata`.
- Не использовать текущий `install.sh` как единый entry point без явного
  Omarchy profile и opt-in для network/system services.
