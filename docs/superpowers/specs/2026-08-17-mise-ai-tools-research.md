# Mise для быстро обновляемых OpenCode и Codex

**Дата проверки:** 2026-08-17
**Статус:** исследование завершено; рекомендованная гибридная схема затем реализована в конфигурации

## Краткий вывод

`mise` имеет смысл использовать для **OpenCode CLI** и **Codex CLI**. Для них он убирает ручное обновление версии и хэшей в Nix, умеет держать несколько версий, переключать их через `PATH`/shims и обновлять одной командой. Это уже не экспериментальная комбинация: OpenCode прямо документирует `mise use -g github:anomalyco/opencode`, оба инструмента есть во встроенном registry mise, а Omarchy применяет mise для обоих CLI.

Для **OpenCode Desktop** и **ChatGPT Desktop с Codex** mise — плохая граница ответственности. Он может скачать подходящий release asset, но не заменяет установку `.desktop`-файлов, иконок, MIME/protocol handlers, FHS-зависимостей и NixOS-обёрток. Omarchy проводит ту же границу: CLI идут через mise, ChatGPT/Codex Desktop — через отдельный пакет pacman.

Реализованная схема для этого репозитория:

1. Управлять OpenCode CLI и Codex CLI через mise на Linux и macOS.
2. Явно выбрать backend, а не полагаться на изменяемый порядок shorthand registry:
   - OpenCode: `github:anomalyco/opencode`;
   - Codex: `aqua:openai/codex` (или shorthand `codex` при осознанном принятии registry indirection); полный bundle исправлен в mise 2026.7.1+.
3. Оставить OpenCode Desktop и ChatGPT Desktop системным package manager: NixOS/AUR/Homebrew в зависимости от host.
4. Обновлять CLI только явной командой `mise upgrade`; не считать `latest` автоматическим обновлением и не добавлять timer или проверку при каждом запуске.
5. Сохранить 24-часовой cooldown и полные backend IDs. Не управлять одним и тем же бинарником одновременно Nix и mise.

## Что сейчас делает репозиторий

| Компонент | Текущий источник | Состояние на 2026-08-17 |
|---|---|---|
| OpenCode CLI | mise: `github:anomalyco/opencode@latest` | Один источник на Linux и macOS; локальный [`pkgs/opencode.nix`](../../../pkgs/opencode.nix) сохранён как fallback, но больше не установлен на hosts |
| Codex CLI | mise: `aqua:openai/codex@latest` | Один источник на Linux и macOS; локальный overlay сохранён как fallback, но больше не входит в `home.packages`, а Homebrew cask `codex` удалён |
| OpenCode Desktop | system package | Nix package на NixOS, AUR package в `install.sh`, общий Homebrew cask на macOS |
| ChatGPT/Codex Desktop | system package | Nix FHS package на NixOS, AUR package в `install.sh`, общий Homebrew cask `chatgpt` на macOS |

OpenCode CLI специально собирается с `dontStrip = true`, потому что upstream binary содержит Bun payload. Переход на upstream binary через mise сохранит этот payload без участия Nix stripping — это один из случаев, где mise действительно упрощает сопровождение.

