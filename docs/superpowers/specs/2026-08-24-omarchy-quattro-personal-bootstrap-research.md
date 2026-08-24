# Персональная конфигурация поверх Omarchy Quattro

**Дата проверки:** 2026-08-24

**Статус:** feasibility study; конфигурация не изменялась

**База проверки:** стабильный Omarchy Quattro `v4.0.0` (`f0020448`), выпущенный
2026-08-14; текущая ветка `quattro` дополнительно просмотрена на коммите
`43bfe9b9` от 2026-08-23. Стабильный статус и переход внутренностей Omarchy на
системные пакеты подтверждены [официальным релизом v4.0.0](https://github.com/basecamp/omarchy/releases/tag/v4.0.0).

## Краткий вывод

**Да, получить практически эквивалентное личное окружение возможно.** Для
заявленной цели — автоматически получить привычные Zsh, Git, GPG/SSH, Codex,
OpenCode, Brave и набор программ без строгой фиксации версий — Arch-основа
Omarchy даже проще NixOS. Pacman/AUR и mise дают актуальные версии, а один
идемпотентный bootstrap-скрипт может восстановить пользовательский слой.

Рекомендуемая граница ответственности:

1. **Omarchy владеет ОС, Hyprland/Quickshell, базовыми пакетами, браузерной и
   desktop-интеграцией, миграциями и обновлениями.**
2. **Этот репозиторий владеет личными dotfiles, дополнительным списком пакетов,
   Git/GPG/SSH и точечными пользовательскими сервисами.** Для Codex/OpenCode
   проще оставить штатную mise policy Omarchy, пока не понадобится особая
   политика источников или задержки обновлений.
3. Для этого нужен отдельный `omarchy`-профиль/скрипт. Текущий `install.sh`
   полезен как исходник, но запускать его целиком поверх Omarchy не следует.

Это даст не бит-в-бит воспроизводимую систему, а требуемый результат:
«чистый Quattro + одна команда → привычное рабочее окружение». Версии будут
плавающими, обновления — штатными для Omarchy.

## Что подтверждено первичными источниками

### Пользовательский слой отделён от Omarchy

Quattro считает `~/.config` пользовательской зоной, а `/usr/share/omarchy` —
пакетной зоной, которую нельзя править напрямую. Обычные изменения следует
делать в пользовательских override-файлах; `~/.bashrc` при обычных обновлениях
не перезаписывается. Для автоматических действий есть исполняемые hooks, в том
числе `post-boot`, `post-update` и `pre-refresh-pacman`. Источник:
[официальная глава Dotfiles для v4.0.0](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/31-dotfiles.md).

Внутренняя модель Quattro состоит из `/etc/skel` для создания нового home,
одноразовой user finalization и явного destructive resync. Команда
`omarchy reinstall configs` копирует `/etc/skel` поверх home и потому может
затереть совпадающие файлы; это не обычный update. Источники:
[file-layout v4.0.0](https://github.com/basecamp/omarchy/blob/v4.0.0/docs/file-layout.md),
[реализация reinstall-configs](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-reinstall-configs).

**Вывод:** собственные `~/.zshrc`, Git/SSH config и файлы в отдельном namespace
`~/.config/nix-config/` не являются пакетными файлами Omarchy и подходят для
dotfile-менеджера или bootstrap-скрипта. Перед `omarchy reinstall configs` их
всё равно нужно считать требующими backup/reapply, потому что сама команда
намеренно destructive.

### Пакеты и обновления

Произвольные пакеты из официального Arch repository устанавливаются через
`omarchy pkg add ...`; AUR доступен через отдельный пункт меню/внутренний helper.
Официальная документация предупреждает, что AUR не проверяется командой Arch.
Источник: [Other Packages v4.0.0](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/29-other-packages.md).

Штатный `omarchy update` делает snapshot, обновляет системные пакеты, запускает
миграции и пользовательский `post-update`, затем обновляет AUR и mise tools.
Прямой `pacman -Syu` намеренно обходить не стоит: он пропускает эту обвязку.
Источники: [Updates v4.0.0](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/30-updates.md),
[update pipeline](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-update),
[AUR update](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-update-aur-pkgs).

**Вывод:** bootstrap должен устанавливать недостающие пакеты, но не становиться
вторым системным updater. После первого применения их должен обновлять
`omarchy update`.

### Codex, OpenCode и mise

Codex CLI и OpenCode уже входят в Quattro как lazy wrappers. На первой попытке
запуска wrapper выполняет `mise use -g <tool>` и затем `mise x`; системное
обновление запускает `MISE_MINIMUM_RELEASE_AGE=0 mise up`. Источники:
[список штатных mise wrappers](https://github.com/basecamp/omarchy/blob/v4.0.0/install/user/mise.sh),
[реализация wrapper](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-mise-install),
[mise update](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-update-mise),
[официальная глава AI](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/17-ai.md).

Текущая конфигурация этого репозитория уже выбирает явные backends
`aqua:openai/codex@latest` и `github:anomalyco/opencode@latest` и задаёт
24-часовой cooldown в [Home Manager common.nix](../../../modules/home-manager/common.nix#L280-L289)
и в Arch bootstrap [install.sh](../../../install.sh#L422-L438).

**Вывод:** нельзя оставлять два независимых владельца одного CLI без явного
решения. Есть два нормальных режима:

- самый простой для Omarchy — принять его wrappers и shorthand keys
  `codex`/`opencode`;
- сохранить текущие явные backend IDs, поставить mise shims раньше
  `~/.local/bin` и не запускать Omarchy wrapper для этих команд.

Для заявленного требования без фиксации версий рекомендуется первый вариант:
он меньше всего конфликтует с Omarchy и обновляется вместе с системой. Второй
имеет смысл только при желании сохранить нынешние явные источники и
24-часовой cooldown; тогда bootstrap должен удалить возможные дублирующие
shorthand entries, если Codex уже запускался до его применения. Следует также
осознанно принять, что штатный `omarchy update` задаёт
`MISE_MINIMUM_RELEASE_AGE=0`, то есть обходит нынешний cooldown.

### Brave и ChatGPT Desktop

Brave штатно устанавливается helper-ом Omarchy как AUR-пакет `brave-bin`.
Helper создаёт `/etc/brave/policies/managed`, ставит Wayland/Chromium flags,
native messaging extensions и применяет текущую тему. Затем Brave можно сделать
XDG browser через `omarchy default browser brave`. Источники:
[browser installer](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-install-browser),
[default browser](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-default-browser),
[browser manual](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/23-browsers.md).

ChatGPT Desktop тоже имеет штатный installer: он ставит Omarchy package
`openai-codex-desktop` и запускает `/usr/bin/chatgpt`. Это отдельный desktop
package, не Codex CLI. Источник:
[ChatGPT installer v4.0.0](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-install-ai-chatgpt).

Omarchy пишет только свой `color.json` в policy directory Brave. Поэтому
список обязательных расширений и прочие личные policies можно поддерживать
отдельным JSON-файлом, не перезаписывая `color.json`; это вывод из
[theme helper](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-theme-set-browser).

### Omarchy остаётся Bash-first

Новый пользователь в Quattro создаётся с `/bin/bash`, stock shell setup — это
`/etc/skel/.bashrc`, который source-ит Omarchy aliases/functions. Zsh отсутствует
в базовом package list. При этом команды Omarchy имеют собственный
`#!/bin/bash`, поэтому смена **интерактивной** login shell не меняет интерпретатор
самих `omarchy-*` scripts. Источники:
[user provisioning](https://github.com/basecamp/omarchy/blob/v4.0.0/bin/omarchy-provision-owner),
[stock bashrc](https://github.com/basecamp/omarchy/blob/v4.0.0/default/bashrc),
[base package list](https://github.com/basecamp/omarchy/blob/v4.0.0/install/omarchy-base.packages).

**Вывод:** интерактивный Zsh реализуем, но это не штатная first-class shell
конфигурация Omarchy. Нельзя source-ить весь `default/bash/rc` из Zsh: там есть
Bash-specific init и `bind`. На первом этапе надёжнее оставить Bash login/session
shell Omarchy и настроить терминал на запуск Zsh. Схема:

1. установить `zsh`, completions, autosuggestions и syntax highlighting;
2. развернуть собственный `~/.zshrc`;
3. сохранить `~/.local/share/mise/shims` и `~/.local/bin` в `PATH`, Starship,
   direnv, fzf и `GPG_TTY`;
4. перенести только нужные Omarchy aliases/functions в Zsh-совместимой форме;
5. не менять login shell через `chsh`, пока нет отдельной проверки login, SSH и
   graphical session environment; для обычной работы достаточно Zsh внутри
   терминала.

Текущий [write_zshrc](../../../install.sh#L350-L419) уже реализует основную
часть этой схемы. Потеря stock aliases/functions — небольшая, но реальная
цена перехода с Bash.

## Насколько текущий репозиторий уже готов

Home Manager сейчас декларативно задаёт Zsh, Git identity, GPG, SSH host
aliases, mise, pass и большой user package set в
[modules/home-manager/common.nix](../../../modules/home-manager/common.nix#L128-L322).
Для Arch/CachyOS уже существует императивный `install.sh`, поэтому работа не
начинается с нуля:

| Область | Что уже есть | Gap для Quattro |
|---|---|---|
| Zsh | plugins, history, completion, Starship, fzf, direnv, mise, `GPG_TTY` | сохранить Omarchy paths и явно перенести нужные Bash conveniences |
| Git | имя, email, default branch, diff-so-fancy | HM-конфигурация шире; при необходимости отдельно задать signing key/`commit.gpgSign` |
| GPG/pass | импорт public/private key и ownertrust, `gpg-agent.conf`, clone password-store | нужен внешний bootstrap key до `git-crypt unlock` |
| SSH | копирование private/public keys, `authorized_keys`, запуск sshd | не переносится `programs.ssh.settings`: host aliases и `ProxyJump` требуют отдельного `~/.ssh/config` слоя |
| CLI | явные mise backends для Codex/OpenCode | по умолчанию принять штатные lazy wrappers; явные backends оставить опциональным режимом |
| Apps | большой Arch/AUR package list | Brave отсутствует в списке; ChatGPT package name лучше отдать штатному installer Omarchy |

Подтверждающие места: пакетный список и полный orchestration находятся в
[install.sh](../../../install.sh#L1480-L1624), Git/GPG/SSH — в
[install.sh](../../../install.sh#L131-L273), а более полный SSH config с
`ProxyJump` — в [common.nix](../../../modules/home-manager/common.nix#L213-L272).

### Почему нельзя запускать `install.sh` целиком

Помимо личного окружения скрипт:

- устанавливает десятки desktop/dev packages и глобальные npm packages;
- меняет KDE и GNOME settings;
- включает `tailscaled` и пытается настроить subnet routing;
- пишет WireGuard/VLESS, меняет Docker/UFW rules;
- открывает SSH firewall, включает `sshd` и копирует ключи;
- перезаписывает `/etc/nix/nix.conf`, запускает `nix-daemon` и добавляет Nix
  packages;
- создаёт/включает дополнительные systemd services.

Это видно в [main](../../../install.sh#L1465-L1624), сетевых функциях
[install.sh](../../../install.sh#L1140-L1420) и Nix setup
[install.sh](../../../install.sh#L70-L113). Такие действия могут быть нужны на
конкретном host, но они шире цели «личное окружение поверх Omarchy» и частично
пересекаются с собственными NetworkManager/UFW/update решениями Quattro.

## Рекомендуемая реализация

Создать отдельный entry point, например `install-omarchy.sh`, или профиль
`./install.sh omarchy-user`. Он должен быть идемпотентным и разбитым на четыре
узких слоя.

### 1. Packages

- Проверить, что это Omarchy (`command -v omarchy`, package/version), и выйти
  на других системах.
- Для обычных пакетов использовать `omarchy pkg add`/pacman `--needed`, для
  AUR — штатный Omarchy AUR path.
- Brave и ChatGPT ставить только через `omarchy install browser brave` и
  `omarchy install ai chatgpt`, затем `omarchy default browser brave`.
- Не запускать system upgrade: это обязанность `omarchy update`.
- Разделить список на `required`, `optional GUI`, `host-specific`; отсутствующий
  AUR-пакет должен давать понятный warning, а не ломать весь bootstrap.

### 2. Dotfiles

- Разворачивать только собственные файлы: `.zshrc`, `starship.toml`, tmux,
  Git includes, SSH config, yt-dlp и личные scripts. Mise fragment нужен лишь
  в опциональном режиме явных backend IDs.
- Не копировать дерево `.config` целиком поверх Omarchy и не менять
  `/usr/share/omarchy`.
- Пользовательские Omarchy overrides (`hypr/*.lua`, hooks, menu extensions,
  Brave policy JSON) хранить как отдельную группу.
- После `omarchy reinstall configs` повторно применять этот слой одной
  командой.

Stow уместен, но не обязателен: сам Omarchy рекомендует backup dotfiles и
упоминает Stow в [официальной главе Dotfiles](https://github.com/basecamp/omarchy/blob/v4.0.0/manual/31-dotfiles.md).
Для небольшого количества генерируемых файлов текущие shell-функции `write_*`
проще, если перед заменой чужого файла они делают backup или проверяют ownership.

### 3. Secrets

Секреты GPG и SSH действительно защищены правилами `git-crypt` в
[.gitattributes](../../../.gitattributes), а `install.sh` ожидает уже
расшифрованные файлы. Возникает bootstrap loop: приватный GPG key внутри
запертого репозитория не может сам разблокировать этот репозиторий на чистой
машине.

Нужен один внешний корень доверия:

- GPG private key на hardware token/зашифрованном носителе/в password manager;
  либо
- отдельно хранимый symmetric key от `git-crypt export-key`.

После clone последовательность: установить `git-crypt` и GnuPG → получить
внешний ключ → `git-crypt unlock [key-file]` → импортировать GPG/ownertrust и
установить SSH keys с режимами `600` → удалить временный key-file. Официальный
git-crypt описывает оба способа разблокировки и отдельно требует безопасно
передавать symmetric key: [git-crypt README](https://github.com/AGWA/git-crypt/blob/master/README.md#using-git-crypt).

### 4. Verify

Bootstrap должен завершаться read-only проверками:

```sh
getent passwd "$USER" | cut -d: -f7
zsh -lic 'command -v git gpg codex opencode; mise current'
git config --global --list --show-origin
gpg --list-secret-keys --keyid-format long
ssh -G m1max >/dev/null
xdg-settings get default-web-browser
pacman -Q brave-bin openai-codex-desktop
```

Для Codex дополнительно проверить `command -v codex`: в рекомендуемом штатном
режиме до первого запуска ожидается `~/.local/bin/codex` wrapper Omarchy; после
установки mise shim может оказаться раньше него в `PATH`.

## Альтернативы

### Standalone Home Manager поверх Omarchy

Технически можно сохранить почти весь `modules/home-manager/common.nix` и
запускать standalone Home Manager через Nix. Это даст наибольший reuse, но
вернёт второй package manager, Nix store, pinned nixpkgs и возможные конфликты
за `.config`/desktop applications. Для пользователя, которому не нужна строгая
воспроизводимость или фиксация версий, это лишняя сложность. Имеет смысл только
если ценность существующих HM modules выше желания жить в нативной модели
Omarchy.

### Chezmoi/Stow + package script

Это наиболее подходящая модель для задачи: dotfile manager отвечает за файлы,
короткий script — за packages и secrets, Omarchy — за ОС. Она даёт понятный
diff, повторный apply и почти не создаёт двух владельцев одного ресурса.

## Риски и границы parity

- Это не заменит NixOS-level декларации boot, kernel, system services и
  rollback всего host config. Omarchy snapshots откатывают плохие updates, но
  не являются декларативной моделью текущего репозитория.
- Названия AUR/Omarchy packages могут меняться. Идемпотентный bootstrap должен
  проверять наличие и сообщать gap, а не закреплять версии.
- Zsh сохранит рабочий Omarchy desktop, но stock Bash aliases/functions нужно
  портировать выборочно.
- `omarchy reinstall configs` destructive; после него нужен повторный dotfiles
  apply.
- Brave extensions/policies, SSH aliases/ProxyJump и host-specific services не
  появятся автоматически только от установки пакетов — это отдельные файлы
  конфигурации.
- В текущем `install.sh` нет полного parity с Home Manager: SSH aliases не
  генерируются, Git settings уже, а Brave не входит в package list.

## Итоговая рекомендация

Делать pilot на новой установке стабильного Quattro и реализовать отдельный
**Omarchy user bootstrap**, а не переносить NixOS как второй системный слой.
Первый минимальный milestone:

1. Zsh + dotfiles + Git/SSH/GPG/pass.
2. Штатные Omarchy wrappers для Codex/OpenCode; явный mise config оставить
   опциональным режимом, если позже понадобится текущий 24-часовой cooldown.
3. Штатные Brave/ChatGPT installers и отдельный Brave policy JSON.
4. Сокращённый package manifest из `install.sh` без KDE/GNOME, network,
   firewall, sshd, Nix и host services.
5. Повторный запуск и verify должны пройти без дополнительных изменений.

Оценка feasibility: **высокая**. Основная работа — не борьба с ограничениями
Omarchy, а аккуратное извлечение безопасного user-level подмножества из уже
существующего Arch/CachyOS bootstrap.
