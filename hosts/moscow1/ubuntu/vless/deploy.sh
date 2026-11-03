#!/usr/bin/env bash
# First installation only, run locally by the parent on Moscow. No package/network setup.
set -Eeuo pipefail
umask 077
readonly expected_ip=132.243.191.232
readonly engine_sha=a056076cff3aa1ced5ed794743b9f87b2dee7dc068280d2665c1e0b45533e793
readonly marker='# Managed by moscow1-vless pilot'
readonly paths=(/usr/local/lib/moscow1 /etc/moscow1 /var/lib/moscow1
  /etc/systemd/system/moscow1-vless.service /etc/caddy/Caddyfile
  /etc/caddy/moscow1.json /etc/systemd/system/caddy.service.d /var/lib/caddy/moscow1)
readonly services=(nginx.service certbot.timer caddy.service moscow1-vless.service)
fail() { echo "$1" >&2; exit 1; }
all_services_active() {
  local service
  for service in "$@"; do
    systemctl is-active --quiet "$service" || return 1
  done
}
[[ $EUID == 0 ]] || fail 'Run on Moscow as root.'
ip -4 -o addr show scope global | awk '{split($4,a,"/"); print a[1]}' | grep -Fxq "$expected_ip" ||
  fail 'Refusing: this host does not own the Moscow pilot IP.'
# shellcheck source=/dev/null
. /etc/os-release
[[ $ID == ubuntu ]] || fail 'Ubuntu is required.'
[[ $# -ge 2 ]] || fail 'Usage: deploy.sh install BUNDLE BINARY BACKUP | rollback BACKUP'
mode=$1
case "$mode" in
  rollback) [[ $# == 2 ]] || fail 'Wrong argument count.'; backup=$2 ;;
  install) [[ $# == 4 ]] || fail 'Wrong argument count.'
    bundle=$(realpath -e -- "$2"); binary=$(realpath -e -- "$3"); backup=$4 ;;
  *) fail 'Unknown mode.' ;;
esac
[[ $backup =~ ^/var/backups/moscow1/[a-zA-Z0-9_-]+$ && ! -L /var/backups &&
   ! -L /var/backups/moscow1 && ! -L $backup ]] || fail 'Use a fresh direct child of /var/backups/moscow1/.'

restore() {
  [[ -f $backup/.moscow1-backup && ! -L $backup/.moscow1-backup &&
     $(cat "$backup/.moscow1-backup") == "$expected_ip" ]] || return 1
  local path service state bad=0
  # Keep going after cleanup errors so one failure does not suppress later recovery.
  systemctl stop caddy.service >>"$backup/rollback.log" 2>&1 || bad=1
  if [[ $(systemctl show -p LoadState --value moscow1-vless.service) != not-found ]]; then
    systemctl stop moscow1-vless.service >>"$backup/rollback.log" 2>&1 || bad=1
  fi
  for path in "${paths[@]}"; do
    rm -rf -- "$path" || { bad=1; continue; }
    if [[ -e $backup/before$path || -L $backup/before$path ]]; then
      mkdir -p -- "$(dirname -- "$path")" && cp -a -- "$backup/before$path" "$path" || bad=1
    fi
  done
  systemctl daemon-reload >>"$backup/rollback.log" 2>&1 || bad=1
  for service in "${services[@]}"; do
    state=$(cat "$backup/$service.enabled") || { bad=1; continue; }
    # Clear both persistent and runtime links before restoring the original form.
    if [[ $state != not-found ]]; then
      systemctl disable "$service" >>"$backup/rollback.log" 2>&1 || bad=1
      systemctl disable --runtime "$service" >>"$backup/rollback.log" 2>&1 || bad=1
    fi
    case "$state" in
      enabled) systemctl enable "$service" >>"$backup/rollback.log" 2>&1 || bad=1 ;;
      enabled-runtime) systemctl enable --runtime "$service" >>"$backup/rollback.log" 2>&1 || bad=1 ;;
      disabled|static|not-found)
        systemctl disable "$service" >>"$backup/rollback.log" 2>&1 ||
          { [[ $state == not-found || $state == static ]] || bad=1; } ;;
      *) bad=1 ;;
    esac
    state=$(cat "$backup/$service.active") || { bad=1; continue; }
    case "$state" in
      active) systemctl start "$service" >>"$backup/rollback.log" 2>&1 || bad=1 ;;
      inactive) systemctl stop "$service" >>"$backup/rollback.log" 2>&1 ||
          { [[ $service == moscow1-vless.service ]] || bad=1; } ;;
      *) bad=1 ;;
    esac
  done
  # Only remove an account/group created by this transaction, never a preexisting one.
  if [[ -f $backup/created-user ]]; then deluser moscow1 >>"$backup/rollback.log" 2>&1 || bad=1; fi
  if [[ -f $backup/created-group ]] && getent group moscow1 >/dev/null; then
    delgroup moscow1 >>"$backup/rollback.log" 2>&1 || bad=1
  fi
  return "$bad"
} >>"$backup/rollback.log" 2>&1
if [[ $mode == rollback ]]; then
  [[ -d $backup && $(stat -c '%u:%a' -- "$backup" 2>/dev/null) == 0:700 ]] ||
    fail 'Rollback requires a root-owned private backup directory.'
  restore || fail 'Rollback incomplete; inspect the private backup and recover remaining items.'
  echo 'Task files and prior service states restored; verify nginx TLS independently.'
  exit 0
