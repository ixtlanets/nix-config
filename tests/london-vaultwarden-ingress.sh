#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
caddyfile="$repo_root/hosts/london/ubuntu/vaultwarden/Caddyfile"
compose_file="$repo_root/hosts/london/ubuntu/vaultwarden/docker-compose.yml"

grep -Fq '"10.0.0.72:443:443"' "$compose_file"

if grep -Eq '443:443(/udp)?"' "$compose_file" &&
  ! grep -Fq 'protocols h1 h2' "$caddyfile"; then
  printf 'Caddy must not advertise HTTP/3 when its ingress publishes TCP/443 only\n' >&2
  exit 1
fi

[[ "$(grep -Fc 'Alt-Svc "clear"' "$caddyfile")" == 2 ]]

printf 'PASS: London Caddy protocols match the published ingress transports\n'
