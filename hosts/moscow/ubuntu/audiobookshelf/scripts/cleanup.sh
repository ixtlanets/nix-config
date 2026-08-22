#!/usr/bin/env bash
set -euo pipefail

snapshot_id=${2:-}
if [[ ${1:-} != "--execute" || -z $snapshot_id ]]; then
  echo "cleanup requires --execute <cutover-snapshot-id>" >&2
  exit 2
fi
if [[ ! $snapshot_id =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-cutover$ ]]; then
  echo "invalid snapshot ID: $snapshot_id" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

sync_bundle

{
  printf 'SNAPSHOT_ID=%q\n' "$snapshot_id"
  printf 'EXPECTED_TARGET_IMAGE_ID=%q\n' "$EXPECTED_TARGET_IMAGE_ID"
  printf 'EXPECTED_CURRENT_IMAGE_ID=%q\n' "$EXPECTED_CURRENT_IMAGE_ID"
  printf 'REMOTE_BUNDLE_DIR=%q\n' "$REMOTE_BUNDLE_DIR"
  printf 'REMOTE_STATE_DIR=%q\n' "$REMOTE_STATE_DIR"
  printf 'MEDIA_DIR=%q\n' "$MEDIA_DIR"
  printf 'TAILSCALE_IP=%q\n' "$TAILSCALE_IP"
  cat <<'REMOTE_SCRIPT'
set -euo pipefail

case "$REMOTE_STATE_DIR" in
  /home/nik/*) ;;
  *)
    echo "unsafe remote state directory: $REMOTE_STATE_DIR" >&2
    exit 1
    ;;
esac

snapshot_dir="$REMOTE_STATE_DIR/snapshots/$SNAPSHOT_ID"
active_cutover="$REMOTE_STATE_DIR/active-cutover.env"
rehearsal_compose="$REMOTE_BUNDLE_DIR/docker-compose.rehearsal.yml"

[[ -f $snapshot_dir/manifest.env && -f $snapshot_dir/files.sha256 ]] || {
  echo "verified snapshot is missing: $SNAPSHOT_ID" >&2
  exit 1
}
[[ -f $active_cutover ]] || {
  echo "active cutover record is missing" >&2
  exit 1
}
grep -Fxq "snapshot_id=$SNAPSHOT_ID" "$active_cutover" || {
  echo "active cutover snapshot mismatch" >&2
  exit 1
}

snapshot_timestamp=${SNAPSHOT_ID%-cutover}
date_part=${snapshot_timestamp%%T*}
time_part=${snapshot_timestamp#*T}
time_part=${time_part%Z}
time_part=${time_part//-/:}
snapshot_epoch=$(date -u -d "$date_part $time_part UTC" +%s)
now_epoch=$(date -u +%s)
age_seconds=$((now_epoch - snapshot_epoch))
((age_seconds >= 604800)) || {
  echo "cleanup refused: cutover snapshot is less than 7 days old" >&2
  exit 1
}

[[ $(docker inspect audiobookshelf --format '{{.Image}}') == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "production image ID mismatch" >&2
  exit 1
}

status_json=$(curl -fsS --max-time 5 http://127.0.0.1:13378/status)
server_version=$(STATUS_JSON="$status_json" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["STATUS_JSON"])
print(status.get("serverVersion") or status.get("version") or "")
PY
)
[[ $server_version == "2.36.0" ]] || {
  echo "unexpected production server version: $server_version" >&2
  exit 1
}

rollback_container=$(awk -F= '$1 == "rollback_container" { print $2; exit }' "$snapshot_dir/manifest.env")
[[ $rollback_container =~ ^audiobookshelf-2\.6\.0-rollback-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$ ]] || {
  echo "unsafe rollback container name" >&2
  exit 1
}
[[ $(docker inspect "$rollback_container" --format '{{.Image}}') == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "rollback container image ID mismatch" >&2
  exit 1
}
[[ $(docker inspect "$rollback_container" --format '{{.State.Running}}') == "false" ]] || {
  echo "rollback container is unexpectedly running" >&2
  exit 1
}

rehearsal_id=$(awk -F= '$1 == "rehearsal_id" { print $2; exit }' "$active_cutover")
[[ $rehearsal_id =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-(rehearsal|cutover)$ ]] || {
  echo "unsafe rehearsal ID" >&2
  exit 1
}
rehearsal_dir="$REMOTE_STATE_DIR/rehearsals/$rehearsal_id"

if docker inspect audiobookshelf-rehearsal >/dev/null 2>&1; then
  [[ $(docker inspect audiobookshelf-rehearsal --format '{{.Image}}') == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
    echo "refusing to remove unexpected rehearsal container" >&2
    exit 1
  }
  (
    cd "$REMOTE_BUNDLE_DIR"
    REHEARSAL_STATE_DIR="$rehearsal_dir/state" \
      TAILSCALE_IP="$TAILSCALE_IP" \
      MEDIA_DIR="$MEDIA_DIR" \
      docker-compose -p audiobookshelf-rehearsal -f "$rehearsal_compose" down
  )
fi

docker rm "$rollback_container"
if [[ -d $rehearsal_dir && $rehearsal_dir == "$REMOTE_STATE_DIR/rehearsals/$rehearsal_id" ]]; then
  rm -rf -- "$rehearsal_dir"
fi

sed -i 's/^status=.*/status=stable/' "$active_cutover"
printf 'cleaned_at=%s\n' "$(date -u +%Y-%m-%dT%H-%M-%SZ)" >>"$active_cutover"

printf 'cleanup complete; retained verified snapshot and old image\n'
printf 'retained_snapshot=%s\n' "$snapshot_dir"
printf 'retained_old_image_id=%s\n' "$EXPECTED_CURRENT_IMAGE_ID"
REMOTE_SCRIPT
} | run_remote