fi

for command in caddy curl nginx sha256sum python3; do command -v "$command" >/dev/null || fail 'Missing prerequisite.'; done
[[ $(command -v caddy) == /usr/bin/caddy ]] || fail 'Use the official Ubuntu caddy package at /usr/bin/caddy.'
for package in caddy nginx certbot; do
  [[ $(dpkg-query -W -f='${Status}' "$package") == 'install ok installed' ]] || fail 'Required package missing.'
done
# Parent verifies apt origin and backs up/removes the packaged default separately.
# Even a stock-looking file is not adopted by guessing its contents.
for path in "${paths[@]}"; do
  [[ ! -e $path && ! -L $path ]] || fail 'Refusing to overwrite an existing task path (including Caddyfile).'
done
for path in /usr/local/lib /etc/caddy /var/lib/caddy /etc/systemd/system /etc/systemd/system/caddy.service.d; do
  [[ ! -L $path ]] || fail 'Refusing symlinked parent directory.'
done
[[ -d /etc/caddy && -d /var/lib/caddy ]] || fail 'Install the official Ubuntu Caddy package first.'
[[ ! -e /run/systemd/system/moscow1-vless.service && ! -e /lib/systemd/system/moscow1-vless.service &&
   ! -d /etc/systemd/system/moscow1-vless.service.d ]] || fail 'Unmanaged Moscow unit exists.'
[[ ! -e /run/systemd/system/caddy.service && ! -e /etc/systemd/system/caddy.service &&
   ! -d /run/systemd/system/caddy.service.d ]] || fail 'Unexpected Caddy unit override.'
# Create private diagnostics before inspecting any potentially token-bearing tree.
install -d -m 0700 /var/backups/moscow1
mkdir -m 0700 -- "$backup"
if [[ -d /etc/systemd/system/caddy.service.d ]]; then
  dropin=$(find /etc/systemd/system/caddy.service.d -mindepth 1 -print -quit 2>>"$backup/filesystem.log") ||
    fail 'Unable to inspect Caddy drop-ins; inspect private diagnostics.'
  [[ -z $dropin ]] || fail 'Unexpected Caddy drop-in.'
fi
getent passwd caddy >/dev/null && getent group caddy >/dev/null || fail 'Packaged caddy account is required.'
[[ $(sha256sum "$binary" | cut -d' ' -f1) == "$engine_sha" ]] || fail 'Pinned binary checksum mismatch.'
for file in server.json Caddyfile moscow1-vless.service caddy-override.conf; do
  [[ -f $bundle/$file && ! -L $bundle/$file ]] || fail 'Incomplete bundle.'
