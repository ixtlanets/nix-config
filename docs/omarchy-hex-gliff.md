# Hex on zenbook → Gliff → omarchy-vm

Microphone and Hex run on the client; the guest receives pasted text. No guest microphone or dictation engine is needed.

## Two independent failure modes

1. Gliff inhibits compositor shortcuts. The zenbook Right Alt Hex binding needs `dont_inhibit = true`, alongside its existing `ignore_mods` and `transparent` options.
2. Hex 3.3.0's `wtype` paste creates a temporary virtual keyboard layout. Gliff can forward it as a bare `v`, losing Control. For the exact Hex paste call and the verified focused `omarchy-vm — Gliff` window, use native Hyprland Control_L down → Ctrl+V down → 50 ms timer → V up → Control_L up instead.

The adapter checks the window class, title, address, PID, actual `/usr/bin/gliff` executable and exact `omarchy-vm` command argument. It rechecks focus inside the compositor before keydown. It never reads or logs the clipboard. Other calls/windows execute `/usr/bin/wtype` unchanged. If native injection fails, it does not retry or fall back and risk a double paste.

## Managed client installation

Sources:

- [zenbook binding](../dotfiles/omarchy/hypr/hosts/zenbook.lua)
- [paste adapter](../scripts/hex-gliff-wtype.py)
- [Hex service wrapper](../scripts/hex-gliff-service.sh)
- [systemd override](../dotfiles/omarchy/systemd/hex.service.d/gliff-paste.conf)

The [Omarchy user installer](../scripts/omarchy-apply-user.sh) installs these only on zenbook when Hex is installed. It does not restart a potentially active recording. After applying, restart Hex when idle:

```sh
systemctl --user restart hex.service
```

For a targeted install from the repository root, without applying unrelated desktop settings:

```sh
install -Dm0755 scripts/hex-gliff-wtype.py "$HOME/.local/lib/hex-gliff/bin/wtype"
install -Dm0755 scripts/hex-gliff-service.sh "$HOME/.local/lib/hex-gliff/service"
install -Dm0644 dotfiles/omarchy/systemd/hex.service.d/gliff-paste.conf \
  "$HOME/.config/systemd/user/hex.service.d/gliff-paste.conf"
systemctl --user daemon-reload
# Only when Hex is idle:
systemctl --user restart hex.service
```

The wrapper prepends its private adapter directory to Hex's inherited PATH and sets `HEX_GLIFF_PASTE=1`. The original packaged service remains enabled, preserving its notification/restart/session behavior. This survives login/reboot and does not depend on a special Gliff launcher. Connect using the `omarchy-vm` SSH alias; another alias/title deliberately falls outside this workaround. Terminal applications in the guest retain their own paste shortcut policy.

## Guest dictation disabled (2026-11-08)

On `omarchy-vm`, the previous `superwhisper` backend selection was backed up to `~/.config/omarchy/defaults/dictation.pre-client-hex`; the active selection file is empty. Thus Omarchy loads neither guest recording bindings nor the Superwhisper shortcut bridge. `superwhisper.service` is masked and stopped. The package/models are retained; VNC and other remote access services are untouched.

To restore the previous guest dictation setup, on the guest:

```sh
cp ~/.config/omarchy/defaults/dictation.pre-client-hex ~/.config/omarchy/defaults/dictation
systemctl --user unmask superwhisper.service
systemctl --user enable --now superwhisper.service
hyprctl reload
hyprctl configerrors
```

## Validation and rollback

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_hex_gliff_wtype.py -v
bash tests/omarchy-hex-gliff.sh
```

Live validation used an isolated guest terminal receiver (Ctrl+V explicitly configured as its paste shortcut, no interactive shell). The original exact Hex `wtype` call produced one byte, `v`; native injection and the installed adapter delivered the full 78-byte ASCII/Russian/multiline sentinel, accounting for normal terminal LF→CR conversion. Native injection passed three consecutive trials. After restarting Hex with the persistent override, the user confirmed real Right Alt dictation inserts the complete text in the VM. The live Hex process was also checked for the adapter PATH/flag and an Enabled shortcut listener. A full client reboot was not performed.

To disable the client adapter without deleting it, on zenbook:

```sh
mv ~/.config/systemd/user/hex.service.d/gliff-paste.conf \
  ~/.config/systemd/user/hex.service.d/gliff-paste.conf.disabled
systemctl --user daemon-reload
# Only when idle:
systemctl --user restart hex.service
```

Remove `dont_inhibit` from the Right Alt binding only if local Hex should no longer work while Gliff captures shortcuts. Reload Hyprland and check `hyprctl configerrors` after Lua changes. Future Hex versions with different `wtype` arguments safely bypass the exact-match adapter and need a new regression test before expanding its signature. macOS Gliff has a separate experimental explicit-paste implementation; it was not modified here.
