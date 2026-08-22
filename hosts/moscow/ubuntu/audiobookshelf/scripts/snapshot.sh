#!/usr/bin/env bash
set -euo pipefail

purpose=${1:-}
if [[ $purpose != "rehearsal" && $purpose != "cutover" ]]; then
  echo "usage: snapshot.sh <rehearsal|cutover>" >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

{
  printf 'PURPOSE=%q\n' "$purpose"
  printf 'EXPECTED_CURRENT_IMAGE_ID=%q\n' "$EXPECTED_CURRENT_IMAGE_ID"
  printf 'SOURCE_STATE_DIR=%q\n' "$SOURCE_STATE_DIR"
  printf 'REMOTE_STATE_DIR=%q\n' "$REMOTE_STATE_DIR"
  cat <<'REMOTE_SCRIPT'
set -euo pipefail

case "$REMOTE_STATE_DIR" in
  /home/nik/* | /tmp/*) ;;
  *)
    echo "unsafe remote state directory: $REMOTE_STATE_DIR" >&2
    exit 1
    ;;
esac

timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
snapshot_id="$timestamp-$PURPOSE"
snapshots_dir="$REMOTE_STATE_DIR/snapshots"
snapshot_dir="$snapshots_dir/$snapshot_id"
partial_dir="$snapshot_dir.partial"
production_stopped=0

cleanup() {
  local status=$?
  trap - EXIT

  if ((production_stopped)); then
    docker start audiobookshelf >/dev/null 2>&1 || true
  fi

  if ((status != 0)); then
    if [[ -n ${partial_dir:-} && $partial_dir == "$snapshots_dir/"*.partial ]]; then
      rm -rf -- "$partial_dir"
    fi
    echo "snapshot failed; production restart was attempted" >&2
  fi

  exit "$status"
}
trap cleanup EXIT

image_id=$(docker inspect audiobookshelf --format '{{.Image}}')
[[ $image_id == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "fingerprint mismatch: image id" >&2
  exit 1
}
[[ -f $SOURCE_STATE_DIR/absdatabase.sqlite ]] || {
  echo "source database is missing" >&2
  exit 1
}
[[ ! -e $snapshot_dir && ! -e $partial_dir ]] || {
  echo "snapshot ID already exists: $snapshot_id" >&2
  exit 1
}

install -d -m 0700 "$REMOTE_STATE_DIR" "$snapshots_dir" "$partial_dir" "$partial_dir/state"

docker stop --time 30 audiobookshelf >/dev/null
production_stopped=1

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
  echo "snapshot SQLite integrity check failed" >&2
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
purpose=$PURPOSE
created_at=$timestamp
source_state_dir=$SOURCE_STATE_DIR
current_image_id=$image_id
database_sha256=$db_sha256
files_manifest_sha256=$files_manifest_sha256
MANIFEST

docker start audiobookshelf >/dev/null

for _ in $(seq 1 30); do
  health=$(docker inspect audiobookshelf --format '{{.State.Health.Status}}' 2>/dev/null || true)
  if [[ $health == "healthy" ]]; then
    production_stopped=0
    break
  fi
  sleep 1
done
[[ $production_stopped == 0 ]] || {
  echo "production did not become healthy after snapshot" >&2
  exit 1
}

mv "$partial_dir" "$snapshot_dir"
printf 'snapshot_id=%s\n' "$snapshot_id"
printf 'snapshot_dir=%s\n' "$snapshot_dir"
REMOTE_SCRIPT
} | run_remote
