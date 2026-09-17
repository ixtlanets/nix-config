#!/usr/bin/env bash
set -euo pipefail

source_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
expected_host="${OMARCHY_EXPECTED_HOST:-$(hostname -s)}"

die() {
  printf '[omarchy:system] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$(id -u)" -eq 0 ]] || die "run as root"
[[ "$(hostname -s)" == "$expected_host" ]] || die "unexpected hostname"
[[ -r /etc/os-release ]] || die "/etc/os-release is missing"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == omarchy ]] || die "host is not Omarchy"

if [[ "$expected_host" == zenbook ]]; then
  rule_source="$source_root/dotfiles/omarchy/system/udev/80-usb-hub-wakeup.rules"
  lid_source="$source_root/dotfiles/omarchy/system/logind.conf.d/90-headless-lid.conf"
  routing_helper_source="$source_root/dotfiles/omarchy/system/libexec/zenbook-lan-first-routing"
  routing_unit_source="$source_root/dotfiles/omarchy/system/systemd/system/zenbook-lan-first-routing.service"
  upower_source="$source_root/dotfiles/omarchy/system/UPower.conf.d/90-headless-battery.conf"
  [[ -f "$rule_source" ]] || die "USB wake rule is missing"
  [[ -f "$lid_source" ]] || die "headless lid configuration is missing"
  [[ -x "$routing_helper_source" ]] || die "LAN-first routing helper is missing"
  [[ -f "$routing_unit_source" ]] || die "LAN-first routing service is missing"
  [[ -f "$upower_source" ]] || die "headless battery configuration is missing"

  install -Dm0644 "$rule_source" /etc/udev/rules.d/80-usb-hub-wakeup.rules
  install -Dm0644 "$lid_source" /etc/systemd/logind.conf.d/90-headless-lid.conf
  install -Dm0755 "$routing_helper_source" /usr/local/libexec/zenbook-lan-first-routing
  install -Dm0644 "$routing_unit_source" /etc/systemd/system/zenbook-lan-first-routing.service
  install -Dm0644 "$upower_source" /etc/UPower/UPower.conf.d/90-headless-battery.conf
  udevadm control --reload-rules
  udevadm trigger --subsystem-match=usb --action=change
  systemctl daemon-reload
  systemctl enable zenbook-lan-first-routing.service
  systemctl restart zenbook-lan-first-routing.service
  systemctl disable --now zenbook-battery-guard.service >/dev/null 2>&1 || true
fi

printf '[omarchy:system] system configuration applied\n'
