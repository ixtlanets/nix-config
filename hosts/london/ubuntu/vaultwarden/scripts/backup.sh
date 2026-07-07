#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=${ENV_FILE:-/opt/vaultwarden/backup.env}

if [[ ! -r "$ENV_FILE" ]]; then
  echo "missing backup env: $ENV_FILE" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

: "${AGE_RECIPIENT:?missing AGE_RECIPIENT}"
: "${BACKUP_DIR:=/var/backups/vaultwarden}"
: "${BACKUP_GROUP:=ubuntu}"
: "${DATA_DIR:=/opt/vaultwarden/vw-data}"
: "${RETENTION_DAYS:=30}"

for command in age jq rsync sqlite3 tar zstd; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required command: $command" >&2
    exit 1
  fi
done

if [[ ! -r "$DATA_DIR/db.sqlite3" ]]; then
  echo "missing Vaultwarden sqlite database: $DATA_DIR/db.sqlite3" >&2
  exit 1
fi

timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
tmp=$(mktemp -d)
partial="$BACKUP_DIR/vaultwarden-london-$timestamp.tar.zst.age.partial"
out="$BACKUP_DIR/vaultwarden-london-$timestamp.tar.zst.age"

cleanup() {
  rm -rf "$tmp"
  rm -f "$partial"
}
trap cleanup EXIT

install -d -m 0750 -o root -g "$BACKUP_GROUP" "$BACKUP_DIR"
install -d -m 0700 "$tmp/data"

sqlite3 "$DATA_DIR/db.sqlite3" ".backup '$tmp/data/db.sqlite3'"

rsync -a --delete \
  --exclude db.sqlite3 \
  --exclude db.sqlite3-shm \
  --exclude db.sqlite3-wal \
  "$DATA_DIR"/ "$tmp/data"/

image=$(docker inspect --format '{{.Config.Image}}@{{.Image}}' vaultwarden 2>/dev/null || true)

jq -n \
  --arg createdAt "$timestamp" \
  --arg hostname "$(hostname -f 2>/dev/null || hostname)" \
  --arg image "$image" \
  --arg dataDir "$DATA_DIR" \
  '{
    createdAt: $createdAt,
    hostname: $hostname,
    service: "vaultwarden",
    image: $image,
    dataDir: $dataDir,
    format: "tar.zst.age"
  }' > "$tmp/manifest.json"

tar -C "$tmp" -cf - data manifest.json \
  | zstd -T0 -19 \
  | age -r "$AGE_RECIPIENT" -o "$partial"

chown "root:$BACKUP_GROUP" "$partial"
chmod 0640 "$partial"
mv "$partial" "$out"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'vaultwarden-london-*.tar.zst.age' -mtime +"$RETENTION_DAYS" -delete

echo "$out"
