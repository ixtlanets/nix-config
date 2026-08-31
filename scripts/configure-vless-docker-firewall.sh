#!/usr/bin/env bash
set -euo pipefail

before_rules=/etc/ufw/before.rules
ufw_bin=ufw

usage() {
  cat <<'EOF'
Usage: configure-vless-docker-firewall.sh [--before-rules PATH] [--ufw PATH]

Install an idempotent UFW rule that accepts sing-box DNAT traffic arriving
from Docker bridges. The optional paths are intended for tests.
EOF
}

while (($# > 0)); do
  case "$1" in
    --before-rules)
      [[ $# -ge 2 ]] || {
        usage >&2
        exit 2
      }
      before_rules=$2
      shift 2
      ;;
    --ufw)
      [[ $# -ge 2 ]] || {
        usage >&2
        exit 2
      }
      ufw_bin=$2
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ $before_rules == /etc/ufw/before.rules && $EUID -ne 0 ]]; then
  printf 'configure-vless-docker-firewall: run as root\n' >&2
  exit 1
fi

[[ -f $before_rules ]] || {
  printf 'configure-vless-docker-firewall: missing %s\n' "$before_rules" >&2
  exit 1
}
[[ -x $ufw_bin ]] || command -v "$ufw_bin" >/dev/null 2>&1 || {
  printf 'configure-vless-docker-firewall: ufw not found: %s\n' "$ufw_bin" >&2
  exit 1
}

begin_marker='# BEGIN nix-config VLESS Docker'
end_marker='# END nix-config VLESS Docker'
rules_changed=false
legacy_changed=false
tmp_rules="$(mktemp "${before_rules}.nix-config.XXXXXX")"

cleanup() {
  rm -f "$tmp_rules"
}
trap cleanup EXIT

if ! awk \
  -v begin_marker="$begin_marker" \
  -v end_marker="$end_marker" '
    $0 == begin_marker { managed = 1; next }
    $0 == end_marker { managed = 0; next }
    managed { next }

    $0 == "*filter" { in_filter = 1 }
    in_filter && !inserted && $0 == "COMMIT" {
      print begin_marker
      print "# sing-box auto_redirect selects an ephemeral TCP port on every start."
      print "# Match DNAT state instead of a port, restricted to Docker bridge ingress."
      print "-A ufw-before-input -i docker0 -p tcp -m conntrack --ctstate DNAT -j ACCEPT"
      print "-A ufw-before-input -i br-+ -p tcp -m conntrack --ctstate DNAT -j ACCEPT"
      print end_marker
      inserted = 1
      in_filter = 0
    }

    { print }

    END {
      if (!inserted || managed) {
        exit 42
      }
    }
  ' "$before_rules" >"$tmp_rules"; then
  printf 'configure-vless-docker-firewall: could not locate a valid UFW filter table in %s\n' "$before_rules" >&2
  exit 1
fi

if ! cmp -s "$before_rules" "$tmp_rules"; then
  backup="${before_rules}.nix-config-backup"
  if [[ ! -e $backup ]]; then
    cp --preserve=all "$before_rules" "$backup"
  fi
  chmod --reference="$before_rules" "$tmp_rules"
  chown --reference="$before_rules" "$tmp_rules"
  mv -f "$tmp_rules" "$before_rules"
  rules_changed=true
  printf 'Installed dynamic sing-box Docker rules in %s\n' "$before_rules"
fi

if ! ufw_status="$($ufw_bin status numbered)"; then
  printf 'configure-vless-docker-firewall: failed to inspect UFW rules\n' >&2
  exit 1
fi

mapfile -t legacy_rule_numbers < <(
  printf '%s\n' "$ufw_status" |
    sed -n '/sing-box docker redirect/ s/^\[[[:space:]]*\([0-9][0-9]*\)\].*/\1/p'
)

for ((i = ${#legacy_rule_numbers[@]} - 1; i >= 0; i--)); do
  "$ufw_bin" --force delete "${legacy_rule_numbers[i]}"
  legacy_changed=true
done

if $rules_changed || $legacy_changed; then
  if grep -Fqx 'Status: active' <<<"$ufw_status"; then
    "$ufw_bin" reload
  else
    printf 'UFW is inactive; rules will load when it is enabled\n'
  fi
else
  printf 'VLESS Docker firewall rules are already current\n'
fi
