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
  [[ -f "$rule_source" ]] || die "USB wake rule is missing"

  install -Dm0644 "$rule_source" /etc/udev/rules.d/80-usb-hub-wakeup.rules
  udevadm control --reload-rules
  udevadm trigger --subsystem-match=usb --action=change
fi

printf '[omarchy:system] system configuration applied\n'
