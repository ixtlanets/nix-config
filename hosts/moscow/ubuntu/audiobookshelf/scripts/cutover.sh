#!/usr/bin/env bash
set -euo pipefail

rehearsal_id=${2:-}
if [[ ${1:-} != "--execute" || -z $rehearsal_id ]]; then
  echo "cutover requires --execute <rehearsal-id>" >&2
  exit 2
fi
if [[ ! $rehearsal_id =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-(rehearsal|cutover)$ ]]; then
  echo "invalid rehearsal ID: $rehearsal_id" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

"$SCRIPT_DIR/preflight.sh" --allow-rehearsal
sync_bundle

echo "--execute confirms that the service baseline passed for rehearsal $rehearsal_id"

{
  printf 'REHEARSAL_ID=%q\n' "$rehearsal_id"
  printf 'EXPECTED_CURRENT_IMAGE_ID=%q\n' "$EXPECTED_CURRENT_IMAGE_ID"
  printf 'EXPECTED_TARGET_IMAGE_ID=%q\n' "$EXPECTED_TARGET_IMAGE_ID"
  printf 'DEPLOYMENT_IMAGE=%q\n' "$DEPLOYMENT_IMAGE"
  printf 'REMOTE_BUNDLE_DIR=%q\n' "$REMOTE_BUNDLE_DIR"
  printf 'REMOTE_STATE_DIR=%q\n' "$REMOTE_STATE_DIR"
  printf 'SOURCE_STATE_DIR=%q\n' "$SOURCE_STATE_DIR"
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

timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
snapshot_id="$timestamp-cutover"
snapshots_dir="$REMOTE_STATE_DIR/snapshots"
snapshot_dir="$snapshots_dir/$snapshot_id"
partial_dir="$snapshot_dir.partial"
rehearsal_dir="$REMOTE_STATE_DIR/rehearsals/$REHEARSAL_ID"
rollback_container="audiobookshelf-2.6.0-rollback-$timestamp"
production_compose="$REMOTE_BUNDLE_DIR/docker-compose.yml"
rehearsal_compose="$REMOTE_BUNDLE_DIR/docker-compose.rehearsal.yml"

old_stopped=0
old_renamed=0
migration_started=0

cleanup() {
  local status=$?
  trap - EXIT

  if ((status != 0)); then
    if ((migration_started)); then
      (
        cd "$REMOTE_BUNDLE_DIR"
        SOURCE_STATE_DIR="$SOURCE_STATE_DIR" MEDIA_DIR="$MEDIA_DIR" \
          docker-compose -p audiobookshelf -f "$production_compose" down
      ) >/dev/null 2>&1 || true
      echo "cutover failed after migration began; run rollback.sh --execute $snapshot_id" >&2
    else
      if ((old_renamed)); then
        docker rename "$rollback_container" audiobookshelf >/dev/null 2>&1 || true
      fi
      if ((old_stopped)); then
        docker start audiobookshelf >/dev/null 2>&1 || true
      fi
      if [[ -n ${partial_dir:-} && $partial_dir == "$snapshots_dir/"*.partial ]]; then
        rm -rf -- "$partial_dir"
      fi
      echo "cutover failed before migration; old production restart was attempted" >&2
    fi
  fi

  exit "$status"
}
trap cleanup EXIT

[[ -f $rehearsal_dir/rehearsal.env ]] || {
  echo "rehearsal report is missing: $REHEARSAL_ID" >&2
  exit 1
}
grep -Fxq "snapshot_id=$REHEARSAL_ID" "$rehearsal_dir/rehearsal.env" || {
  echo "rehearsal report ID mismatch" >&2
  exit 1
}
grep -Fxq "image_id=$EXPECTED_TARGET_IMAGE_ID" "$rehearsal_dir/rehearsal.env" || {
  echo "rehearsal image verification is missing" >&2
  exit 1
}
grep -Fxq "server_version=2.36.0" "$rehearsal_dir/rehearsal.env" || {
  echo "rehearsal version verification is missing" >&2
  exit 1
}
[[ $(docker inspect audiobookshelf-rehearsal --format '{{.Image}}') == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "rehearsal runtime image ID mismatch" >&2
  exit 1
}
rehearsal_status=$(curl -fsS --max-time 5 "http://$TAILSCALE_IP:13379/status")
rehearsal_version=$(STATUS_JSON="$rehearsal_status" python3 - <<'PY'
import json
import os

status = json.loads(os.environ["STATUS_JSON"])
print(status.get("serverVersion") or status.get("version") or "")
PY
)
[[ $rehearsal_version == "2.36.0" ]] || {
  echo "rehearsal status endpoint did not report 2.36.0" >&2
  exit 1
}

[[ $(docker inspect audiobookshelf --format '{{.Image}}') == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "production image fingerprint changed" >&2
  exit 1
}
[[ $(docker image inspect "$DEPLOYMENT_IMAGE" --format '{{.Id}}') == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "deployment image ID mismatch" >&2
  exit 1
}
[[ ! -e $snapshot_dir && ! -e $partial_dir ]] || {
  echo "cutover snapshot ID already exists: $snapshot_id" >&2
  exit 1
}

(
  cd "$REMOTE_BUNDLE_DIR"
  REHEARSAL_STATE_DIR="$rehearsal_dir/state" \
    TAILSCALE_IP="$TAILSCALE_IP" \
    MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf-rehearsal -f "$rehearsal_compose" down
)

install -d -m 0700 "$REMOTE_STATE_DIR" "$snapshots_dir" "$partial_dir" "$partial_dir/state"

docker stop --time 30 audiobookshelf >/dev/null
old_stopped=1

tar -C "$SOURCE_STATE_DIR" -cf - . | tar -C "$partial_dir/state" -xf -
# Extracting `.` restores the source directory mode on the destination root.
chmod 0700 "$partial_dir" "$partial_dir/state"

integrity=$(DB_PATH="$partial_dir/state/absdatabase.sqlite" python3 - <<'PY'
import os
import sqlite3

path = "file:" + os.environ["DB_PATH"] + "?mode=ro"
connection = sqlite3.connect(path, uri=True)
connection.execute("PRAGMA query_only=ON")
print(connection.execute("PRAGMA integrity_check").fetchone()[0])
PY
)
[[ $integrity == "ok" ]] || {
  echo "cutover snapshot SQLite integrity check failed" >&2
  exit 1
}

(
  cd "$partial_dir/state"
  find . -type f -print0 | sort -z | xargs -0 sha256sum
) >"$partial_dir/files.sha256"

db_sha256=$(sha256sum "$partial_dir/state/absdatabase.sqlite" | awk '{print $1}')
files_manifest_sha256=$(sha256sum "$partial_dir/files.sha256" | awk '{print $1}')
cat >"$partial_dir/manifest.env" <<MANIFEST
snapshot_id=$snapshot_id
purpose=cutover
created_at=$timestamp
source_state_dir=$SOURCE_STATE_DIR
current_image_id=$EXPECTED_CURRENT_IMAGE_ID
database_sha256=$db_sha256
files_manifest_sha256=$files_manifest_sha256
rollback_container=$rollback_container
MANIFEST
mv "$partial_dir" "$snapshot_dir"

docker rename audiobookshelf "$rollback_container"
old_renamed=1

cat >"$REMOTE_STATE_DIR/active-cutover.env" <<ACTIVE
snapshot_id=$snapshot_id
rehearsal_id=$REHEARSAL_ID
rollback_container=$rollback_container
target_image_id=$EXPECTED_TARGET_IMAGE_ID
started_at=$timestamp
status=migration-pending
ACTIVE
chmod 0600 "$REMOTE_STATE_DIR/active-cutover.env"

migration_started=1
(
  cd "$REMOTE_BUNDLE_DIR"
  SOURCE_STATE_DIR="$SOURCE_STATE_DIR" MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf -f "$production_compose" config >/dev/null
  SOURCE_STATE_DIR="$SOURCE_STATE_DIR" MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf -f "$production_compose" up -d --no-build
)

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
  if [[ $server_version == "2.36.0" ]]; then
    break
  fi
  sleep 1
done
[[ $server_version == "2.36.0" ]] || {
  docker logs --tail 200 audiobookshelf >&2 || true
  echo "production status endpoint did not report 2.36.0" >&2
  exit 1
}

runtime_image_id=$(docker inspect audiobookshelf --format '{{.Image}}')
[[ $runtime_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "production runtime image ID mismatch" >&2
  exit 1
}

sqlite_integrity=$(docker exec audiobookshelf node -e '
const sqlite3 = require("/app/node_modules/sqlite3")
const database = new sqlite3.Database("/config/absdatabase.sqlite", sqlite3.OPEN_READONLY)
database.get("PRAGMA integrity_check", (error, row) => {
  if (error) {
    console.error(error)
    process.exitCode = 1
  } else {
    console.log(Object.values(row)[0])
  }
  database.close()
})
')
[[ $sqlite_integrity == "ok" ]] || {
  echo "production SQLite integrity check failed" >&2
  exit 1
}

sed -i 's/^status=.*/status=baseline-pending/' "$REMOTE_STATE_DIR/active-cutover.env"
cat >>"$REMOTE_STATE_DIR/active-cutover.env" <<ACTIVE
server_version=$server_version
production_image_id=$runtime_image_id
sqlite_integrity=$sqlite_integrity
rollback_window_ends_after=24h-manual-baseline
retain_until_at_least=7d
ACTIVE

printf 'cutover ready for service baseline\n'
printf 'snapshot_id=%s\n' "$snapshot_id"
printf 'rollback_container=%s\n' "$rollback_container"
printf 'server_version=%s\n' "$server_version"
REMOTE_SCRIPT
} | run_remote
