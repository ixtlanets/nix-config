#!/usr/bin/env bash
set -euo pipefail

expected_host="${OMARCHY_EXPECTED_HOST:-x1carbon}"
declare -A syncthing_ids=(
  [x1carbon]="ACDNQPU-AYZTZJD-43ZO52W-DJQNMLQ-PZWOHHQ-M7LCWID-7WUGJ2U-DJJ4RQS"
  [zenbook]="H5LDAHA-HZQTPI6-S75ZBJ3-LZUFTBM-FW55GVP-DUKYHBB-G73AHIJ-CCCNNQ7"
)
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd -- "$script_dir/.." && pwd)"
tmux_plugins_dir="${XDG_CONFIG_HOME:-$HOME/.config}/tmux/plugins"

fail() {
  printf '[omarchy:verify] FAIL: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '[omarchy:verify] WARNING: %s\n' "$*" >&2
}

[[ "$(hostname -s)" == "$expected_host" ]] || fail "unexpected hostname"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || fail "host is not Omarchy"
[[ "$(getent passwd "$USER" | cut -d: -f7)" == /usr/bin/bash ]] ||
  fail "login shell must remain Bash"

for command_name in brightnessctl git gpg zsh pass direnv mise codex opencode omarchy python tat tmux wl-copy wl-paste yp yt yt-dlp; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is missing"
done
for package_name in python-curl_cffi python-secretstorage; do
  pacman -Q "$package_name" >/dev/null 2>&1 || fail "$package_name package is missing"
done
if [[ "$expected_host" == zenbook ]]; then
  [[ -f /usr/lib/dri/iHD_drv_video.so ]] || fail "Intel iHD VA-API driver is missing"
fi
python -c 'import curl_cffi, secretstorage' >/dev/null 2>&1 ||
  fail "yt-dlp Python dependencies could not be imported"
yt-dlp --ignore-config --list-impersonate-targets 2>/dev/null | grep -Fq curl_cffi ||
  fail "yt-dlp curl_cffi impersonation targets are unavailable"
command -v urlview >/dev/null 2>&1 || warn "urlview is missing; tmux-urlview is unavailable"

