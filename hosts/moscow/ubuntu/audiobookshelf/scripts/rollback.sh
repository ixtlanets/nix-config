#!/usr/bin/env bash
set -euo pipefail

snapshot_id=${2:-}
if [[ ${1:-} != "--execute" || -z $snapshot_id ]]; then
  echo "rollback requires --execute <snapshot-id>" >&2
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

echo "rollback will discard Audiobookshelf progress written after snapshot $snapshot_id" >&2

{
  printf 'SNAPSHOT_ID=%q\n' "$snapshot_id"
  printf 'EXPECTED_CURRENT_IMAGE_ID=%q\n' "$EXPECTED_CURRENT_IMAGE_ID"
  printf 'EXPECTED_TARGET_IMAGE_ID=%q\n' "$EXPECTED_TARGET_IMAGE_ID"
  printf 'REMOTE_BUNDLE_DIR=%q\n' "$REMOTE_BUNDLE_DIR"
  printf 'REMOTE_STATE_DIR=%q\n' "$REMOTE_STATE_DIR"
  printf 'SOURCE_STATE_DIR=%q\n' "$SOURCE_STATE_DIR"
  printf 'MEDIA_DIR=%q\n' "$MEDIA_DIR"
  cat <<'REMOTE_SCRIPT'
set -euo pipefail

case "$REMOTE_STATE_DIR" in
  /home/nik/*) ;;
  *)
    echo "unsafe remote state directory: $REMOTE_STATE_DIR" >&2
    exit 1
    ;;
esac
case "$SOURCE_STATE_DIR" in
  /media/disk1/media/meta) ;;
  *)
    echo "unsafe production state directory: $SOURCE_STATE_DIR" >&2
    exit 1
    ;;
esac

snapshot_dir="$REMOTE_STATE_DIR/snapshots/$SNAPSHOT_ID"
active_cutover="$REMOTE_STATE_DIR/active-cutover.env"
production_compose="$REMOTE_BUNDLE_DIR/docker-compose.yml"
timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
restore_dir="$SOURCE_STATE_DIR.restore-$timestamp"
failed_dir="$SOURCE_STATE_DIR.failed-$timestamp"
rollback_failed_dir="$SOURCE_STATE_DIR.rollback-failed-$timestamp"
swapped=0

cleanup() {
  local status=$?
  trap - EXIT

  if ((status != 0 && swapped)); then
    docker stop --time 10 audiobookshelf >/dev/null 2>&1 || true
    if [[ -d $SOURCE_STATE_DIR && -d $failed_dir ]]; then
      mv "$SOURCE_STATE_DIR" "$rollback_failed_dir" || true
      mv "$failed_dir" "$SOURCE_STATE_DIR" || true
    fi
    echo "rollback failed after state swap; migrated state restoration was attempted" >&2
  fi

  exit "$status"
}
trap cleanup EXIT

[[ -f $snapshot_dir/manifest.env && -d $snapshot_dir/state && -f $snapshot_dir/files.sha256 ]] || {
  echo "rollback snapshot is incomplete: $SNAPSHOT_ID" >&2
  exit 1
}
grep -Fxq "snapshot_id=$SNAPSHOT_ID" "$snapshot_dir/manifest.env" || {
  echo "snapshot manifest ID mismatch" >&2
  exit 1
}
grep -Fxq "purpose=cutover" "$snapshot_dir/manifest.env" || {
  echo "snapshot is not a cutover snapshot" >&2
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

rollback_container=$(awk -F= '$1 == "rollback_container" { print $2; exit }' "$snapshot_dir/manifest.env")
[[ $rollback_container =~ ^audiobookshelf-2\.6\.0-rollback-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z$ ]] || {
  echo "unsafe rollback container name" >&2
  exit 1
}
[[ $(docker inspect "$rollback_container" --format '{{.Image}}') == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "rollback container image ID mismatch" >&2
  exit 1
}

(
  cd "$snapshot_dir/state"
  sha256sum -c ../files.sha256 >/dev/null
)

[[ ! -e $restore_dir && ! -e $failed_dir && ! -e $rollback_failed_dir ]] || {
  echo "rollback working directory already exists" >&2
  exit 1
}
install -d -m 0700 "$restore_dir"
tar -C "$snapshot_dir/state" -cf - . | tar -C "$restore_dir" -xf -
(
  cd "$restore_dir"
  sha256sum -c "$snapshot_dir/files.sha256" >/dev/null
)

integrity=$(DB_PATH="$restore_dir/absdatabase.sqlite" python3 - <<'PY'
import os
import sqlite3

path = "file:" + os.environ["DB_PATH"] + "?mode=ro"
connection = sqlite3.connect(path, uri=True)
connection.execute("PRAGMA query_only=ON")
print(connection.execute("PRAGMA integrity_check").fetchone()[0])
PY
)
[[ $integrity == "ok" ]] || {
  echo "restored SQLite integrity check failed" >&2
  exit 1
}

install -d -m 0700 "$REMOTE_STATE_DIR/rollback-logs"
if docker inspect audiobookshelf >/dev/null 2>&1; then
  running_image_id=$(docker inspect audiobookshelf --format '{{.Image}}')
  [[ $running_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
    echo "refusing to remove unexpected container named audiobookshelf" >&2
    exit 1
  }
  docker logs audiobookshelf >"$REMOTE_STATE_DIR/rollback-logs/$SNAPSHOT_ID.log" 2>&1 || true
fi

(
  cd "$REMOTE_BUNDLE_DIR"
  SOURCE_STATE_DIR="$SOURCE_STATE_DIR" MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf -f "$production_compose" down
)

mv "$SOURCE_STATE_DIR" "$failed_dir"
mv "$restore_dir" "$SOURCE_STATE_DIR"
swapped=1

docker rename "$rollback_container" audiobookshelf
docker start audiobookshelf >/dev/null

server_version=""
for _ in $(seq 1 120); do
  status_json=$(curl -fsS --max-time 5 http://127.0.0.1:13378/status 2>/dev/null || true)
  if [[ -n $status_json ]]; then
    server_version=$(STATUS_JSON="$status_json" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["STATUS_JSON"])
print(status.get("serverVersion") or status.get("version") or "")
PY
)
  fi
  if [[ $server_version == "2.6.0" ]]; then
    break
  fi
  sleep 1
done
[[ $server_version == "2.6.0" ]] || {
  docker logs --tail 200 audiobookshelf >&2 || true
  echo "rollback status endpoint did not report 2.6.0" >&2
  exit 1
}
[[ $(docker inspect audiobookshelf --format '{{.Image}}') == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "rollback runtime image ID mismatch" >&2
  exit 1
}

sed -i 's/^status=.*/status=rolled-back/' "$active_cutover"
cat >>"$active_cutover" <<ACTIVE
rolled_back_at=$timestamp
failed_migrated_state=$failed_dir
ACTIVE

swapped=0
printf 'rollback complete\n'
printf 'server_version=%s\n' "$server_version"
printf 'failed_migrated_state=%s\n' "$failed_dir"
REMOTE_SCRIPT
} | run_remote
