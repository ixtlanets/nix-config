#!/usr/bin/env bash

set -euo pipefail

execute=false
if [[ ${1:-} == "--execute" && $# -eq 1 ]]; then
  execute=true
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--execute]" >&2
  exit 2
fi

state_root=${READMABOOK_STATE_ROOT:-/home/nik/services/readmeabook}
publisher_state=${READMABOOK_PUBLISHER_STATE_DIR:-/home/nik/.local/state/readmeabook-publisher}
operator_config=${READMABOOK_OPERATOR_CONFIG_DIR:-/home/nik/.config/readmeabook}
secrets_root=${READMABOOK_SECRETS_ROOT:-/etc/readmeabook/secrets}
backup_root=${READMABOOK_BACKUP_ROOT:-/var/backups/readmeabook}
docker_bin=${READMABOOK_DOCKER_BIN:-docker}

echo "ReadMeABook backup preview"
echo "  state: $state_root/{rmab/config,prowlarr,transmission,flaresolverr}"
echo "  publisher: $publisher_state"
echo "  operator config: $operator_config"
echo "  secrets: $secrets_root"
echo "  destination: $backup_root"
echo "  excluded: $state_root/{downloads,staging,rmab/pgdata,rmab/redis}"

if [[ $execute != true ]]; then
  echo "No files written; pass --execute to create the backup."
  exit 0
fi

for required in \
  "$state_root/rmab/config" \
  "$state_root/prowlarr" \
  "$state_root/transmission" \
  "$state_root/flaresolverr" \
  "$publisher_state" \
  "$operator_config" \
  "$secrets_root"; do
  if [[ ! -d $required || -L $required ]]; then
    echo "required backup source is missing or unsafe: $required" >&2
    exit 1
  fi
done

mkdir -p -- "$backup_root"
chmod 700 -- "$backup_root"
backup_root=$(realpath -- "$backup_root")
state_root=$(realpath -- "$state_root")
case "$backup_root/" in
  "//"|"$state_root/"|"$state_root/"*)
    echo "unsafe backup root: $backup_root" >&2
    exit 1
    ;;
esac

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final="$backup_root/$timestamp"
partial="$backup_root/.partial-$timestamp-$$"
sums="$backup_root/.sums-$timestamp-$$"
if [[ -e $final || -e $partial ]]; then
  echo "backup destination already exists" >&2
  exit 1
fi

paused=false
cleanup() {
  if [[ $paused == true ]]; then
    "$docker_bin" unpause readmeabook readmeabook-flaresolverr readmeabook-rutracker-gateway readmeabook-prowlarr readmeabook-transmission >/dev/null 2>&1 || true
  fi
  if [[ -n ${partial:-} && $partial == "$backup_root/.partial-"* ]]; then
    rm -rf -- "$partial"
  fi
  if [[ -n ${sums:-} && $sums == "$backup_root/.sums-"* ]]; then
    rm -f -- "$sums"
  fi
}
trap cleanup EXIT

install -d -m 700 -- "$partial" "$partial/state/rmab"
"$docker_bin" exec readmeabook sh -c \
  'PGPASSWORD=$(cat /run/secrets/rmab-postgres-password) exec pg_dump -Fc -U readmeabook readmeabook' \
  >"$partial/postgres.dump"

"$docker_bin" pause readmeabook readmeabook-flaresolverr readmeabook-rutracker-gateway readmeabook-prowlarr readmeabook-transmission >/dev/null
paused=true
cp -a -- "$state_root/rmab/config" "$partial/state/rmab/config"
cp -a -- "$state_root/prowlarr" "$partial/state/prowlarr"
cp -a -- "$state_root/transmission" "$partial/state/transmission"
cp -a -- "$state_root/flaresolverr" "$partial/state/flaresolverr"
cp -a -- "$publisher_state" "$partial/publisher-state"
cp -a -- "$operator_config" "$partial/operator-config"
cp -a -- "$secrets_root" "$partial/secrets"
"$docker_bin" inspect \
  --format '{{.Name}} {{.Config.Image}} {{.Image}}' \
  readmeabook readmeabook-flaresolverr readmeabook-rutracker-gateway readmeabook-prowlarr readmeabook-transmission \
  >"$partial/images.txt"
"$docker_bin" unpause readmeabook readmeabook-flaresolverr readmeabook-rutracker-gateway readmeabook-prowlarr readmeabook-transmission >/dev/null
paused=false

(
  cd -- "$partial"
  find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) >"$sums"
mv -- "$sums" "$partial/SHA256SUMS"
chmod 600 -- "$partial/SHA256SUMS" "$partial/postgres.dump" "$partial/images.txt"
mv -- "$partial" "$final"
trap - EXIT
echo "Backup created: $final"
