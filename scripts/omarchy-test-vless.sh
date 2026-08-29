#!/usr/bin/env bash
set -euo pipefail

service="vless-sing-box.service"
started_here=false

cleanup() {
  if $started_here; then
    sudo systemctl stop "$service" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! systemctl is-active --quiet "$service"; then
  sudo systemctl start "$service"
  started_here=true
fi

read -r tun_interface < /etc/sing-box/vless-interface
tunnel_ready=false
for ((attempt = 0; attempt < 60; attempt++)); do
  if systemctl is-active --quiet "$service" && [[ -e "/sys/class/net/$tun_interface" ]]; then
    tunnel_ready=true
    break
  fi
  [[ "$(systemctl show --property=SubState --value "$service")" != auto-restart ]] || break
  sleep 0.5
done
if ! $tunnel_ready; then
  printf '[omarchy:vless] TUN interface %s did not become ready.\n' "$tun_interface" >&2
  systemctl status --no-pager "$service" >&2 || true
  exit 1
fi

if systemctl is-active --quiet systemd-resolved.service; then
  resolved_dns="$(resolvectl dns "$tun_interface")"
  resolved_domains="$(resolvectl domain "$tun_interface")"
  resolved_default_route="$(resolvectl default-route "$tun_interface")"
  if grep -Eq '\):[[:space:]]+[^[:space:]]' <<< "$resolved_dns"; then
    printf '[omarchy:vless] TUN unexpectedly registered DNS servers.\n' >&2
    exit 1
  fi
  if grep -Fq '~.' <<< "$resolved_domains"; then
    printf '[omarchy:vless] TUN unexpectedly owns the default DNS domain.\n' >&2
    exit 1
  fi
  if grep -Eq ': yes$' <<< "$resolved_default_route"; then
    printf '[omarchy:vless] TUN unexpectedly owns the default DNS route.\n' >&2
    exit 1
  fi
fi

curl --fail --silent --show-error --max-time 15 \
  --output /dev/null https://www.google.com/generate_204
if $started_here; then
  printf '[omarchy:vless] smoke test passed on %s; stopping the temporary tunnel.\n' "$tun_interface"
else
  printf '[omarchy:vless] smoke test passed on already-active tunnel %s.\n' "$tun_interface"
fi
