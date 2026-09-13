#!/usr/bin/env bash

set -u

if [[ ${1:-} != --host || $# -ne 2 ]]; then
  echo "usage: $0 --host um790pro|moscow" >&2
  exit 2
fi
host=$2
if [[ $host != um790pro && $host != moscow ]]; then
  echo "unknown host: $host" >&2
  exit 2
fi

bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
failures=0
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); }

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "command: $1"
  else
    fail "command: $1"
  fi
}

check_secret() {
  local path=$1 mode uid
  if [[ ! -f $path || -L $path || ! -s $path ]]; then
    fail "secret is non-empty regular file: $(basename -- "$path")"
    return
  fi
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  if [[ $mode == 600 ]]; then
    pass "secret mode 0600: $(basename -- "$path")"
  else
    fail "secret mode 0600: $(basename -- "$path")"
  fi
  if [[ $uid == 0 ]]; then
    pass "secret owner root: $(basename -- "$path")"
  else
    fail "secret owner root: $(basename -- "$path")"
  fi
}

check_root_immutable_file() {
  local path=$1 label=$2 mode uid
  if [[ ! -f $path || -L $path ]]; then
    fail "$label: $path"
    return
  fi
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  if [[ $uid == 0 && $mode =~ ^[0-7]{3,4}$ ]] && (( (8#$mode & 8#022) == 0 )); then
    pass "$label: $path"
  else
    fail "$label: $path"
  fi
}

check_operator_config_directory() {
  local path=$1 mode uid gid
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  gid=$(stat -c %g -- "$path" 2>/dev/null || true)
  if [[ -d $path && ! -L $path && $uid == 0 && $gid == 1000 && $mode == 750 ]]; then
    pass "operator config readable by service group: $path"
  else
    fail "operator config readable by service group: $path"
  fi
}

check_nik_directory() {
  local path=$1 mode uid
  if [[ ! -d $path || -L $path ]]; then
    fail "nik-owned writable state directory: $path"
    return
  fi
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  if [[ $uid == 1000 && $mode =~ ^[0-7]{3,4}$ ]] && (( (8#$mode & 8#200) != 0 )); then
    pass "nik-owned writable state directory: $path"
  else
    fail "nik-owned writable state directory: $path"
  fi
}

check_root_private_directory() {
  local path=$1 mode uid
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  if [[ -d $path && ! -L $path && $uid == 0 && $mode == 700 ]]; then
    pass "root-private directory: $path"
  else
    fail "root-private directory: $path"
  fi
}

check_free() {
  local path=$1 minimum_gib=$2 available
  available=$(df -Pk -- "$path" 2>/dev/null | awk 'NR == 2 {print $4}')
  if [[ $available =~ ^[0-9]+$ ]] && ((available >= minimum_gib * 1024 * 1024)); then
    pass "free-space reserve ${minimum_gib} GiB: $path"
  else
    fail "free-space reserve ${minimum_gib} GiB: $path"
  fi
}

if [[ $host == um790pro ]]; then
  state_root=${AUDIOBOOK_OPS_STATE_ROOT:-/home/nik/services/audiobook-ops}
  retained_root=${AUDIOBOOK_OPS_RETAINED_STATE_ROOT:-/home/nik/services/readmeabook}
  secrets_root=${AUDIOBOOK_OPS_SECRETS_ROOT:-/etc/audiobook-ops/secrets}
  backup_root=${AUDIOBOOK_OPS_BACKUP_ROOT:-/var/backups/audiobook-ops}
  config_file=${AUDIOBOOK_OPS_CONFIG_FILE:-/etc/audiobook-ops/config/audiobook-ops.json}
  config_root=$(dirname -- "$config_file")
  compose_env=${AUDIOBOOK_OPS_COMPOSE_ENV:-/etc/audiobook-ops/config/compose.env}
  for command in docker tailscale python3 ssh rsync ffprobe ffmpeg curl flock systemctl ip; do
    check_command "$command"
  done
  if [[ $(uname -m) == x86_64 ]]; then
    pass "architecture: x86_64"
  else
    fail "architecture: x86_64"
  fi
  if [[ $bundle_dir == /usr/local/lib/audiobook-ops ]] \
    && [[ -z $(find "$bundle_dir" -xdev \( -type l -o ! -user root -o -perm /022 \) -print -quit 2>/dev/null) ]]; then
    pass "installed bundle root-owned and immutable"
  else
    fail "installed bundle root-owned and immutable"
  fi
  check_operator_config_directory "$config_root"
  for name in audiobook-ops.json backup.json compose.env health.json policy.json publisher.json; do
    check_root_immutable_file "$config_root/$name" "operator config root-owned and immutable"
  done
  for root in "$state_root" "$state_root/staging" "$retained_root/prowlarr" "$retained_root/transmission" "$retained_root/downloads"; do
    check_nik_directory "$root"
  done
  check_root_private_directory "$secrets_root"
  check_root_private_directory "$backup_root"
  check_free "$state_root" 100
  for name in abs-api-token mcp-bearer prowlarr-api-key publisher-ssh-key transmission-password; do
    check_secret "$secrets_root/$name"
  done
  if [[ -f $config_file && ! -L $config_file ]] \
    && python3 -m json.tool "$config_file" >/dev/null 2>&1; then
    pass "runtime config JSON"
  else
    fail "runtime config JSON"
  fi
  rendered_compose=$(docker compose --env-file "$compose_env" \
    -f "$bundle_dir/docker-compose.yml" config --format json 2>/dev/null || true)
  if [[ -f $compose_env && ! -L $compose_env ]] \
    && python3 -c \
      'import json,re,sys; value=json.loads(sys.stdin.read()); assert re.fullmatch(r"sha256:[0-9a-f]{64}", value["services"]["audiobook-ops"]["image"])' \
      <<<"$rendered_compose"; then
    pass "production Compose render"
  else
    fail "production Compose render"
  fi
  if systemctl is-active --quiet vless-sing-box.service; then
    pass "VLESS service active"
  else
    fail "VLESS service active"
  fi
  if ip link show dev nekoray-tun >/dev/null 2>&1; then
    pass "VLESS interface present"
  else
    fail "VLESS interface present"
  fi
  expected_ip=${AUDIOBOOK_OPS_EXPECTED_TAILSCALE_IP:-100.95.213.117}
  if tailscale ip -4 2>/dev/null | grep -Fxq -- "$expected_ip"; then
    pass "Tailscale bind address: $expected_ip"
  else
    fail "Tailscale bind address: $expected_ip"
  fi
  remote_host=${AUDIOBOOK_OPS_REMOTE_HOST:-nik@100.81.67.47}
  known_hosts=${AUDIOBOOK_OPS_KNOWN_HOSTS_FILE:-/home/nik/.ssh/known_hosts}
  capacity=$(ssh -T -i "$secrets_root/publisher-ssh-key" \
    -o BatchMode=yes -o ClearAllForwardings=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$known_hosts" -o UpdateHostKeys=no \
    "$remote_host" capacity 2>/dev/null || true)
  if python3 -c \
    'import json,sys; value=json.loads(sys.argv[1]); assert int(value["free_bytes"]) >= 200 * 1024**3' \
    "$capacity" 2>/dev/null; then
    pass "restricted publisher capacity"
  else
    fail "restricted publisher capacity"
  fi
else
  incoming=${AUDIOBOOK_OPS_INCOMING_ROOT:-/media/disk1/media/.readmeabook-incoming}
  final=${AUDIOBOOK_OPS_FINAL_ROOT:-/media/disk1/media/ReadMeABook}
  wrapper=${AUDIOBOOK_OPS_REMOTE_WRAPPER:-/home/nik/.local/libexec/audiobook-ops-remote-wrapper.py}
  for command in tailscale python3 curl systemctl docker; do check_command "$command"; done
  for root in "$incoming" "$final"; do
    if [[ -d $root && ! -L $root && -w $root ]]; then
      pass "confined writable root: $root"
    else
      fail "confined writable root: $root"
    fi
  done
  if [[ $(stat -c %d -- "$incoming" 2>/dev/null) == $(stat -c %d -- "$final" 2>/dev/null) ]]; then
    pass "publication roots share a filesystem"
  else
    fail "publication roots share a filesystem"
  fi
  if [[ $(stat -c %a -- "$incoming" 2>/dev/null) == 700 ]]; then
    pass "incoming mode 0700"
  else
    fail "incoming mode 0700"
  fi
  if [[ $(stat -c %a -- "$final" 2>/dev/null) == 2775 ]]; then
    pass "final mode 2775"
  else
    fail "final mode 2775"
  fi
  check_free "$final" 200
  if [[ -f $wrapper && ! -L $wrapper ]] \
    && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$wrapper"; then
    pass "forced-command wrapper parses"
  else
    fail "forced-command wrapper parses"
  fi
  if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:13378 >/dev/null; then
    pass "Audiobookshelf reachable"
  else
    fail "Audiobookshelf reachable"
  fi
  if docker inspect audiobookshelf >/dev/null 2>&1; then
    pass "Audiobookshelf container exists"
  else
    fail "Audiobookshelf container exists"
  fi
fi

if ((failures)); then
  echo "Preflight failed: $failures check(s)"
  exit 1
fi
echo "Preflight passed"
