#!/usr/bin/env bash

set -u

host=
if [[ ${1:-} == "--host" && $# -eq 2 ]]; then
  host=$2
else
  echo "usage: $0 --host um790pro|moscow" >&2
  exit 2
fi
if [[ $host != um790pro && $host != moscow ]]; then
  echo "unknown host: $host" >&2
  exit 2
fi

bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
failures=0

pass() {
  echo "PASS  $1"
}

fail() {
  echo "FAIL  $1"
  failures=$((failures + 1))
}

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "command available: $1"
  else
    fail "command missing: $1"
  fi
}

check_architecture() {
  local expected=${READMABOOK_EXPECTED_ARCH:-x86_64}
  local actual
  actual=$(uname -m)
  if [[ $actual == "$expected" ]]; then
    pass "architecture: $actual"
  else
    fail "architecture is $actual, expected $expected"
  fi
}

check_tailscale_ip() {
  local expected=$1
  local addresses
  if ! addresses=$(tailscale ip -4 2>/dev/null); then
    fail "Tailscale IPv4 lookup"
  elif grep -Fxq -- "$expected" <<<"$addresses"; then
    pass "Tailscale IPv4: $expected"
  else
    fail "Tailscale IPv4 does not include $expected"
  fi
}

check_free_space() {
  local path=$1
  local minimum_gib=$2
  local label=$3
  local available_kib minimum_kib
  if [[ ! -d $path ]]; then
    fail "$label path exists: $path"
    return
  fi
  available_kib=$(df -Pk -- "$path" | awk 'NR == 2 {print $4}')
  minimum_kib=$((minimum_gib * 1024 * 1024))
  if [[ $available_kib =~ ^[0-9]+$ ]] && ((available_kib >= minimum_kib)); then
    pass "$label free-space reserve: ${minimum_gib} GiB"
  else
    fail "$label free-space reserve: ${minimum_gib} GiB"
  fi
}

check_secret() {
  local path=$1
  local name
  name=$(basename -- "$path")
  if [[ ! -f $path || -L $path || ! -s $path ]]; then
    fail "$name exists, is non-empty, and is not a symlink"
    return
  fi
  local mode
  mode=$(stat -c %a -- "$path" 2>/dev/null || true)
  if [[ $mode =~ ^[0-7]{3,4}$ ]] && (((8#$mode & 077) == 0)); then
    pass "$name permissions: $mode"
  else
    fail "$name permissions are private (actual: ${mode:-unknown})"
  fi
  local expected_uid=${READMABOOK_SECRETS_UID:-0}
  local actual_uid
  actual_uid=$(stat -c %u -- "$path" 2>/dev/null || true)
  if [[ $actual_uid == "$expected_uid" ]]; then
    pass "$name owner uid: $actual_uid"
  else
    fail "$name owner uid is $expected_uid (actual: ${actual_uid:-unknown})"
  fi
}

preflight_um790pro() {
  local state_root=${READMABOOK_STATE_ROOT:-/home/nik/services/readmeabook}
  local secrets_root=${READMABOOK_SECRETS_ROOT:-/etc/readmeabook/secrets}
  local publisher_config=${READMABOOK_PUBLISHER_CONFIG:-/home/nik/.config/readmeabook/publisher.json}
  local expected_ip=${READMABOOK_EXPECTED_TAILSCALE_IP:-100.95.213.117}
  local minimum_local=${READMABOOK_MIN_LOCAL_FREE_GIB:-100}
  local minimum_remote=${READMABOOK_MIN_REMOTE_FREE_GIB:-200}
  local remote_host=${READMABOOK_REMOTE_HOST:-nik@100.81.67.47}
  local known_hosts=${READMABOOK_KNOWN_HOSTS_FILE:-/home/nik/.ssh/known_hosts}
  local state_uid=${READMABOOK_STATE_UID:-1000}

  for command in docker tailscale python3 ssh rsync ffprobe curl; do
    check_command "$command"
  done
  check_architecture
  check_tailscale_ip "$expected_ip"

  if [[ -d $state_root && ! -L $state_root && -w $state_root ]]; then
    pass "state root exists and is writable"
  else
    fail "state root exists, is writable, and is not a symlink: $state_root"
  fi
  if [[ $(stat -c %a -- "$state_root" 2>/dev/null) == 700 ]] \
    && [[ $(stat -c %u -- "$state_root" 2>/dev/null) == "$state_uid" ]]; then
    pass "state root mode 0700 and expected owner"
  else
    fail "state root mode 0700 and owner uid $state_uid"
  fi
  check_free_space "$state_root" "$minimum_local" "UM790Pro"

  for secret in \
    abs-api-token \
    publisher-ssh-key \
    rmab-api-token \
    rmab-config-encryption-key \
    rmab-jwt-refresh-secret \
    rmab-jwt-secret \
    rmab-postgres-password \
    transmission-password; do
    check_secret "$secrets_root/$secret"
  done

  if [[ -f $publisher_config && ! -L $publisher_config ]] \
    && python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert isinstance(value,dict)' "$publisher_config" 2>/dev/null; then
    pass "publisher config is a JSON object"
  else
    fail "publisher config is a JSON object: $publisher_config"
  fi

  if docker compose -f "$bundle_dir/docker-compose.yml" config >/dev/null 2>&1; then
    pass "Compose renders successfully"
  else
    fail "Compose renders successfully"
  fi

  local capacity
  if capacity=$(ssh -T -i "$secrets_root/publisher-ssh-key" \
    -o BatchMode=yes -o ClearAllForwardings=yes -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$known_hosts" "$remote_host" capacity 2>/dev/null) \
    && python3 -c \
      'import json,sys; value=json.loads(sys.argv[1]); assert int(value["free_bytes"]) >= int(sys.argv[2]) * 1024**3' \
      "$capacity" "$minimum_remote" 2>/dev/null; then
    pass "remote publisher capacity and restricted SSH command"
  else
    fail "remote publisher capacity and restricted SSH command"
  fi
}

preflight_moscow() {
  local incoming_root=${READMABOOK_INCOMING_ROOT:-/media/disk1/media/.readmeabook-incoming}
  local final_root=${READMABOOK_FINAL_ROOT:-/media/disk1/media/ReadMeABook}
  local wrapper=${READMABOOK_REMOTE_WRAPPER:-/home/nik/.local/libexec/readmeabook-remote-wrapper.py}
  local expected_ip=${READMABOOK_EXPECTED_TAILSCALE_IP:-100.81.67.47}
  local minimum_remote=${READMABOOK_MIN_REMOTE_FREE_GIB:-200}
  local abs_url=${READMABOOK_ABS_URL:-http://127.0.0.1:13378}
  local remote_uid=${READMABOOK_REMOTE_UID:-$(id -u)}

  for command in tailscale python3 systemctl curl; do
    check_command "$command"
  done
  check_tailscale_ip "$expected_ip"

  local roots_ok=true
  for root in "$incoming_root" "$final_root"; do
    if [[ -d $root && ! -L $root && -w $root ]]; then
      pass "confined root exists and is writable: $root"
    else
      fail "confined root exists, is writable, and is not a symlink: $root"
      roots_ok=false
    fi
  done
  local incoming_mode final_mode incoming_uid final_uid
  incoming_mode=$(stat -c %a -- "$incoming_root" 2>/dev/null || true)
  final_mode=$(stat -c %a -- "$final_root" 2>/dev/null || true)
  incoming_uid=$(stat -c %u -- "$incoming_root" 2>/dev/null || true)
  final_uid=$(stat -c %u -- "$final_root" 2>/dev/null || true)
  if [[ $incoming_mode == 700 && $incoming_uid == "$remote_uid" ]]; then
    pass "incoming root mode 0700 and expected owner"
  else
    fail "incoming root mode 0700 and owner uid $remote_uid"
  fi
  if [[ $final_mode == 2775 && $final_uid == "$remote_uid" ]]; then
    pass "final root mode 2775 and expected owner"
  else
    fail "final root mode 2775 and owner uid $remote_uid"
  fi
  if [[ $roots_ok == true ]] && [[ $(stat -c %d -- "$incoming_root") == $(stat -c %d -- "$final_root") ]]; then
    pass "incoming and final roots use the same filesystem"
  else
    fail "incoming and final roots use the same filesystem"
  fi
  check_free_space "$final_root" "$minimum_remote" "Moscow"

  if [[ -f $wrapper && ! -L $wrapper ]] \
    && python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$wrapper" 2>/dev/null; then
    pass "remote wrapper parses without writing bytecode"
  else
    fail "remote wrapper exists and parses: $wrapper"
  fi
  if systemctl is-active --quiet transmission-daemon 2>/dev/null; then
    pass "existing system Transmission is active"
  else
    fail "existing system Transmission is active"
  fi
  if curl --fail --silent --show-error --max-time 5 "$abs_url" >/dev/null 2>&1; then
    pass "existing Audiobookshelf is reachable"
  else
    fail "existing Audiobookshelf is reachable"
  fi
}

echo "ReadMeABook read-only preflight: $host"
if [[ $host == um790pro ]]; then
  preflight_um790pro
else
  preflight_moscow
fi

if ((failures > 0)); then
  echo "Preflight failed: $failures check(s)"
  exit 1
fi
echo "Preflight passed"
