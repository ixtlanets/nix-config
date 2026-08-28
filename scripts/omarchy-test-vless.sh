#!/usr/bin/env bash
set -euo pipefail

service="vless-sing-box.service"
started_here=false

cleanup() {
  if $started_here; then
    sudo -n systemctl stop "$service" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sudo -v
if ! systemctl is-active --quiet "$service"; then
  sudo systemctl start "$service"
  started_here=true
fi

sleep 5
systemctl is-active --quiet "$service"
read -r tun_interface < /etc/sing-box/vless-interface
[[ -e "/sys/class/net/$tun_interface" ]]

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
