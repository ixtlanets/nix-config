#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$repo_root/omarchy/plugins.tsv"
shell_config="$repo_root/dotfiles/omarchy/shell.json"
omaquote_config="$repo_root/dotfiles/omarchy/omaquote/config.json"
declare -A declared_plugins=()

jq -e . "$shell_config" >/dev/null
jq -e '
  .version == 1 and
  .intervalMinutes == 10 and
  .fontFamily == "Monaspace Krypton" and
  .preferredFontSize == 20
' "$omaquote_config" >/dev/null
jq -e '
  [.bar.layout.right[] | select(.id == "io.github.guiestrela.wallpaperomarchymanager")] == [{
    "id": "io.github.guiestrela.wallpaperomarchymanager",
    "displayConfig": {
      "eDP-1": {
        "folder": "~/wallpapers",
        "recursive": true,
        "mode": "shuffle",
        "pinned": "",
        "scaling": "zoom"
      },
      "all": {
        "folder": "~/wallpapers",
        "recursive": true,
        "mode": "shuffle",
        "pinned": "/home/nik/wallpapers/20150529_183703.jpg",
        "scaling": "zoom"
      }
    },
    "intervalSec": 600,
    "perDisplayConfig": false
  }]
' "$shell_config" >/dev/null
while read -r plugin_id plugin_url plugin_extra; do
  [[ -z "${plugin_id:-}" || "$plugin_id" == \#* ]] && continue
  [[ -n "${plugin_url:-}" && -z "${plugin_extra:-}" ]] || {
    printf 'Invalid Omarchy plugin manifest entry for %s\n' "$plugin_id" >&2
    exit 1
  }
  [[ -z "${declared_plugins[$plugin_id]:-}" ]] || {
    printf 'Duplicate Omarchy plugin manifest entry: %s\n' "$plugin_id" >&2
    exit 1
  }
  declared_plugins[$plugin_id]="$plugin_url"
  jq -e --arg id "$plugin_id" '
    [
      .bar.layout[][]?.id,
      .plugins[]?.id
    ] | any(. == $id)
  ' "$shell_config" >/dev/null || {
    printf 'Declared Omarchy plugin is not enabled in shell.json: %s\n' "$plugin_id" >&2
    exit 1
  }
done < "$manifest"

while read -r plugin_id; do
  [[ -n "${declared_plugins[$plugin_id]:-}" ]] || {
    printf 'Enabled Omarchy plugin is absent from plugins.tsv: %s\n' "$plugin_id" >&2
    exit 1
  }
done < <(jq -r '
  [
    .bar.layout[][]?.id,
    .plugins[]?.id
  ] | unique[] | select(startswith("omarchy.") | not)
' "$shell_config")

[[ "${#declared_plugins[@]}" -eq 4 ]] || {
  printf 'Expected four shared third-party Omarchy plugins, found %s\n' \
    "${#declared_plugins[@]}" >&2
  exit 1
}

grep -Fq 'omarchy/plugins.tsv' "$repo_root/scripts/omarchy-apply-user.sh"
grep -Fq 'omarchy/plugins.tsv' "$repo_root/scripts/omarchy-provision.sh"
grep -Fq 'omarchy/plugins.tsv' "$repo_root/scripts/omarchy-verify.sh"
grep -Fq 'dotfiles/quotes.txt' "$repo_root/scripts/omarchy-apply-user.sh"
grep -Fq 'dotfiles/quotes.txt' "$repo_root/scripts/omarchy-provision.sh"
grep -Fxq 'otf-monaspace' "$repo_root/omarchy/packages/required.txt"
grep -Fxq 'hyprmoncfg-bin' "$repo_root/omarchy/packages/aur.txt"
grep -Fq 'scripts/omarchy-apply-user.sh' "$repo_root/scripts/omarchy-root-phase.sh"
apply_user_line="$(grep -nF 'scripts/omarchy-apply-user.sh' \
  "$repo_root/scripts/omarchy-root-phase.sh" | cut -d: -f1)"
root_aur_line="$(grep -nF 'omarchy pkg aur add "${aur_packages[@]}"' \
  "$repo_root/scripts/omarchy-root-phase.sh" | cut -d: -f1)"
root_tailscale_line="$(grep -nF 'sudo tailscale up --accept-routes --accept-dns=true' \
  "$repo_root/scripts/omarchy-root-phase.sh" | cut -d: -f1)"
mapfile -t root_vless_probe_lines < <(
  grep -nF 'bash "$source_root/scripts/omarchy-test-vless.sh"' \
    "$repo_root/scripts/omarchy-root-phase.sh" | cut -d: -f1
)
[[ "${#root_vless_probe_lines[@]}" -eq 2 ]]
((root_vless_probe_lines[0] < root_aur_line))
((root_aur_line <= apply_user_line))
((apply_user_line < root_tailscale_line))
((root_tailscale_line < root_vless_probe_lines[1]))
remote_vless_probe_line="$(grep -nF "omarchy-test-vless.sh' --keep-active" \
  "$repo_root/scripts/omarchy-provision.sh" | cut -d: -f1)"
remote_aur_line="$(grep -nF 'omarchy pkg aur add $aur_package_command' \
  "$repo_root/scripts/omarchy-provision.sh" | cut -d: -f1)"
remote_tailscale_line="$(grep -nF 'sudo tailscale set --accept-dns=true' \
  "$repo_root/scripts/omarchy-provision.sh" | cut -d: -f1)"
remote_final_vless_probe_line="$(grep -nF 'run_privileged_remote "bash '\''$remote_root/scripts/omarchy-test-vless.sh' \
  "$repo_root/scripts/omarchy-provision.sh" | cut -d: -f1 | while read -r line; do
    [[ "$line" == "$remote_vless_probe_line" ]] || printf '%s\n' "$line"
  done)"
((remote_aur_line > remote_vless_probe_line))
((remote_tailscale_line > remote_aur_line))
((remote_final_vless_probe_line > remote_tailscale_line))
grep -Fq "omarchy-test-vless.sh' --keep-active --probe-url https://cp.cloudflare.com/generate_204" \
  "$repo_root/scripts/omarchy-provision.sh"
[[ "$(grep -Fc 'run_privileged_remote "bash '\''$remote_root/scripts/omarchy-test-vless.sh' \
  "$repo_root/scripts/omarchy-provision.sh")" -eq 2 ]]
grep -Fq 'command -v hyprmoncfgd >/dev/null 2>&1 ||' \
  "$repo_root/scripts/omarchy-apply-user.sh"
! grep -Fq 'if command -v hyprmoncfgd' "$repo_root/scripts/omarchy-apply-user.sh"
grep -Fq 'systemctl --user enable --now hyprmoncfgd.service' \
  "$repo_root/scripts/omarchy-apply-user.sh"
grep -Fq 'systemctl --user is-enabled hyprmoncfgd.service' \
  "$repo_root/scripts/omarchy-verify.sh"
grep -Fq 'hyprmoncfgd.service' "$repo_root/scripts/omarchy-verify.sh"

printf 'PASS: Omarchy provisioning declares and enables all shared plugins\n'
