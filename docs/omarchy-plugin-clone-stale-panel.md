# Omarchy shell plugins: устаревший клон ломает закрытие панели

Проблема (видели на x1carbon 2026-09-24, zenbook в том же состоянии, t14s — TBD):
бар-виджет/панель плагина открывается, но не закрывается после клика/повторного
открытия. В `journalctl --user` сыплются повторяющиеся:

```
WARN scene: .../plugins/io.github.sspaeti.timezones/Panel.qml[61:-1]:
TypeError: Cannot assign to read-only property "centerHoverRevealSuppressed"
```

## Причина

Клоны плагинов в `~/.config/omarchy/plugins/<id>/` НЕ управляются nix-config и
НЕ обновляются вместе с omarchy. После обновления omarchy (4.0.4) шелл передаёт
плагину read-only facade (`PluginBarApi`) вместо объекта Bar; старый код плагина
присваивает напрямую в свойство facade, падает с TypeError, и `close()`
умирает до `controller.hide()` — панель остаётся открытой (с keyboard grab).

## Проверка

```bash
# 1. Симптом в журнале (за текущий бут):
journalctl --user -b --no-pager | grep -c "read-only property"
journalctl --user -b --no-pager | grep "read-only property" | grep -o "plugins/[^[]*" | sort | uniq -c

# 2. Отставание всех клонов от origin (для каждого гит-клона в plugins/):
git -C ~/.config/omarchy/plugins/io.github.sspaeti.timezones fetch origin
git -C ~/.config/omarchy/plugins/io.github.sspaeti.timezones rev-list HEAD..origin/main | wc -l
```

## Исправление (на хосте, для каждого сломанного плагина)

```bash
omarchy plugin update <plugin-id> --yes
omarchy restart shell
```

Верификация (x1carbon, отработало): открыть/закрыть панель через IPC и убедиться,
что слой появляется/исчезает в `hyprctl layers` (секция overlay), а TypeError
в journal не растут. Нюансы:

- IPC-вызов требует явной адресации инстанса: `quickshell ipc --pid <pid> call
  <plugin-id> open|close` (pid из `pgrep -f "quickshell -n"`); голый
  `quickshell ipc call` и `-p /usr/share/omarchy/shell` инстанс не находят.
- `hyprctl` из ssh-сессии требует `HYPRLAND_INSTANCE_SIGNATURE` (первая папка в
  `/run/user/1000/hypr/`), `XDG_RUNTIME_DIR=/run/user/1000`,
  `WAYLAND_DISPLAY=wayland-1`.
- grep по слоям: неймспейсы называются `omarchy-*` (например,
  `omarchy-keyboard-panel`), а не по имени плагина.

## Статус на 2026-09-24

- **x1carbon**: пофикшен — клон `io.github.sspaeti.timezones` обновлён
  907a71a → 8419c2e, верифицировано через IPC + hyprctl layers.
- **zenbook**: та же болезнь — клон timezones на 9faa0be (без фикс-коммита
  ea8ff26), 9 TypeError в текущем буте. Плюс отстают от origin и другие клоны:
  `akitaonrails.ai-usagebar` (−322), `crmne.hyprmoncfg` (−30). Исправить:
  `omarchy plugin update io.github.sspaeti.timezones --yes && omarchy restart shell`.
- **t14s**: на момент фиксa был выключен; при включении проверить по
  journalctl-команде выше.

Примечание: zenbook headless-подобный хост (см. docs/zenbook-headless-power.md) —
интерактивная верификация панели на нём ограничена; обновление клона
безопасно и этого достаточно.
