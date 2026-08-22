#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

allow_rehearsal=0
if [[ ${1:-} == "--allow-rehearsal" ]]; then
  allow_rehearsal=1
elif [[ -n ${1:-} ]]; then
  echo "usage: preflight.sh [--allow-rehearsal]" >&2
  exit 2
fi

if fingerprint=$(
  {
    printf 'EXPECTED_CURRENT_IMAGE_ID=%q\n' "$EXPECTED_CURRENT_IMAGE_ID"
    printf 'EXPECTED_TARGET_IMAGE_ID=%q\n' "$EXPECTED_TARGET_IMAGE_ID"
    printf 'SOURCE_STATE_DIR=%q\n' "$SOURCE_STATE_DIR"
    printf 'MEDIA_DIR=%q\n' "$MEDIA_DIR"
    printf 'TAILSCALE_IP=%q\n' "$TAILSCALE_IP"
    printf 'ALLOW_REHEARSAL=%q\n' "$allow_rehearsal"
    cat <<'REMOTE_SCRIPT'
set -euo pipefail

die() {
  echo "preflight failed: $*" >&2
  exit 1
}

for command in docker python3 findmnt ss; do
  command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done

hostname_value=$(hostname)
arch_value=$(uname -m)
image_id=$(docker inspect audiobookshelf --format '{{.Image}}' 2>/dev/null) || die "container audiobookshelf is missing"
image_ref=$(docker inspect audiobookshelf --format '{{.Config.Image}}')
labels=$(docker inspect audiobookshelf --format '{{json .Config.Labels}}')
restart_policy=$(docker inspect audiobookshelf --format '{{.HostConfig.RestartPolicy.Name}}')
network_mode=$(docker inspect audiobookshelf --format '{{.HostConfig.NetworkMode}}')
host_port=$(docker inspect audiobookshelf --format '{{(index (index .HostConfig.PortBindings "80/tcp") 0).HostPort}}')
mounts=$(docker inspect audiobookshelf --format '{{range .Mounts}}{{println .Source "|" .Destination "|" .RW}}{{end}}')

[[ $image_id == "$EXPECTED_CURRENT_IMAGE_ID" ]] || die "fingerprint mismatch: image id"
[[ $image_ref == "ghcr.io/advplyr/audiobookshelf:latest" ]] || die "fingerprint mismatch: image reference"
[[ $labels == "{}" ]] || die "fingerprint mismatch: labels"
[[ $restart_policy == "unless-stopped" ]] || die "fingerprint mismatch: restart policy"
[[ $network_mode == "bridge" ]] || die "fingerprint mismatch: network mode"
[[ $host_port == "13378" ]] || die "fingerprint mismatch: host port"
grep -Fxq "$SOURCE_STATE_DIR | /config | true" <<<"$mounts" || die "fingerprint mismatch: /config mount"
grep -Fxq "$SOURCE_STATE_DIR | /metadata | true" <<<"$mounts" || die "fingerprint mismatch: /metadata mount"
grep -Fxq "$MEDIA_DIR | /audiobooks | true" <<<"$mounts" || die "fingerprint mismatch: /audiobooks mount"

[[ -n $(docker ps -q --filter name='^/audiobookshelf$' --filter status=running) ]] || die "production container is not running"
findmnt -n /media/disk1 >/dev/null 2>&1 || die "/media/disk1 is not mounted"
[[ -d $SOURCE_STATE_DIR && -f $SOURCE_STATE_DIR/absdatabase.sqlite ]] || die "source state is missing"
[[ -d $MEDIA_DIR ]] || die "media directory is missing"
[[ -z $(find "$SOURCE_STATE_DIR" -not -readable -print -quit 2>/dev/null) ]] || die "source state is not fully readable"
ip -4 addr show tailscale0 2>/dev/null | grep -Fq "$TAILSCALE_IP/" || die "Tailscale IP is missing"

available_kib=$(df -Pk /home/nik | awk 'NR == 2 { print $4 }')
((available_kib >= 2097152)) || die "less than 2 GiB free on root filesystem"

integrity=$(DB_PATH="$SOURCE_STATE_DIR/absdatabase.sqlite" python3 - <<'PY'
import os
import sqlite3

path = "file:" + os.environ["DB_PATH"] + "?mode=ro"
connection = sqlite3.connect(path, uri=True)
connection.execute("PRAGMA query_only=ON")
print(connection.execute("PRAGMA integrity_check").fetchone()[0])
PY
)
[[ $integrity == "ok" ]] || die "SQLite integrity check failed"

if ss -H -lnt 'sport = :13379' | grep -q .; then
  [[ $ALLOW_REHEARSAL == 1 ]] || die "rehearsal port 13379 is already in use"
  rehearsal_image_id=$(docker inspect audiobookshelf-rehearsal --format '{{.Image}}' 2>/dev/null) || die "port 13379 is not owned by the rehearsal container"
  [[ $rehearsal_image_id == "$EXPECTED_TARGET_IMAGE_ID" ]] || die "rehearsal image ID mismatch"
fi

if docker ps -a --format '{{.Names}}|{{.Image}}' | grep -Eiq 'watchtower|diun|ouroboros|dockupdater'; then
  die "automatic Docker updater detected"
fi

printf 'hostname=%s\n' "$hostname_value"
printf 'arch=%s\n' "$arch_value"
printf 'image_id=%s\n' "$image_id"
printf 'remote_checks=ok\n'
REMOTE_SCRIPT
  } | run_remote
); then
  :
else
  printf '%s\n' "$fingerprint" >&2
  exit 1
fi

field() {
  local key=$1
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' <<<"$fingerprint"
}

hostname_value=$(field hostname)
arch_value=$(field arch)
image_id=$(field image_id)
remote_checks=$(field remote_checks)

[[ $hostname_value == "$EXPECTED_HOSTNAME" ]] || {
  echo "fingerprint mismatch: hostname" >&2
  exit 1
}
[[ $arch_value == "$EXPECTED_ARCH" ]] || {
  echo "fingerprint mismatch: architecture" >&2
  exit 1
}
[[ $image_id == "$EXPECTED_CURRENT_IMAGE_ID" ]] || {
  echo "fingerprint mismatch: image id" >&2
  exit 1
}
[[ $remote_checks == "ok" ]] || {
  echo "preflight failed: incomplete remote checks" >&2
  exit 1
}

printf 'preflight ok: host=%s arch=%s image=%s\n' "$hostname_value" "$arch_value" "$image_id"
