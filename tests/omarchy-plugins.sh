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
grep -Fq 'hyprmoncfgd.service' "$repo_root/scripts/omarchy-verify.sh"

printf 'PASS: Omarchy provisioning declares and enables all shared plugins\n'
