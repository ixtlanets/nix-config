#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rule_set_url="https://cdn.jsdelivr.net/gh/SagerNet/sing-geoip@rule-set/geoip-ru.srs"
linux_configs=(
  desktop.json
  um790pro.json
  x13.json
  x1carbon.json
  zenbook.json
)

for config_name in "${linux_configs[@]}"; do
  config="$repo_root/secrets/vless/$config_name"
  jq -e --arg url "$rule_set_url" '
    [.route.rule_set[] | select(.tag == "geoip-ru")] == [{
      tag: "geoip-ru",
      type: "remote",
      format: "binary",
      url: $url,
      download_detour: "direct"
    }]
  ' "$config" >/dev/null || {
    printf 'Invalid geoip-ru bootstrap in %s\n' "$config_name" >&2
    exit 1
  }
done

printf 'PASS: Linux VLESS configs bootstrap geoip-ru directly from jsDelivr\n'
