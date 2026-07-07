#!/usr/bin/env bash
set -euo pipefail

ZONE_NAME=${ZONE_NAME:-nikcode.xyz}
RECORD_NAME=${RECORD_NAME:-vault.nikcode.xyz}
TTL=${TTL:-300}
PASS_NAME=${PASS_NAME:-api/cloudflare.com/snikulin@gmail.com/dns}

content=${1:-}

if [[ -z "$content" ]]; then
  echo "usage: $0 <ipv4-address>" >&2
  exit 1
fi

for command in curl jq pass; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

token=$(pass show "$PASS_NAME")
api=https://api.cloudflare.com/client/v4

cf() {
  curl -fsS \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    "$@"
}

zone_id=$(cf "$api/zones?name=$ZONE_NAME" | jq -er '.result[0].id')
record_id=$(cf "$api/zones/$zone_id/dns_records?type=A&name=$RECORD_NAME" | jq -r '.result[0].id // empty')

payload=$(jq -n \
  --arg type A \
  --arg name "$RECORD_NAME" \
  --arg content "$content" \
  --argjson ttl "$TTL" \
  '{type: $type, name: $name, content: $content, ttl: $ttl, proxied: false}')

if [[ -n "$record_id" ]]; then
  cf -X PUT --data "$payload" "$api/zones/$zone_id/dns_records/$record_id" >/dev/null
else
  cf -X POST --data "$payload" "$api/zones/$zone_id/dns_records" >/dev/null
fi

echo "$RECORD_NAME A $content"
