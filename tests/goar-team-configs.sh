#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'Usage: %s <server-ip> <reality-public-key> <reality-short-id>\n' "$0" >&2
  exit 2
fi
server=$1
public_key=$2
short_id=$3
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$repo_root/secrets/vless"
profiles=(ios android macos windows)
uuids=()

for profile in "${profiles[@]}"; do
  config="$config_dir/goar-team-$profile.json"
  [[ -f "$config" ]] || { printf 'Missing %s\n' "$config" >&2; exit 1; }
  jq -e --arg server "$server" --arg public_key "$public_key" --arg short_id "$short_id" '
    (.outbounds | map(select(.tag == "proxy" and .type == "vless")) | length) == 1 and
    (.outbounds[] | select(.tag == "proxy") |
      .server == $server and .server_port == 443 and
      .tls.enabled == true and .tls.server_name == "www.google.com" and
      .tls.reality.enabled == true and
      .tls.reality.public_key == $public_key and
      .tls.reality.short_id == $short_id and
      (.uuid | test("^[0-9a-fA-F-]{36}$")))
  ' "$config" >/dev/null || { printf 'Invalid REALITY identity in %s\n' "$config" >&2; exit 1; }
  uuids+=("$(jq -r '.outbounds[] | select(.tag == "proxy") | .uuid' "$config")")
done

if [[ "$(printf '%s\n' "${uuids[@]}" | sort -u | wc -l)" -ne 4 ]]; then
  printf 'Goar-team device UUIDs must be distinct\n' >&2
  exit 1
fi

for profile in ios android; do
  config="$config_dir/goar-team-$profile.json"
  jq -e '
    .route.default_domain_resolver == "dns-bootstrap" and
    any(.dns.servers[]; .tag == "dns-bootstrap" and .type == "udp") and
    ([.route.rule_set[] | select(.tag == "geoip-ru" or .tag == "geosite-category-ru") |
      select(.type == "remote" and (.url | startswith("https://cdn.jsdelivr.net/gh/SagerNet/")) and
        .download_detour == "direct")] | length) == 2
  ' "$config" >/dev/null || { printf 'Invalid mobile bootstrap in %s\n' "$config" >&2; exit 1; }
done

jq -e '
  any(.inbounds[]; .type == "tun" and (.interface_name | startswith("utun"))) and
  any(.dns.servers[]; has("address") and has("address_resolver"))
' "$config_dir/goar-team-macos.json" >/dev/null || {
  printf 'Invalid macOS GUI shape\n' >&2; exit 1;
}

jq -e '
  any(.inbounds[]; .type == "tun" and .interface_name == "throne-tun" and
    (has("auto_redirect") | not)) and
  any(.outbounds[]; .tag == "block" and .type == "block")
' "$config_dir/goar-team-windows.json" >/dev/null || {
  printf 'Invalid Windows Throne shape\n' >&2; exit 1;
}

printf 'PASS: four Goar-team profiles have distinct UUIDs and expected identity/shapes\n'