done
for file in Caddyfile moscow1-vless.service caddy-override.conf; do
  [[ $(head -n1 "$bundle/$file") == "$marker" ]] || fail 'Missing managed marker.'
done
[[ -d $bundle/subscriptions && ! -L $bundle/subscriptions ]] || fail 'Invalid subscription tree.'
invalid_subscription=$(find "$bundle/subscriptions" ! -type f ! -type d -print -quit \
  2>>"$backup/filesystem.log") || fail 'Unable to inspect subscriptions; inspect private diagnostics.'
[[ -z $invalid_subscription ]] || fail 'Invalid subscription tree.'
if getent passwd moscow1 >/dev/null; then
  IFS=: read -r _ _ account_uid account_gid _ account_home account_shell <<<"$(getent passwd moscow1)"
  [[ $account_uid -gt 0 && $account_uid -lt 1000 && $account_home == /nonexistent &&
     $account_shell == /usr/sbin/nologin && $(getent group moscow1 | cut -d: -f3) == "$account_gid" ]] ||
    fail 'Existing moscow1 account is not dedicated.'
fi
if getent group moscow1 >/dev/null; then
  IFS=: read -r _ _ group_gid group_members <<<"$(getent group moscow1)"
  [[ $group_gid -gt 0 && $group_gid -lt 1000 && -z $group_members ]] || fail 'Existing moscow1 group is not private.'
fi

mkdir -m 0700 "$backup/before"
for path in "${paths[@]}"; do
  if [[ -e $path || -L $path ]]; then
    cp -a --parents -- "$path" "$backup/before/" >>"$backup/filesystem.log" 2>&1 ||
      fail 'Snapshot failed; inspect private diagnostics.'
  fi
done
# Snapshot exact stable states; reject masked/transitional/exotic states before mutations.
for service in "${services[@]}"; do
  state=$(systemctl is-enabled "$service" 2>/dev/null) || true
  [[ -n $state ]] || state=not-found
  case "$state" in enabled|enabled-runtime|disabled|static|not-found) ;; *) fail 'Unsupported prior enable state.' ;; esac
  printf '%s\n' "$state" >"$backup/$service.enabled"
  state=$(systemctl is-active "$service" 2>/dev/null) || true
  case "$state" in active|inactive) ;; *) fail 'Unsupported prior active state.' ;; esac
  printf '%s\n' "$state" >"$backup/$service.active"
done
[[ $(cat "$backup/nginx.service.active") == active &&
   $(cat "$backup/certbot.timer.enabled") == enabled &&
   $(cat "$backup/caddy.service.active") == inactive &&
   $(cat "$backup/moscow1-vless.service.active") == inactive ]] || fail 'Unexpected initial service state.'
[[ $(cat "$backup/caddy.service.enabled") != not-found ]] || fail 'Packaged caddy.service is missing.'
printf '%s\n' "$expected_ip" >"$backup/.moscow1-backup"
next_config=''
rollback_on_failure() {
  local code=$1
  trap - ERR INT TERM
  echo 'Install interrupted/failed; restoring task files and prior service states.' >&2
  if [[ -n ${next_config:-} ]]; then
    rm -f -- "$next_config" >>"$backup/rollback.log" 2>&1 ||
      echo 'Temporary Caddyfile cleanup failed; inspect /etc/caddy privately.' >&2
  fi
  restore >>"$backup/rollback.log" 2>&1 || echo 'Rollback incomplete; inspect the private backup.' >&2
  exit "$code"
}
trap 'rollback_on_failure $?' ERR
trap 'rollback_on_failure 130' INT
trap 'rollback_on_failure 143' TERM
# All diagnostic output is private: adapters/validators may print token-bearing config.
nginx -t >"$backup/nginx-check.log" 2>&1
"$binary" check -c "$bundle/server.json" >"$backup/sing-box-check.log" 2>&1
python3 "$(dirname -- "$0")/adapt-caddy.py" "$bundle/Caddyfile" "$backup/caddy.json" >"$backup/caddy-adapt.log" 2>&1
/usr/bin/caddy validate --config "$backup/caddy.json" >"$backup/caddy-check.log" 2>&1
if ! getent group moscow1 >/dev/null; then
  touch "$backup/created-group"
  addgroup --system moscow1 >"$backup/account.log" 2>&1
