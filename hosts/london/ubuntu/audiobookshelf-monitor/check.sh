#!/usr/bin/env bash
set -euo pipefail

public_status_url="${PUBLIC_STATUS_URL:-https://books.nikcode.xyz/status}"
upstream_status_url="${UPSTREAM_STATUS_URL:-http://100.81.67.47:13378/status}"
tls_host="${TLS_HOST:-books.nikcode.xyz}"
tls_port="${TLS_PORT:-443}"
tls_min_valid_seconds="${TLS_MIN_VALID_SECONDS:-604800}"

for command_name in curl jq openssl timeout; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf '[audiobookshelf-monitor] missing command: %s\n' "$command_name" >&2
    exit 1
  }
done

check_status() {
  local label="$1"
  local url="$2"
  local response

  response="$(curl --fail --silent --show-error \
    --connect-timeout 5 --max-time 15 "$url")"
  jq -e '.app == "audiobookshelf" and .isInit == true' \
    <<<"$response" >/dev/null || {
    printf '[audiobookshelf-monitor] invalid %s status response\n' "$label" >&2
    exit 1
  }
  printf '[audiobookshelf-monitor] %s status healthy\n' "$label"
}

check_status upstream "$upstream_status_url"
check_status public "$public_status_url"

certificate="$(
  timeout 15 openssl s_client \
    -connect "$tls_host:$tls_port" \
    -servername "$tls_host" </dev/null 2>/dev/null |
    openssl x509 -outform PEM
)"
[[ -n "$certificate" ]] || {
  printf '[audiobookshelf-monitor] could not read TLS certificate\n' >&2
  exit 1
}
openssl x509 -checkend "$tls_min_valid_seconds" -noout \
  <<<"$certificate" >/dev/null || {
  printf '[audiobookshelf-monitor] TLS certificate expires too soon\n' >&2
  exit 1
}

printf '[audiobookshelf-monitor] public HTTPS, upstream, and TLS checks passed\n'
