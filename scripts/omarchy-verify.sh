#!/usr/bin/env bash
set -euo pipefail

expected_host="${OMARCHY_EXPECTED_HOST:-x1carbon}"
expected_syncthing_id="ACDNQPU-AYZTZJD-43ZO52W-DJQNMLQ-PZWOHHQ-M7LCWID-7WUGJ2U-DJJ4RQS"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd -- "$script_dir/.." && pwd)"

fail() {
  printf '[omarchy:verify] FAIL: %s\n' "$*" >&2
  exit 1
}

[[ "$(hostname -s)" == "$expected_host" ]] || fail "unexpected hostname"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || fail "host is not Omarchy"
[[ "$(getent passwd "$USER" | cut -d: -f7)" == /usr/bin/bash ]] ||
  fail "login shell must remain Bash"

for command_name in git gpg zsh pass direnv mise codex opencode omarchy; do
  command -v "$command_name" >/dev/null 2>&1 || fail "$command_name is missing"
done

if systemctl cat vless-sing-box.service >/dev/null 2>&1; then
  command -v sing-box >/dev/null 2>&1 || fail "sing-box is missing"
  command -v vless >/dev/null 2>&1 || fail "vless helper is missing"
  [[ -f /etc/sing-box/vless.json ]] || fail "VLESS config is missing"
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
    visual-studio-code-bin; do
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

[[ "$(systemctl --user is-active syncthing.service)" == active ]] ||
  fail "Syncthing user service inactive"
syncthing_id="$(syncthing cli show system | jq -r '.myID // .myId // ""')"
[[ "$syncthing_id" == "$expected_syncthing_id" ]] || fail "Syncthing identity mismatch"
bash "$script_dir/omarchy-configure-syncthing.sh" --check

if command -v tailscale >/dev/null 2>&1; then
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
  [[ "$(hyprctl getoption input:kb_layout -j | jq -r '.str')" == us,ru ]] ||
    fail "Hyprland keyboard layouts mismatch"
  [[ "$(hyprctl getoption input:kb_options -j | jq -r '.str')" == grp:win_space_toggle ]] ||
    fail "Hyprland keyboard switch mismatch"
fi

OMARCHY_PATH="${OMARCHY_PATH:-/usr/share/omarchy}" omarchy channel current >/dev/null
printf '[omarchy:verify] PASS\n'
