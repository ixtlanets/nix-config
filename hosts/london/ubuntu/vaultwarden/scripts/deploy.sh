#!/usr/bin/env bash
set -euo pipefail

REMOTE=${REMOTE:-ubuntu@london}
REMOTE_DIR=${REMOTE_DIR:-/opt/vaultwarden}
PUBLIC_BIND_IP=${PUBLIC_BIND_IP:-10.0.0.72}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "$SCRIPT_DIR/../../../../.." && pwd)
SECRET_DIR=${SECRET_DIR:-$ROOT_DIR/secrets/vaultwarden/london}

required_local=(
  "$SCRIPT_DIR/../docker-compose.yml"
  "$SCRIPT_DIR/../Caddyfile"
  "$SCRIPT_DIR/../systemd/vaultwarden.service"
  "$SCRIPT_DIR/../systemd/vaultwarden-backup.service"
  "$SCRIPT_DIR/../systemd/vaultwarden-backup.timer"
  "$SCRIPT_DIR/backup.sh"
  "$SCRIPT_DIR/restore.sh"
  "$SECRET_DIR/vaultwarden.env"
  "$SECRET_DIR/backup.env"
)

for path in "${required_local[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing required file: $path" >&2
    exit 1
  fi
done

for command in scp ssh; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "missing required local command: $command" >&2
    exit 1
  fi
done

tmp_remote=$(ssh "$REMOTE" 'mktemp -d /tmp/vaultwarden-deploy.XXXXXX')
cleanup() {
  ssh "$REMOTE" "rm -rf '$tmp_remote'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ssh "$REMOTE" "mkdir -p '$tmp_remote/scripts' '$tmp_remote/systemd'"

scp \
  "$SCRIPT_DIR/../docker-compose.yml" \
  "$SCRIPT_DIR/../Caddyfile" \
  "$REMOTE:$tmp_remote"/

scp "$SCRIPT_DIR/backup.sh" "$SCRIPT_DIR/restore.sh" "$REMOTE:$tmp_remote/scripts/"
scp "$SCRIPT_DIR/../systemd/"* "$REMOTE:$tmp_remote/systemd/"
scp "$SECRET_DIR/vaultwarden.env" "$SECRET_DIR/backup.env" "$REMOTE:$tmp_remote/"

ssh "$REMOTE"   "REMOTE_DIR='$REMOTE_DIR' PUBLIC_BIND_IP='$PUBLIC_BIND_IP' TMP_REMOTE='$tmp_remote' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

: "${REMOTE_DIR:?missing REMOTE_DIR}"
: "${PUBLIC_BIND_IP:?missing PUBLIC_BIND_IP}"
: "${TMP_REMOTE:?missing TMP_REMOTE}"

need_packages=()
for command in age rsync sqlite3 zstd jq; do
  if ! command -v "$command" >/dev/null 2>&1; then
    case "$command" in
      age) need_packages+=(age) ;;
      rsync) need_packages+=(rsync) ;;
      sqlite3) need_packages+=(sqlite3) ;;
      zstd) need_packages+=(zstd) ;;
      jq) need_packages+=(jq) ;;
    esac
  fi
done

if ((${#need_packages[@]} > 0)); then
  sudo apt-get update
  sudo apt-get install -y "${need_packages[@]}"
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required on london" >&2
  exit 1
fi

if ! systemctl is-active --quiet docker; then
  echo "docker.service is not active" >&2
  exit 1
fi

if ! ip -4 addr show | grep -q "inet $PUBLIC_BIND_IP/"; then
  echo "public bind IP $PUBLIC_BIND_IP is not configured on this host" >&2
  exit 1
fi

port_conflict() {
  local port=$1
  ss -H -lnt "sport = :$port" | awk -v ip="$PUBLIC_BIND_IP" -v port="$port" '
    $4 == ip ":" port || $4 == "0.0.0.0:" port || $4 == "[::]:" port { found = 1 }
    END { exit found ? 0 : 1 }
  '
}

if [[ ! -f "$REMOTE_DIR/.managed-by-nix-config-vaultwarden" ]]; then
  for port in 80 443; do
    if port_conflict "$port"; then
      echo "port $port is already bound by a non-managed listener; refusing deploy" >&2
      ss -H -lnt "sport = :$port" >&2 || true
      exit 1
    fi
  done
fi

echo "Tailscale Serve status before deploy:"
tailscale serve status || true

sudo install -d -m 0755 "$REMOTE_DIR"
sudo install -d -m 0755 "$REMOTE_DIR/scripts"

if [[ ! -f "$REMOTE_DIR/.managed-by-nix-config-vaultwarden" && -d "$REMOTE_DIR/vw-data" ]]; then
  timestamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
  if [[ -f "$REMOTE_DIR/docker-compose.yml" ]]; then
    (cd "$REMOTE_DIR" && sudo docker compose down) || true
  else
    sudo docker stop vaultwarden || true
    sudo docker rm vaultwarden || true
  fi
  sudo mv "$REMOTE_DIR/vw-data" "$REMOTE_DIR/vw-data.archived-$timestamp"
fi

sudo install -m 0644 "$TMP_REMOTE/docker-compose.yml" "$REMOTE_DIR/docker-compose.yml"
sudo install -m 0644 "$TMP_REMOTE/Caddyfile" "$REMOTE_DIR/Caddyfile"
sudo install -m 0755 "$TMP_REMOTE/scripts/backup.sh" "$REMOTE_DIR/scripts/backup.sh"
sudo install -m 0755 "$TMP_REMOTE/scripts/restore.sh" "$REMOTE_DIR/scripts/restore.sh"
sudo install -m 0600 "$TMP_REMOTE/vaultwarden.env" "$REMOTE_DIR/vaultwarden.env"
sudo install -m 0600 "$TMP_REMOTE/backup.env" "$REMOTE_DIR/backup.env"

sudo install -d -m 0755 "$REMOTE_DIR/vw-data"
sudo install -d -m 0755 "$REMOTE_DIR/caddy-config"
sudo install -d -m 0755 "$REMOTE_DIR/caddy-data"
sudo touch "$REMOTE_DIR/.managed-by-nix-config-vaultwarden"

sudo install -m 0644 "$TMP_REMOTE/systemd/vaultwarden.service" /etc/systemd/system/vaultwarden.service
sudo install -m 0644 "$TMP_REMOTE/systemd/vaultwarden-backup.service" /etc/systemd/system/vaultwarden-backup.service
sudo install -m 0644 "$TMP_REMOTE/systemd/vaultwarden-backup.timer" /etc/systemd/system/vaultwarden-backup.timer

sudo systemctl daemon-reload
sudo systemctl enable vaultwarden.service
sudo systemctl restart vaultwarden.service
sudo systemctl enable --now vaultwarden-backup.timer

cd "$REMOTE_DIR"
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/alive >/dev/null
curl -fsSI -H 'Host: vault.nikcode.xyz' "http://$PUBLIC_BIND_IP" >/dev/null

echo "Tailscale Serve status after deploy:"
tailscale serve status || true
REMOTE_SCRIPT
