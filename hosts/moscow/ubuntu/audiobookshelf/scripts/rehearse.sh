#!/usr/bin/env bash
set -euo pipefail

snapshot_id=${1:-}
if [[ -z $snapshot_id ]]; then
  echo "usage: rehearse.sh <snapshot-id>" >&2
  exit 2
fi
if [[ ! $snapshot_id =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z-(rehearsal|cutover)$ ]]; then
  echo "invalid snapshot ID: $snapshot_id" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

"$SCRIPT_DIR/preflight.sh"
sync_bundle

{
  printf 'SNAPSHOT_ID=%q\n' "$snapshot_id"
  printf 'EXPECTED_TARGET_IMAGE_ID=%q\n' "$EXPECTED_TARGET_IMAGE_ID"
  printf 'DEPLOYMENT_IMAGE=%q\n' "$DEPLOYMENT_IMAGE"
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
rehearsal_dir="$REMOTE_STATE_DIR/rehearsals/$SNAPSHOT_ID"
rehearsal_partial="$rehearsal_dir.partial"
compose_file="$REMOTE_BUNDLE_DIR/docker-compose.rehearsal.yml"
started=0

cleanup() {
  local status=$?
  trap - EXIT

  if ((status != 0)); then
    if ((started)); then
      (
        cd "$REMOTE_BUNDLE_DIR"
        REHEARSAL_STATE_DIR="$rehearsal_dir/state" \
          TAILSCALE_IP="$TAILSCALE_IP" \
          MEDIA_DIR="$MEDIA_DIR" \
          docker-compose -p audiobookshelf-rehearsal -f "$compose_file" down
      ) >/dev/null 2>&1 || true
    fi
    if [[ -n ${rehearsal_partial:-} && $rehearsal_partial == "$REMOTE_STATE_DIR/rehearsals/"*.partial ]]; then
      rm -rf -- "$rehearsal_partial"
    fi
    echo "upgrade rehearsal failed; production was not changed" >&2
  fi

  exit "$status"
}
trap cleanup EXIT

[[ -f $snapshot_dir/manifest.env && -d $snapshot_dir/state ]] || {
  echo "snapshot is incomplete: $SNAPSHOT_ID" >&2
  exit 1
}
grep -Fxq "snapshot_id=$SNAPSHOT_ID" "$snapshot_dir/manifest.env" || {
  echo "snapshot manifest ID mismatch" >&2
  exit 1
}
[[ ! -e $rehearsal_dir && ! -e $rehearsal_partial ]] || {
  echo "rehearsal already exists: $SNAPSHOT_ID" >&2
  exit 1
}
if docker inspect audiobookshelf-rehearsal >/dev/null 2>&1; then
  echo "container audiobookshelf-rehearsal already exists" >&2
  exit 1
fi

image_id=$(docker image inspect "$DEPLOYMENT_IMAGE" --format '{{.Id}}')
[[ $image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "deployment image ID mismatch" >&2
  exit 1
}

(
  cd "$snapshot_dir/state"
  sha256sum -c ../files.sha256 >/dev/null
)

install -d -m 0700 \
  "$REMOTE_STATE_DIR" \
  "$REMOTE_STATE_DIR/rehearsals" \
  "$rehearsal_partial" \
  "$rehearsal_partial/state"
tar -C "$snapshot_dir/state" -cf - . | tar -C "$rehearsal_partial/state" -xf -
# Extracting `.` restores the source directory mode on the destination root.
chmod 0700 "$rehearsal_partial" "$rehearsal_partial/state"
(
  cd "$rehearsal_partial/state"
  sha256sum -c "$snapshot_dir/files.sha256" >/dev/null
)
mv "$rehearsal_partial" "$rehearsal_dir"

(
  cd "$REMOTE_BUNDLE_DIR"
  REHEARSAL_STATE_DIR="$rehearsal_dir/state" \
    TAILSCALE_IP="$TAILSCALE_IP" \
    MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf-rehearsal -f "$compose_file" config >/dev/null
)
started=1
(
  cd "$REMOTE_BUNDLE_DIR"
  REHEARSAL_STATE_DIR="$rehearsal_dir/state" \
    TAILSCALE_IP="$TAILSCALE_IP" \
    MEDIA_DIR="$MEDIA_DIR" \
    docker-compose -p audiobookshelf-rehearsal -f "$compose_file" up -d --no-build
)

server_version=""
for _ in $(seq 1 120); do
  status_json=$(curl -fsS --max-time 5 "http://$TAILSCALE_IP:13379/status" 2>/dev/null || true)
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
  docker logs --tail 100 audiobookshelf-rehearsal >&2 || true
  echo "rehearsal status endpoint did not report 2.36.0" >&2
  exit 1
}

runtime_image_id=$(docker inspect audiobookshelf-rehearsal --format '{{.Image}}')
[[ $runtime_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || {
  echo "rehearsal runtime image ID mismatch" >&2
  exit 1
}

sqlite_integrity=$(docker exec audiobookshelf-rehearsal node -e '
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
  echo "rehearsal SQLite integrity check failed" >&2
  exit 1
}

cat >"$rehearsal_dir/rehearsal.env" <<REPORT
snapshot_id=$SNAPSHOT_ID
image_id=$runtime_image_id
server_version=$server_version
sqlite_integrity=$sqlite_integrity
url=http://$TAILSCALE_IP:13379
baseline_status=awaiting-manual-verification
REPORT

started=0
printf 'rehearsal ready: http://%s:13379\n' "$TAILSCALE_IP"
printf 'verify the service baseline in Absorb before cutover\n'
REMOTE_SCRIPT
} | run_remote
