#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
manifest="$source_root/omarchy/packages/gui.txt"
brave_policy="$source_root/dotfiles/omarchy/brave/extensions.json"
firefox_extensions="$source_root/dotfiles/omarchy/firefox/extensions.json"
firefox_policy="/usr/lib/firefox/distribution/policies.json"
omarchy_firefox_policy="${OMARCHY_PATH:-/usr/share/omarchy}/default/firefox/policies.json"
state_dir="$HOME/.local/state/nix-config-omarchy"
marker="$state_dir/gui-installed"
vscode_marker="$state_dir/vscode-integrated"
chatgpt_marker="$state_dir/chatgpt-integrated"
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT

log() {
  printf '[omarchy:gui] %s\n' "$*"
}

die() {
  printf '[omarchy:gui] ERROR: %s\n' "$*" >&2
  exit 1
}

package_installed() {
  pacman -Q "$1" >/dev/null 2>&1
}

[[ "$(hostname -s)" == x1carbon ]] || die "unexpected hostname"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"
command -v omarchy >/dev/null 2>&1 || die "omarchy command is missing"
[[ -f "$manifest" ]] || die "GUI package manifest missing"
jq empty "$brave_policy" || die "invalid Brave policy JSON"
jq empty "$firefox_extensions" || die "invalid Firefox extension JSON"

while IFS= read -r variable; do
  export "${variable?}"
done < <(systemctl --user show-environment | grep -E \
  '^(DBUS_SESSION_BUS_ADDRESS|DISPLAY|HYPRLAND_INSTANCE_SIGNATURE|WAYLAND_DISPLAY|XDG_CURRENT_DESKTOP|XDG_RUNTIME_DIR)=')

package_output="$(grep -Ev '^[[:space:]]*(#|$)' "$manifest")" ||
  die "could not load GUI package manifest"
mapfile -t packages <<< "$package_output"
((${#packages[@]} > 0)) || die "GUI package manifest is empty"
omarchy pkg add "${packages[@]}"
omarchy-pkg-aur-add bibata-cursor-theme

# Browser helpers own Wayland flags, native messaging, and base policies.
omarchy install browser brave
omarchy install browser firefox

if [[ ! -f "$vscode_marker" ]]; then
  omarchy install editor vscode
  install -Dm0644 /dev/null "$vscode_marker"
elif ! package_installed visual-studio-code-bin; then
  omarchy pkg add visual-studio-code-bin
else
  log "VS Code integration already installed"
fi

if [[ ! -f "$chatgpt_marker" ]]; then
  omarchy install ai chatgpt
  install -Dm0644 /dev/null "$chatgpt_marker"
elif ! package_installed openai-codex-desktop; then
  omarchy pkg add openai-codex-desktop
else
  log "ChatGPT integration already installed"
fi

sudo install -Dm0644 "$brave_policy" /etc/brave/policies/managed/nik-extensions.json
jq --slurpfile extensions "$firefox_extensions" \
  '.policies.ExtensionSettings = ((.policies.ExtensionSettings // {}) + $extensions[0])' \
  "$firefox_policy" > "$temporary"
jq empty "$temporary"
sudo install -m 0644 "$temporary" "$firefox_policy"

omarchy default browser brave

expected_packages=(
  bibata-cursor-theme
  bitwarden
  brave-bin
  firefox
  openai-codex-desktop
  t3code-bin
  telegram-desktop
  visual-studio-code-bin
)
for package in "${expected_packages[@]}"; do
  package_installed "$package" || die "$package is missing after installation"
done

[[ "$(env -u BROWSER xdg-settings get default-web-browser)" == brave-browser.desktop ]] ||
  die "Brave is not the default browser"
cmp -s "$brave_policy" /etc/brave/policies/managed/nik-extensions.json ||
  die "Brave extension policy mismatch"
jq -e --slurpfile extensions "$firefox_extensions" \
  '. as $policy | all($extensions[0] | to_entries[]; $policy.policies.ExtensionSettings[.key] == .value)' \
  "$firefox_policy" >/dev/null || die "Firefox extension policy mismatch"
jq -e --slurpfile base "$omarchy_firefox_policy" \
  '(.policies | del(.ExtensionSettings)) == ($base[0].policies | del(.ExtensionSettings))' \
  "$firefox_policy" >/dev/null || die "Omarchy Firefox policy mismatch"

install -Dm0644 /dev/null "$marker"
log "GUI applications and browser policies installed"
