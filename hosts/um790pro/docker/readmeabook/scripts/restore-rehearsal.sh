#!/usr/bin/env bash

set -euo pipefail

backup=
execute=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup)
      if [[ $# -lt 2 ]]; then
        echo "--backup requires a path" >&2
        exit 2
      fi
      backup=$2
      shift 2
      ;;
    --execute)
      execute=true
      shift
      ;;
    *)
      echo "usage: $0 --backup PATH [--execute]" >&2
      exit 2
      ;;
  esac
done

if [[ -z $backup ]]; then
  echo "usage: $0 --backup PATH [--execute]" >&2
  exit 2
fi
if [[ ! -d $backup || -L $backup ]]; then
  echo "backup is missing or unsafe: $backup" >&2
  exit 1
fi
backup=$(realpath -- "$backup")
for required in postgres.dump SHA256SUMS publisher-state/ledger.json; do
  if [[ ! -f $backup/$required || -L $backup/$required ]]; then
    echo "backup artifact is missing or unsafe: $required" >&2
    exit 1
  fi
done

rehearsal_root=${READMABOOK_REHEARSAL_ROOT:-/home/nik/.local/state/readmeabook-restore-rehearsals}
docker_bin=${READMABOOK_DOCKER_BIN:-docker}
postgres_image=${READMABOOK_RESTORE_POSTGRES_IMAGE:-postgres:16-bookworm@sha256:bb3e1a57e5407e0a5280b4211980a5e537f4abd234a87014ac979849a78dd825}
production_state=$(realpath -m -- "${READMABOOK_STATE_ROOT:-/home/nik/services/readmeabook}")
production_final=$(realpath -m -- "${READMABOOK_FINAL_ROOT:-/media/disk1/media/ReadMeABook}")
rehearsal_root=$(realpath -m -- "$rehearsal_root")
for forbidden in / "$production_state" "$production_final" "$backup"; do
  case "$rehearsal_root/" in
    "$forbidden/"|"$forbidden/"*)
      echo "unsafe rehearsal root: $rehearsal_root" >&2
      exit 1
      ;;
  esac
done

echo "ReadMeABook restore rehearsal preview"
echo "  backup: $backup"
echo "  disposable destination: $rehearsal_root"
echo "  production paths are never accepted as a destination"
if [[ $execute != true ]]; then
  echo "No files or containers created; pass --execute to run the rehearsal."
  exit 0
fi

mkdir -p -- "$rehearsal_root"
chmod 700 -- "$rehearsal_root"
rehearsal_root=$(realpath -- "$rehearsal_root")

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final="$rehearsal_root/$timestamp"
partial="$rehearsal_root/.partial-$timestamp-$$"
if [[ -e $final || -e $partial ]]; then
  echo "rehearsal destination already exists" >&2
  exit 1
fi
container="readmeabook-restore-$$"
container_started=false
cleanup() {
  if [[ $container_started == true ]]; then
    "$docker_bin" rm -f "$container" >/dev/null 2>&1 || true
  fi
  if [[ -n ${partial:-} && $partial == "$rehearsal_root/.partial-"* ]]; then
    rm -rf -- "$partial"
  fi
}
trap cleanup EXIT

(
  cd -- "$backup"
  sha256sum --check SHA256SUMS
)
python3 -m json.tool "$backup/publisher-state/ledger.json" >/dev/null
install -d -m 700 -- "$partial"
cp -a -- "$backup/." "$partial/"

"$docker_bin" run --rm -d \
  --name "$container" \
  --network none \
  -e POSTGRES_PASSWORD=rehearsal-only \
  -e POSTGRES_DB=readmeabook \
  "$postgres_image" >/dev/null
container_started=true
ready=false
for _attempt in $(seq 1 30); do
  if "$docker_bin" exec "$container" pg_isready -U postgres >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ $ready != true ]]; then
  echo "disposable PostgreSQL did not become ready" >&2
  exit 1
fi
"$docker_bin" exec -i "$container" \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  -U postgres -d readmeabook <"$backup/postgres.dump"
"$docker_bin" exec "$container" \
  psql -U postgres -d readmeabook -Atqc 'select 1' >/dev/null
"$docker_bin" rm -f "$container" >/dev/null
container_started=false

mv -- "$partial" "$final"
trap - EXIT
echo "Restore rehearsal passed: $final"