При миграции соответствующие CLI удалены из `home.packages` и Homebrew casks. `mise activate` ставит свой путь впереди системного [`PATH`](https://mise.jdx.dev/dev-tools/#path-management). Проверки после переключения: `command -v opencode`, `command -v codex`, `mise which opencode`, `mise which codex`.

### Локальная проверка на этом flake

На `x86_64-linux` проверен `mise 2026.7.17` из текущего pinned nixpkgs с полностью временными data/cache/config directories:

- registry разрешил `opencode` в `aqua:anomalyco/opencode`, а `codex` — сначала в `aqua:openai/codex` с npm fallback;
- `mise latest` вернул OpenCode `1.18.18` и Codex `0.147.0`, то есть те же версии, которые сейчас закреплены в репозитории;
- временная установка и запуск OpenCode завершились успешно;
- временная установка и запуск Codex завершились успешно, причём Aqua поставил полный `codex-package`: `bin/codex`, `bin/codex-code-mode-host`, bundled `rg`, `bwrap` и `zsh`. Текущий Nix overlay устанавливает только отдельный `codex` binary.

При одном запросе Codex remote versions сработал известный трёхсекундный timeout GitHub API; установка явно заданной версии после этого прошла успешно. Это подтверждает, что runtime не зависит от сети после установки, но Omarchy-style remote check при каждом запуске добавляет потенциальную задержку/точку отказа. Аналогичный отчёт есть в [jdx/mise discussion #11185](https://github.com/jdx/mise/discussions/11185).

## Возможности mise, существенные для задачи

### Версии, pin и lockfile

- `mise use -g TOOL` записывает глобальную конфигурацию в `~/.config/mise/config.toml`; `--pin` сохраняет разрешённую точную версию. Документация рекомендует рассмотреть lockfile вместо записи точной версии в TOML: [`mise use --pin`](https://mise.jdx.dev/cli/use.html#pin).
- `latest` в обычном config означает последнюю **установленную** подходящую версию, а не постоянную проверку remote registry. Новую remote-версию ставят `mise upgrade`/`mise install TOOL@latest`; это важное различие описано в [FAQ mise](https://mise.jdx.dev/faq.html#does-latest-mean-the-newest-remote-version).
- `mise upgrade` сохраняет диапазон версии; `--bump` меняет диапазон/версию в TOML. Есть `--dry-run`, `--interactive` и `--minimum-release-age`: [CLI reference](https://mise.jdx.dev/cli/upgrade.html).
- При включённом [`lockfile`](https://mise.jdx.dev/configuration/settings.html#lockfile) loose-выражение вроде `latest` может сосуществовать с зафиксированной разрешённой версией, URL и checksum в `mise.lock`. Для global config lockfile создаётся только `mise lock --global`.
- Значение `minimum_release_age` по умолчанию сейчас `24h`; оно уменьшает риск немедленно подобрать только что опубликованный проблемный release: [settings](https://mise.jdx.dev/configuration/settings.html#minimum-release-age). Для этих агентов разумно начать с 24 часов, а не с нуля.

Иными словами, mise предлагает два разных режима:

| Режим | Конфигурация | Поведение |
|---|---|---|
| Быстро меняющийся | `latest`, без lock или с регулярно обновляемым lock | `mise upgrade` подбирает новую версию; можно запускать таймером |
| Воспроизводимый | точная версия или committed `mise.lock` | обновление становится явным изменением, удобным для review/rollback |

Встроенного фонового updater для dev tools нет. «Автообновление» получается только если явно вызывать `mise upgrade` по расписанию либо, как Omarchy, делать `mise use -g` при каждом запуске инструмента. Автоматическая установка missing versions (`auto_install`) — другая функция и не означает автоматическое обновление уже установленного `latest`: [Dev Tools / Auto-Install](https://mise.jdx.dev/dev-tools/#auto-install-mechanisms).

### PATH activation и shims

Для интерактивной shell mise рекомендует `mise activate`; для IDE, scripts и неинтерактивных сессий — shims: [Getting Started](https://mise.jdx.dev/getting-started.html#_3-activate-mise-optional). При установке/обновлении/удалении mise сам выполняет reshim; отдельный `mise reshim` обычно не нужен: [Shims](https://mise.jdx.dev/dev-tools/shims.html#mise-reshim).

Для этого flake оптимален гибрид:

- `mise activate zsh` в интерактивной shell;
- `~/.local/share/mise/shims` в session/systemd/IDE `PATH`, если `codex` и `opencode` должны находиться вне shell;
- проверка порядка `PATH`, потому что сейчас те же имена поставляет Nix.

### Registry freshness

Mise по умолчанию использует протестированные snapshots собственного и Aqua registry из конкретного release mise. [`registry_floating=true`](https://mise.jdx.dev/registry.html#floating-registries) позволяет получать свежие registry entries, но сами docs предпочитают обновлять mise. Следовательно, mise из pinned nixpkgs тоже нужно держать достаточно свежим: новый upstream layout assets иногда требует новой версии asset matcher/registry recipe.

### Home Manager: mutable global config

В pinned Home Manager этого flake уже есть `programs.mise.enableMutableConfig`. При обычном `programs.mise.globalConfig` файл `~/.config/mise/config.toml` является symlink в Nix store, поэтому Omarchy-подобные `mise use --global` и команды, обновляющие global config, не смогут его записать.

При `enableMutableConfig = true` модуль:

- оставляет `~/.config/mise/config.toml` обычным mutable user-файлом и создаёт его, если он отсутствует;
- пишет декларативную часть Home Manager в `~/.config/mise/conf.d/50-home-manager.toml`;
- отдельно предупреждает держать mutable config и `globalConfig` непересекающимися.

Источник: [`modules/programs/mise.nix` Home Manager на pinned commit](https://github.com/nix-community/home-manager/blob/4ad9aaae70c9aaab504127f926c0fa9cfbc2b365/modules/programs/mise.nix).

Это даёт подходящий hybrid ownership:

- Nix/Home Manager владеет бинарником mise, shell integration, shims/session `PATH` и стабильными settings (`minimum_release_age`, backend/security policy);
- mutable `config.toml` владеет списком/версиями часто обновляемых CLI и может меняться `mise use -g`/`mise up`;
- Nix продолжает владеть desktop packages и их system integration.

Если нужен полностью reviewed/flake-like режим, `enableMutableConfig` не обязателен: можно декларативно держать `[tools]` в `globalConfig`, не запускать mutating `mise use -g`, а обновлять только lock/version через контролируемое изменение репозитория. Нельзя одновременно положить один и тот же `[tools]` key в mutable config и Home Manager fragment.

## Backends

| Backend | OpenCode CLI | Codex CLI | Оценка |
|---|---|---|---|
| `github:` | Официально документирован `github:anomalyco/opencode` | Возможен `github:openai/codex`, но release содержит много разных binaries/assets и требует точного `matching`/`asset_pattern` | Лучший прямой путь для OpenCode; для Codex без явного asset filter слишком неоднозначен |
| `aqua:` | В registry mise shorthand `opencode` → `aqua:anomalyco/opencode` | Первый backend shorthand `codex` → `aqua:openai/codex` | Хорошая platform-aware установка; зависит от актуальности Aqua recipe |
| `npm:` | `npm:opencode-ai` возможен и upstream поддерживает npm, но package требует postinstall | `npm:@openai/codex` соответствует первому официальному способу установки OpenAI, но launcher требует Node runtime | Рабочий fallback; более широкий dependency/supply-chain surface, чем Aqua native bundle |
| `ubi:` | Технически возможен | Технически возможен с filters | Не начинать новый config: backend [deprecated в пользу `github:`](https://mise.jdx.dev/dev-tools/backends/ubi.html) |
| `asdf:` | Не нужен | Не нужен | Не использовать: mise считает asdf plugins [legacy и менее безопасными](https://mise.jdx.dev/dev-tools/backends/asdf.html) |

Mise registry на дату проверки содержит:

- [`opencode.toml`](https://github.com/jdx/mise/blob/main/registry/opencode.toml): `aqua:anomalyco/opencode`, binary `opencode`;
- [`codex.toml`](https://github.com/jdx/mise/blob/main/registry/codex.toml): сначала `aqua:openai/codex`, затем `npm:@openai/codex`; binaries `codex` и `codex-code-mode-host`.

Shorthand удобен, но его backend может поменяться вместе с mise registry. Для Nix-конфигурации, где важен предсказуемый источник, лучше записывать полное имя backend.

### `github:`

[`github` backend](https://mise.jdx.dev/dev-tools/backends/github.html) скачивает GitHub Release assets, выбирает OS/architecture/libc/archive и поддерживает `matching`, `matching_regex`, `asset_pattern`, checksums, lockfile и SLSA provenance verification. Это больше всего похоже на текущие `fetchzip`/`fetchurl`, но version discovery и обновление выполняет mise.

Для OpenCode выбор подтверждён самим upstream:

```sh
mise use -g github:anomalyco/opencode
```

Источник: [официальная инструкция OpenCode](https://opencode.ai/docs/#install).

У одного OpenCode release лежат и CLI, и desktop assets. На `v1.18.18` опубликованы CLI tarballs, Linux AppImage/DEB/RPM и macOS/Windows desktop installers: [официальный release](https://github.com/anomalyco/opencode/releases/tag/v1.18.18). Документированная команда без filter предназначена для CLI. Если вручную нацелить backend на `opencode-desktop-*`, mise скачает другой asset, но это не превратит его в корректно установленное desktop-приложение.

Codex release содержит множество близко названных binaries (`codex`, `codex-app-server`, `codex-code-mode-host`, platform packages и служебные helpers). Поэтому generic autodetection без строгого filter несёт больше риска выбрать неполный asset. В `rust-v0.147.0` есть полноценные `codex-package-<target>.tar.gz`, отдельные binaries, npm tarballs, checksums и sigstore-файлы: [официальный release](https://github.com/openai/codex/releases/tag/rust-v0.147.0).

### `aqua:`

Mise компилирует snapshot официального Aqua registry внутрь бинарника; отдельный aqua CLI не нужен. Backend умеет platform templating и несколько способов verification: [Aqua backend](https://mise.jdx.dev/dev-tools/backends/aqua.html).

Текущие recipes:

- [OpenCode](https://github.com/aquaproj/aqua-registry/blob/main/pkgs/anomalyco/opencode/registry.yaml) знает исторические изменения zip/tar.gz и текущие Linux/macOS/Windows assets;
- [Codex](https://github.com/aquaproj/aqua-registry/blob/main/pkgs/openai/codex/registry.yaml) знает prefix `rust-`, старые `.zst` binaries и новые `codex-package-<target>.tar.gz`.

Важная исправленная история Codex: Aqua recipe перешёл с отдельного `codex-*` binary на официальный полный `codex-package-*` archive, содержащий `bin/codex-code-mode-host` и остальную package layout. После этого mise снова сделал Aqua первым backend; fix включён начиная с mise `2026.7.1`: [jdx/mise PR #10922](https://github.com/jdx/mise/pull/10922). Поэтому реализация требует mise не старее `2026.7.1` и безопасно использует Aqua.

### `npm:`

OpenCode поддерживает `npm install -g opencode-ai`, а OpenAI — `npm install -g @openai/codex`: [OpenCode install docs](https://opencode.ai/docs/#install), [OpenAI Codex repository](https://github.com/openai/codex#installing-and-running-codex-cli).

Современный [`npm` backend mise](https://mise.jdx.dev/dev-tools/backends/npm.html) по умолчанию сам запрашивает npm registry и использует embedded `aube`; установленный Node/npm не обязателен для самого installer, но mise **не устанавливает Node автоматически**, если package требует его в runtime или lifecycle scripts. Можно принудительно использовать npm/pnpm/bun. Dependency lifecycle scripts в default aube deny-by-default, а для npm mise по умолчанию передаёт `--ignore-scripts=true`.

Это влияет на выбор:

- npm package OpenCode формируется как wrapper вокруг platform packages и использует `postinstall`: [официальный publish script](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/script/publish.ts). При shell-out через npm default `--ignore-scripts=true` потребует явного разрешения;
- npm package Codex — JavaScript launcher с platform-specific optional dependencies: [официальный build script](https://github.com/openai/codex/blob/main/codex-cli/scripts/build_npm_package.py). Ему нужен Node runtime, которого native Aqua bundle не требует.

Codex npm package использует platform-specific optional dependencies. Это штатная first-party layout, но её нужно включить в smoke test: после установки проверить не только `codex --version`, но и отсутствие сообщения `Missing optional dependency`, `codex doctor` и запуск реальной сессии. Преимущество npm-варианта — он следует официальному install path; недостатки — Node runtime и больше moving parts, чем Aqua native package.

## Отдельно по продуктам

### OpenCode CLI — да

Рекомендуемый источник:

```toml
[tools]
"github:anomalyco/opencode" = "latest"
```

Почему:

- команда прямо указана upstream;
- release assets уже совпадают с теми, которые вручную описывает `pkgs/opencode.nix`;
- upstream binary self-contained;
- mise убирает четыре architecture-specific hashes из регулярного bump процесса.

Альтернатива для следования Omarchy/registry: `opencode = "latest"`, сейчас это Aqua. Для максимальной воспроизводимости добавить global lockfile или записывать точную версию.

### Codex CLI — да

Первый кандидат при mise `2026.7.1+`:

```toml
[tools]
"aqua:openai/codex" = "latest"
```

Именно этот backend сейчас предпочитает mise и использует Omarchy через shorthand `codex`; исправленный Aqua recipe устанавливает полный официальный `codex-package-*` archive. `npm:@openai/codex` остаётся first-party fallback, но требует mise-managed/system Node и проверки optional dependencies. Голый `github:openai/codex` хуже обоих вариантов из-за неоднозначного набора release assets.

Важно: OpenAI официально поддерживает Codex CLI на Linux и macOS, а npm и GitHub Releases перечислены как install paths: [официальный repository](https://github.com/openai/codex). Codex CLI не равен desktop app; наличие `codex-app-server` в CLI release также не является GUI installer.

При централизованном обновлении через mise стоит выключить собственные проверки/updaters обоих CLI:

- OpenCode: `autoupdate: false`. Его upgrade code прекращает работу при этом флаге, а для нераспознанного метода установки (`unknown`, что ожидаемо для mise) всё равно не выполняет upgrade: [официальный `upgrade.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/cli/upgrade.ts), [config docs](https://opencode.ai/docs/config/);
- Codex: `check_for_update_on_startup = false`; комментарий upstream прямо рекомендует это при centrally managed updates: [официальный config source](https://github.com/openai/codex/blob/main/codex-rs/config/src/config_toml.rs). Mise/Aqua binary определяется как `Other`, для него update action отсутствует; npm install context, напротив, может предложить обычный `npm install -g`, обходя ownership mise: [install context](https://github.com/openai/codex/blob/main/codex-rs/install-context/src/lib.rs), [update action](https://github.com/openai/codex/blob/main/codex-rs/tui/src/update_action.rs).

### OpenCode Desktop — оставить в Nix

OpenCode выпускает AppImage, DEB и RPM. Его desktop package на Linux должен установить launcher, icons и protocol scheme; upstream electron-builder config явно задаёт Linux desktop metadata и форматы: [`electron-builder.config.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/desktop/electron-builder.config.ts).

У packaged production app включён `electron-updater`, который проверяет GitHub, скачивает update и вызывает `quitAndInstall`: [`updater.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/desktop/src/main/updater.ts), [`constants.ts`](https://github.com/anomalyco/opencode/blob/dev/packages/desktop/src/main/constants.ts). В Nix store package immutable, поэтому на встроенное обновление нельзя полагаться: обёрнутый AppImage должен обновляться сменой Nix derivation. Mise, нацеленный на AppImage, не решает эту проблему и теряет текущую Nix desktop integration.

Текущий локальный package отстаёт от CLI (`1.14.50` против `1.18.18`), что скорее аргумент за автоматизацию Nix bump, а не за перенос GUI в mise.

### Codex Desktop / ChatGPT Desktop — оставить в Nix/system package

На дату проверки Codex desktop experience входит в новый ChatGPT Desktop: [официальное объявление OpenAI](https://openai.com/index/chatgpt-for-your-most-ambitious-work/) и [migration help](https://help.openai.com/en/articles/20001276/). Актуальная публичная [download page](https://chatgpt.com/download/) уже предлагает **Download for Linux**.

Локальный Nix package использует официальный OpenAI Linux DEB endpoint. Mise registry `codex` всё равно относится к CLI и этого DEB не знает; GitHub Releases `openai/codex` также публикуют CLI package, а не Linux Electron desktop installer.

Даже при добавлении произвольного URL в mise остались бы FHS dependencies, Wayland flags, `.desktop`/icon installation и конфликт встроенного updater с immutable state. Нынешний `buildFHSEnv` решает всё это явно, поэтому Nix — правильный слой.

## Как это делает официальный Omarchy

Проверен default branch `quattro` официального repository на commit [`30f7a060`](https://github.com/basecamp/omarchy/commit/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec) от 2026-08-16.

### CLI: ленивые mise wrappers

Omarchy не хранит единый committed `mise.toml` со всеми AI tools. Installer вызывает [`omarchy-mise-install`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/install/user/mise.sh) для `codex`, `opencode`, `claude`, `gemini`, `copilot`, `crush`, `pi` и других. Helper создаёт маленький wrapper в `~/.local/bin/<command>`:

```sh
export MISE_MINIMUM_RELEASE_AGE=0
mise use -g --quiet "$package" || exit 1
exec mise x "$package" -- "$bin" "$@"
```

Источник: [`bin/omarchy-mise-install`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/bin/omarchy-mise-install).

Следствия:

- инструмент не скачивается до первого запуска;
- каждый запуск делает remote resolution/install check через `mise use -g`;
- Omarchy использует shorthand `codex` и `opencode`, поэтому фактический backend задаёт bundled/floating mise registry;
- cooldown mise намеренно выключен (`MISE_MINIMUM_RELEASE_AGE=0`) ради самых свежих releases;
- команда выполняется через `mise x`, а wrapper в `~/.local/bin` остаётся стабильной точкой входа.

Manual прямо описывает эти AI agents как lazy-loaded mise stubs: [`manual/17-ai.md`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/manual/17-ai.md).

### Обновления

Общий [`omarchy update`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/bin/omarchy-update) последовательно обновляет system packages, AUR, затем mise tools. Шаг [`omarchy-update-mise`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/bin/omarchy-update-mise) делает:

```sh
MISE_MINIMUM_RELEASE_AGE=0 mise up
```

Также есть alias `mup` с той же командой. То есть Omarchy совмещает два механизма: upgrade check при запуске wrapper и массовый update во время system update.

### PATH и mise как системный компонент

- Сам `mise` входит в базовый pacman package list: [`install/omarchy-base.packages`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/install/omarchy-base.packages).
- Interactive bash использует `mise activate`; UWSM/session и SSH получают shims path: [`default/bash/init`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/default/bash/init), [`default/uwsm/env.d/10-omarchy`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/default/uwsm/env.d/10-omarchy), [`install/config/ssh-command-path.sh`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/install/config/ssh-command-path.sh).
- Node устанавливается отдельно через mise, включая offline tarball для ISO setup: [`install/user/mise-work.sh`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/install/user/mise-work.sh).

### Граница с pacman/AUR и desktop apps

Omarchy использует mise для user-scoped development runtimes и быстро меняющихся CLI. Системные библиотеки и GUI остаются pacman/AUR packages. Особенно показателен ChatGPT/Codex Desktop:

- menu запускает [`omarchy-install-ai-chatgpt`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/bin/omarchy-install-ai-chatgpt);
- installer вызывает `omarchy-pkg-add openai-codex-desktop` и затем `/usr/bin/chatgpt`;
- `omarchy-pkg-add` использует pacman: [`bin/omarchy-pkg-add`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/bin/omarchy-pkg-add);
- package приходит из настроенного Omarchy repository `https://pkgs.omarchy.org/...`: [`pacman-stable.conf`](https://github.com/basecamp/omarchy/blob/30f7a06090dc20dd1a4a8d0c99bfb8e2370df2ec/default/pacman/pacman-stable.conf).

OpenCode Desktop в текущем Omarchy AI menu отдельно не предлагается; `opencode` там означает CLI. Это подтверждает, что перенос CLI в mise не подразумевает перенос одноимённого desktop artifact.

### Что стоит и не стоит перенимать из Omarchy

Стоит:

- ясную границу «CLI → mise, GUI/system integration → system package manager»;
- глобальный update step для всех mise tools;
- shims path для неинтерактивных запусков;

Не стоит автоматически копировать:

- `MISE_MINIMUM_RELEASE_AGE=0`: для личного Nix fleet 24-часовая задержка даёт полезное окно против bad release;
- mutable global config без lockfile: это соответствует rolling Arch, но слабее воспроизводимости flake;
- shorthand без явного backend: удобен, но источник может измениться вместе с registry;
- проверку/обновление при каждом запуске, если важны быстрый startup и предсказуемая работа offline.

## Рекомендационная матрица

| Цель | Mise? | Backend/слой | Pin/update policy | Итог |
|---|---:|---|---|---|
| OpenCode CLI | Да | `github:anomalyco/opencode` | `latest` + только явный `mise upgrade` | Реализовано |
| Codex CLI | Да | `aqua:openai/codex` на mise 2026.7.1+; npm fallback | `latest` + 24h cooldown + только явный `mise upgrade` | Реализовано |
| OpenCode Desktop | Нет | текущий Nix `appimageTools` package | automated Nix bump/hash PR | Оставить в Nix |
| ChatGPT/Codex Desktop Linux | Нет | текущий Nix FHS package из официального Linux DEB | controlled Nix bump/hash; не полагаться на in-app update | Оставить в Nix |
| ChatGPT/Codex Desktop macOS | Нет | официальный app/Homebrew cask `chatgpt` | Homebrew/nix-darwin update | Mise не добавляет ценности |
| Сам mise | Да, как Nix/system package | nixpkgs | регулярно обновлять; при необходимости floating registry | Не self-update из Nix package |

## Реализация и проверка

Desktop packages остались у системных package managers, а CLI переведены на mise:

1. Home Manager устанавливает mise на Linux и macOS; `install.sh` устанавливает его на Arch/CachyOS.
2. Shell activation и shims path покрывают интерактивные и неинтерактивные запуски.
3. Декларативный global config содержит:

   ```toml
   [settings]
   minimum_release_age = "24h"

   [tools]
   "github:anomalyco/opencode" = "latest"
   "aqua:openai/codex" = "latest"
   ```

4. Для проверки после применения используются:

   ```sh
   mise install
   mise which opencode
   mise which codex
   opencode --version
   codex --version
   codex doctor
   mise upgrade --dry-run
   ```

5. Upstream-owned update paths отключены: OpenCode через config и `OPENCODE_DISABLE_AUTOUPDATE`, Codex через `check_for_update_on_startup = false` с сохранением остальных mutable настроек.
6. Единственный выбранный update workflow — ручной запуск `mise upgrade`. Timer, lazy wrappers и remote check при старте не используются.
7. OpenCode/Codex CLI удалены из Nix/Homebrew host packages. Desktop derivations и casks остаются системными.

## Риски и критерии отката

- **Два владельца одного binary:** Nix CLI удалены из host packages; источник проверяется через `command -v` и `mise which`.
- **Mutable state вне Nix:** installs находятся в `~/.local/share/mise`; нужны backup/cleanup expectations, а rollback — возврат Nix package.
- **Registry/backend drift:** использовать полные backend IDs и/или lockfile.
- **Bad fresh release:** сохранить `minimum_release_age = "24h"` или больше.
- **GitHub layout изменился:** обновить mise/registry; прямой Nix derivation остаётся fallback.
- **Старый mise/Aqua recipe Codex неполон:** требовать mise 2026.7.1+; откатиться на текущий Nix overlay или npm fallback.
- **GUI updater конфликтует с Nix store:** игнорировать/отключить in-app update и обновлять derivation; не переносить GUI в mise.

Критерии успешной эксплуатации: один однозначный binary source, одинаковая работа в интерактивной shell и GUI/IDE-launched процессах, успешные реальные sessions, предсказуемое ручное обновление и быстрый rollback на Nix.
