#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
helper="$repo_root/dotfiles/omarchy/system/libexec/zenbook-lan-first-routing"
unit="$repo_root/dotfiles/omarchy/system/systemd/system/zenbook-lan-first-routing.service"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

[[ -x "$helper" ]]
[[ -f "$unit" ]]

mock_ip="$tmp_dir/ip"
state="$tmp_dir/state"
calls="$tmp_dir/calls"

cat > "$mock_ip" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

if [[ "$*" == '-4 rule show' ]]; then
  printf '0: from all lookup local\n'
  case "$(<"$IP_STATE")" in
    managed)
      printf '5260: from all to 192.168.1.0/24 lookup main suppress_prefixlength 23\n'
      ;;
    collision)
      printf '5260: from all to 10.0.0.0/8 lookup main\n'
      ;;
  esac
  printf '5270: from all lookup 52\n'
  printf '32766: from all lookup main\n'
  exit 0
fi

printf '%s\n' "$*" >> "$IP_CALLS"
case "$*" in
  '-4 rule add priority 5260 to 192.168.1.0/24 lookup main suppress_prefixlength 23')
    printf 'managed\n' > "$IP_STATE"
    ;;
  '-4 rule delete priority 5260 to 192.168.1.0/24 lookup main suppress_prefixlength 23')
    printf 'none\n' > "$IP_STATE"
    ;;
  *)
    printf 'Unexpected ip arguments: %s\n' "$*" >&2
    exit 1
    ;;
esac
MOCK
chmod +x "$mock_ip"

printf 'none\n' > "$state"
: > "$calls"
IP_BIN="$mock_ip" IP_STATE="$state" IP_CALLS="$calls" "$helper" ensure
[[ "$(<"$state")" == managed ]]
grep -Fxq -- '-4 rule add priority 5260 to 192.168.1.0/24 lookup main suppress_prefixlength 23' "$calls"

call_count="$(wc -l < "$calls")"
IP_BIN="$mock_ip" IP_STATE="$state" IP_CALLS="$calls" "$helper" ensure
[[ "$(wc -l < "$calls")" == "$call_count" ]]

IP_BIN="$mock_ip" IP_STATE="$state" IP_CALLS="$calls" "$helper" remove
[[ "$(<"$state")" == none ]]
grep -Fxq -- '-4 rule delete priority 5260 to 192.168.1.0/24 lookup main suppress_prefixlength 23' "$calls"

call_count="$(wc -l < "$calls")"
IP_BIN="$mock_ip" IP_STATE="$state" IP_CALLS="$calls" "$helper" remove
[[ "$(wc -l < "$calls")" == "$call_count" ]]

printf 'collision\n' > "$state"
if IP_BIN="$mock_ip" IP_STATE="$state" IP_CALLS="$calls" "$helper" ensure 2>/dev/null; then
  printf 'Helper accepted a conflicting priority 5260 rule\n' >&2
  exit 1
fi
[[ "$(<"$state")" == collision ]]

if unshare --user --map-root-user --net true 2>/dev/null; then
  HELPER="$helper" unshare --user --map-root-user --net bash <<'NAMESPACE'
set -euo pipefail

ip link add lan type dummy
ip link set lan up
ip link set lo up
ip address add 192.168.1.249/24 dev lan
ip route add 192.168.1.174/32 dev lo table 52
ip route add 192.168.1.144/32 dev lo table 52
ip rule add priority 5270 lookup 52

"$HELPER" ensure
ip route get 192.168.1.174 | grep -Eq 'dev lan([[:space:]]|$)'
ip route get 192.168.1.144 | grep -Eq 'dev lan([[:space:]]|$)'

ip address delete 192.168.1.249/24 dev lan
ip route get 192.168.1.174 | grep -Eq 'dev lo table 52([[:space:]]|$)'
ip route get 192.168.1.144 | grep -Eq 'dev lo table 52([[:space:]]|$)'

"$HELPER" remove
! ip -4 rule show | grep -Eq '^5260:[[:space:]]'
NAMESPACE
else
  printf 'SKIP: unprivileged network namespaces are unavailable\n'
fi

grep -Fq 'ExecStart=/usr/local/libexec/zenbook-lan-first-routing ensure' "$unit"
grep -Fq 'ExecStop=/usr/local/libexec/zenbook-lan-first-routing remove' "$unit"
grep -Fq 'RemainAfterExit=yes' "$unit"

grep -Fq 'zenbook-lan-first-routing' "$repo_root/scripts/omarchy-apply-system.sh"
grep -Fq 'zenbook-lan-first-routing' "$repo_root/scripts/omarchy-verify.sh"
grep -Fq 'zenbook-lan-first-routing' "$repo_root/install.sh"
grep -Fq 'zenbook-lan-first-routing' "$repo_root/hosts/zenbook/nixos/configuration.nix"

printf 'PASS: Zenbook prefers a connected /24 LAN route before Tailscale host routes\n'