fi
if ! getent passwd moscow1 >/dev/null; then
  touch "$backup/created-user"
  adduser --system --ingroup moscow1 --no-create-home --home /nonexistent --shell /usr/sbin/nologin moscow1 >>"$backup/account.log" 2>&1
fi
install -d -o root -g moscow1 -m 0750 /etc/moscow1
install -d -o root -g root -m 0755 /usr/local/lib/moscow1 /var/lib/moscow1
install -d -o caddy -g caddy -m 0700 /var/lib/caddy/moscow1
install -d -m 0755 /etc/systemd/system/caddy.service.d
install -o root -g root -m 0755 "$binary" /usr/local/lib/moscow1/sing-box
install -o root -g moscow1 -m 0640 "$bundle/server.json" /etc/moscow1/server.json
install -o root -g root -m 0644 "$bundle/moscow1-vless.service" /etc/systemd/system/moscow1-vless.service
install -o root -g root -m 0644 "$bundle/caddy-override.conf" /etc/systemd/system/caddy.service.d/moscow1-vless.conf
install -o root -g caddy -m 0640 "$backup/caddy.json" /etc/caddy/moscow1.json
cp -a "$bundle/subscriptions" /var/lib/moscow1/subscriptions >>"$backup/filesystem.log" 2>&1
chown -R root:caddy /var/lib/moscow1/subscriptions >>"$backup/filesystem.log" 2>&1
find /var/lib/moscow1/subscriptions -type d -exec chmod 0750 {} + >>"$backup/filesystem.log" 2>&1
find /var/lib/moscow1/subscriptions -type f -exec chmod 0640 {} + >>"$backup/filesystem.log" 2>&1
# The candidate was validated before the cutover; publish its protected inode atomically.
next_config=$(mktemp /etc/caddy/.moscow1.XXXXXX)
install -o root -g caddy -m 0640 "$bundle/Caddyfile" "$next_config"
mv -fT -- "$next_config" /etc/caddy/Caddyfile
next_config=''
systemctl daemon-reload
systemctl stop certbot.timer nginx.service >"$backup/stop.log" 2>&1
systemctl start caddy.service moscow1-vless.service >"$backup/start.log" 2>&1
# Trust system CAs and verify hostname+TLS against loopback. Never -k or token URLs.
healthy=0
for ((attempt=0; attempt<180; attempt++)); do
  if [[ $(curl --silent --show-error --fail --noproxy '*' --connect-timeout 2 --max-time 5 \
    --resolve moscow1.nikcode.xyz:443:127.0.0.1 https://moscow1.nikcode.xyz/healthz \
    2>>"$backup/health.log") == ok ]] && all_services_active caddy.service moscow1-vless.service; then
    healthy=1; break
  fi
  sleep 2
done
[[ $healthy == 1 ]]
# Success gate: only now change boot policy. No package purge or letsencrypt writes.
systemctl disable nginx.service certbot.timer >"$backup/disable.log" 2>&1
systemctl enable caddy.service moscow1-vless.service >"$backup/enable.log" 2>&1
# Read back each unit independently before accepting the completed transaction.
all_services_active caddy.service moscow1-vless.service
for service in caddy.service moscow1-vless.service; do
  [[ $(systemctl is-enabled "$service") == enabled ]]
done
for service in nginx.service certbot.timer; do
  [[ $(systemctl is-active "$service" || true) == inactive ]]
  [[ $(systemctl is-enabled "$service" || true) == disabled ]]
done
trap - ERR INT TERM
echo 'Caddy TLS/health passed; pilot installed. Native VLESS and client acceptance remain required.'