if systemctl cat vless-sing-box.service >/dev/null 2>&1; then
  command -v sing-box >/dev/null 2>&1 || fail "sing-box is missing"
  command -v vless >/dev/null 2>&1 || fail "vless helper is missing"
  [[ -f /etc/sing-box/vless.json ]] || fail "VLESS config is missing"
  [[ -r /etc/sing-box/vless-interface ]] || fail "VLESS interface metadata is missing"
  [[ -x /usr/local/libexec/vless-revert-resolved ]] ||
    fail "VLESS resolved helper is missing"
  read -r tun_interface < /etc/sing-box/vless-interface
  [[ "$tun_interface" =~ ^[A-Za-z0-9][A-Za-z0-9_.+-]*$ ]] ||
    fail "invalid VLESS TUN interface"
  ((${#tun_interface} <= 15)) || fail "VLESS TUN interface is too long"

  if systemctl is-active --quiet vless-sing-box.service &&
    systemctl is-active --quiet systemd-resolved.service; then
    [[ -e "/sys/class/net/$tun_interface" ]] || fail "VLESS TUN interface is missing"
    resolved_dns="$(resolvectl dns "$tun_interface")" || fail "could not read VLESS DNS state"
    resolved_domains="$(resolvectl domain "$tun_interface")" || fail "could not read VLESS DNS domains"
    resolved_default_route="$(resolvectl default-route "$tun_interface")" ||
      fail "could not read VLESS DNS route"
    ! grep -Eq '\):[[:space:]]+[^[:space:]]' <<< "$resolved_dns" ||
      fail "VLESS TUN must not register DNS with systemd-resolved"
    ! grep -Fq '~.' <<< "$resolved_domains" ||
      fail "VLESS TUN must not own the default DNS domain"
    ! grep -Eq ': yes$' <<< "$resolved_default_route" ||
      fail "VLESS TUN must not be the default DNS route"
  fi
fi

if [[ -f "$HOME/.local/state/nix-config-omarchy/gui-installed" ]]; then
  for package in \
    bibata-cursor-theme \
    bitwarden \
    brave-bin \
    firefox \
    openai-codex-desktop \
    t3code-bin \
    telegram-desktop \
    visual-studio-code-bin \
    voxtype-bin; do
    pacman -Q "$package" >/dev/null 2>&1 || fail "$package GUI package is missing"
  done
  [[ -f "$HOME/.local/state/nix-config-omarchy/vscode-integrated" ]] ||
    fail "VS Code integration marker is missing"
  [[ -f "$HOME/.local/state/nix-config-omarchy/chatgpt-integrated" ]] ||
    fail "ChatGPT integration marker is missing"
  [[ "$(env -u BROWSER xdg-settings get default-web-browser)" == brave-browser.desktop ]] ||
    fail "Brave is not the default browser"
  cmp -s \
    "$source_root/dotfiles/omarchy/brave/extensions.json" \
    /etc/brave/policies/managed/nik-extensions.json ||
    fail "Brave extension policy is missing"
  jq -e --slurpfile extensions "$source_root/dotfiles/omarchy/firefox/extensions.json" \
    '. as $policy | all($extensions[0] | to_entries[]; $policy.policies.ExtensionSettings[.key] == .value)' \
    /usr/lib/firefox/distribution/policies.json >/dev/null ||
    fail "Firefox extension policy is missing"
  jq -e --slurpfile base /usr/share/omarchy/default/firefox/policies.json \
    '(.policies | del(.ExtensionSettings)) == ($base[0].policies | del(.ExtensionSettings))' \
    /usr/lib/firefox/distribution/policies.json >/dev/null ||
    fail "Omarchy Firefox policy mismatch"
  [[ "$(gsettings get org.gnome.desktop.interface cursor-theme)" == "'Bibata-Original-Ice'" ]] ||
    fail "GTK cursor theme mismatch"
  [[ "$(gsettings get org.gnome.desktop.interface cursor-size)" == 24 ]] ||
    fail "GTK cursor size mismatch"
  [[ "$(systemctl --user show-environment | grep '^XCURSOR_THEME=')" == "XCURSOR_THEME=Bibata-Original-Ice" ]] ||
    fail "session cursor theme mismatch"
  [[ "$(systemctl --user show-environment | grep '^XCURSOR_SIZE=')" == "XCURSOR_SIZE=24" ]] ||
    fail "session cursor size mismatch"
fi

[[ "$(git config --global user.name)" == "Sergey Nikulin" ]] || fail "Git name mismatch"
[[ "$(git config --global user.email)" == "snikulin@gmail.com" ]] || fail "Git email mismatch"
gpg --batch --list-secret-keys --with-colons | grep -q '^sec:' || fail "GPG secret key missing"
[[ -d "$HOME/.password-store/.git" ]] || fail "password store missing"
ssh -G m1max >/dev/null || fail "SSH m1max alias invalid"
zsh -n "$HOME/.zshrc" || fail "Zsh config invalid"
cmp -s "$source_root/dotfiles/omarchy/hypr/bindings.lua" "$HOME/.config/hypr/bindings.lua" ||
  fail "Hyprland bindings mismatch"
cmp -s "$source_root/dotfiles/omarchy/hypr/input.lua" "$HOME/.config/hypr/input.lua" ||
  fail "Hyprland input config mismatch"
cmp -s "$source_root/dotfiles/omarchy/hypr/looknfeel.lua" "$HOME/.config/hypr/looknfeel.lua" ||
  fail "Hyprland look and feel config mismatch"
cmp -s "$source_root/dotfiles/omarchy/hypr/hosts/$expected_host.lua" "$HOME/.config/hypr/host.lua" ||
  fail "Hyprland host config mismatch"
cmp -s "$source_root/dotfiles/omarchy/shell.json" "$HOME/.config/omarchy/shell.json" ||
  fail "Omarchy shell config mismatch"
cmp -s "$source_root/dotfiles/omarchy/voxtype/config.toml" "$HOME/.config/voxtype/config.toml" ||
  fail "Voxtype config mismatch"
cmp -s \
  "$source_root/dotfiles/omarchy/yt-dlp/config" \
  "${XDG_CONFIG_HOME:-$HOME/.config}/yt-dlp/config" ||
  fail "yt-dlp config mismatch"
cmp -s \
  "$source_root/dotfiles/omarchy/tmux/tmux.conf" \
  "${XDG_CONFIG_HOME:-$HOME/.config}/tmux/tmux.conf" ||
  fail "tmux config mismatch"
[[ -x "${XDG_CONFIG_HOME:-$HOME/.config}/tmux/plugins/tpm/tpm" ]] ||
  fail "tmux plugin manager is missing"
for plugin in tmux-sensible tmux-pain-control tmux-urlview tmux-prefix-highlight tmux; do
  [[ -d "$tmux_plugins_dir/$plugin/.git" ]] || fail "tmux plugin $plugin is missing"
done
for helper in kbd-backlight tat yp yt; do
  cmp -s "$source_root/dotfiles/omarchy/bin/$helper" "$HOME/.local/bin/$helper" ||
    fail "$helper helper mismatch"
  [[ -x "$HOME/.local/bin/$helper" ]] || fail "$helper helper is not executable"
done
if command -v voxtype >/dev/null 2>&1; then
  [[ "$(voxtype setup onnx --status 2>&1)" == *'Backend: ONNX'* ]] ||
    fail "Voxtype ONNX backend is not active"
  [[ -f "$HOME/.local/share/voxtype/models/parakeet-tdt-0.6b-v3/encoder-model.onnx.data" ]] ||
    fail "Voxtype Parakeet model is missing"
  [[ "$(systemctl --user is-active voxtype.service)" == active ]] ||
    fail "Voxtype user service inactive"
fi
for plugin_id in io.github.sspaeti.timezones io.github.snikulin.omaquote; do
  [[ -e "$HOME/.config/omarchy/plugins/$plugin_id" ]] ||
    fail "Omarchy plugin $plugin_id is missing"
done

if [[ -n "${syncthing_ids[$expected_host]:-}" ]]; then
  [[ "$(systemctl --user is-active syncthing.service)" == active ]] ||
    fail "Syncthing user service inactive"
  syncthing_id="$(syncthing cli show system | jq -r '.myID // .myId // ""')"
  [[ "$syncthing_id" == "${syncthing_ids[$expected_host]}" ]] || fail "Syncthing identity mismatch"
  bash "$script_dir/omarchy-configure-syncthing.sh" --check
fi

if command -v tailscale >/dev/null 2>&1 && [[ "${OMARCHY_SKIP_TAILSCALE:-false}" != true ]]; then
  [[ "$(tailscale status --json | jq -r '.BackendState')" == Running ]] ||
    fail "Tailscale is not connected"
  tailscale_dns="$(tailscale status --json | jq -r '.Self.DNSName')"
  [[ "${tailscale_dns%%.*}" == "$expected_host" ]] || fail "Tailscale DNS name mismatch"
fi

while IFS= read -r variable; do
  export "${variable?}"
done < <(systemctl --user show-environment | grep -E '^(HYPRLAND_INSTANCE_SIGNATURE|XDG_RUNTIME_DIR|WAYLAND_DISPLAY)=')
if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
  hyprctl reload >/dev/null
  [[ -z "$(hyprctl configerrors)" ]] || fail "Hyprland configuration errors"
  if [[ "$expected_host" == zenbook ]]; then
    session_environment="$(systemctl --user show-environment)"
    grep -Fxq 'LIBVA_DRIVER_NAME=iHD' <<< "$session_environment" ||
      fail "session VA-API driver is not Intel iHD"
    grep -Fxq '__GLX_VENDOR_LIBRARY_NAME=mesa' <<< "$session_environment" ||
      fail "session GLX vendor is not Mesa"
  fi
  [[ "$(hyprctl getoption input:kb_layout -j | jq -r '.str')" == us,ru ]] ||
    fail "Hyprland keyboard layouts mismatch"
  [[ "$(hyprctl getoption input:kb_options -j | jq -r '.str')" == grp:win_space_toggle ]] ||
    fail "Hyprland keyboard switch mismatch"
fi

OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}" omarchy channel current >/dev/null
printf '[omarchy:verify] PASS\n'
