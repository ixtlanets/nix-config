#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
firewall_helper="$repo_root/scripts/configure-vless-docker-firewall.sh"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

[[ -x $firewall_helper ]]
grep -Fq 'scripts/configure-vless-docker-firewall.sh' "$repo_root/install.sh"

before_rules="$tmp_dir/before.rules"
cat >"$before_rules" <<'RULES'
# ufw fixture
*filter
:ufw-before-input - [0:0]
:ufw-before-output - [0:0]
:ufw-before-forward - [0:0]
-A ufw-before-input -i lo -j ACCEPT
COMMIT
RULES
chmod 0640 "$before_rules"

mock_bin="$tmp_dir/bin"
mock_state="$tmp_dir/ufw.state"
mock_calls="$tmp_dir/ufw.calls"
mkdir -p "$mock_bin"
printf 'two\n' >"$mock_state"

cat >"$mock_bin/ufw" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' "$*" >>"$UFW_CALLS"

case "$*" in
  'status numbered')
    printf 'Status: active\n'
    case "$(<"$UFW_STATE")" in
      two)
        printf '[ 1] 41935/tcp on docker0 ALLOW IN Anywhere # sing-box docker redirect\n'
        printf '[ 2] 41935/tcp on br-deadbeef ALLOW IN Anywhere # sing-box docker redirect\n'
        ;;
      one)
        printf '[ 1] 41935/tcp on docker0 ALLOW IN Anywhere # sing-box docker redirect\n'
        ;;
    esac
    ;;
  '--force delete 2')
    printf 'one\n' >"$UFW_STATE"
    ;;
  '--force delete 1')
    printf 'none\n' >"$UFW_STATE"
    ;;
  'reload') ;;
  *)
    printf 'Unexpected ufw arguments: %s\n' "$*" >&2
    exit 1
    ;;
esac
MOCK
chmod +x "$mock_bin/ufw"

UFW_STATE="$mock_state" \
  UFW_CALLS="$mock_calls" \
  "$firewall_helper" --before-rules "$before_rules" --ufw "$mock_bin/ufw"

grep -Fxq '# BEGIN nix-config VLESS Docker' "$before_rules"
grep -Fxq -- '-A ufw-before-input -i docker0 -p tcp -m conntrack --ctstate DNAT -j ACCEPT' "$before_rules"
grep -Fxq -- '-A ufw-before-input -i br-+ -p tcp -m conntrack --ctstate DNAT -j ACCEPT' "$before_rules"
grep -Fxq '# END nix-config VLESS Docker' "$before_rules"
[[ "$(grep -Fc '# BEGIN nix-config VLESS Docker' "$before_rules")" == 1 ]]
managed_end_line="$(grep -nF '# END nix-config VLESS Docker' "$before_rules" | cut -d: -f1)"
filter_commit_line="$(grep -nFx 'COMMIT' "$before_rules" | head -n1 | cut -d: -f1)"
((managed_end_line < filter_commit_line))
[[ "$(stat -c '%a' "$before_rules")" == 640 ]]
[[ "$(<"$mock_state")" == none ]]
grep -Fxq -- '--force delete 2' "$mock_calls"
grep -Fxq -- '--force delete 1' "$mock_calls"
grep -Fxq 'reload' "$mock_calls"

rules_checksum="$(sha256sum "$before_rules")"
calls_count="$(wc -l <"$mock_calls")"

UFW_STATE="$mock_state" \
  UFW_CALLS="$mock_calls" \
  "$firewall_helper" --before-rules "$before_rules" --ufw "$mock_bin/ufw"

[[ "$(sha256sum "$before_rules")" == "$rules_checksum" ]]
[[ "$(wc -l <"$mock_calls")" == $((calls_count + 1)) ]]
[[ "$(tail -n 1 "$mock_calls")" == 'status numbered' ]]

if command -v iptables-translate >/dev/null 2>&1; then
  for iface in docker0 br-+; do
    iptables-translate \
      -A ufw-before-input \
      -i "$iface" \
      -p tcp \
      -m conntrack --ctstate DNAT \
      -j ACCEPT | grep -Fq 'ct status dnat'
  done
fi

if rg -q -- '--dport 41935|local port=41935' \
  "$repo_root/install.sh" \
  "$repo_root/modules/nixos/vless.nix"; then
  printf 'VLESS Docker firewall still assumes fixed redirect port 41935\n' >&2
  exit 1
fi

printf 'PASS: VLESS Docker firewall follows dynamic sing-box DNAT ports\n'
