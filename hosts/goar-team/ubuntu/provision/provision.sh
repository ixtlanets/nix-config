#!/usr/bin/env bash
set -euo pipefail

: "${REMOTE:?set REMOTE=root@<IP> for the new goar-team VPS}"
remote="$REMOTE"
domain="${REALITY_DOMAIN:-www.google.com}"
port="${REALITY_PORT:-443}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
[[ "$remote" != -* && "$remote" != *[[:space:]]* ]] || { printf 'invalid REMOTE\n' >&2; exit 1; }
[[ "$domain" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || { printf 'invalid REALITY_DOMAIN\n' >&2; exit 1; }
[[ "$port" =~ ^[1-9][0-9]{0,4}$ && "$port" -le 65535 ]] || { printf 'invalid REALITY_PORT\n' >&2; exit 1; }
ssh_options=(-o BatchMode=yes)
if [[ -n "${SSH_KEY:-}" ]]; then
  ssh_options+=(-i "$SSH_KEY" -o IdentitiesOnly=yes)
fi
for command_name in ssh; do
  command -v "$command_name" >/dev/null || { printf 'missing local command: %s\n' "$command_name" >&2; exit 1; }
done

# Send the optional key over stdin, never in the SSH command or printed output.
{
  printf 'REALITY_DOMAIN=%q\nREALITY_PORT=%q\n' "$domain" "$port"
  cat <<'REMOTE_SCRIPT'
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { printf 'REMOTE must log in as root\n' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu ]] || { printf 'refusing non-Ubuntu host: %s\n' "$ID" >&2; exit 1; }
for command_name in docker tailscale jq; do
  if command -v "$command_name" >/dev/null; then
    printf '%s: present\n' "$command_name"
  else
    printf '%s: missing; will install\n' "$command_name"
  fi
done
if docker compose version >/dev/null 2>&1; then
  printf 'docker compose: present\n'
fi
packages=()
for command_name in curl jq python3; do
  command -v "$command_name" >/dev/null || packages+=("$command_name")
done
if [[ "${#packages[@]}" -gt 0 ]]; then
  apt-get update
  apt-get install -y "${packages[@]}" ca-certificates
fi
installer=$(mktemp)
trap 'rm -f "$installer"' EXIT
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com -o "$installer"
  sh "$installer"
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker-compose-plugin
fi
docker compose version
if [[ ! -e /opt/reality-ezpz && ! -L /opt/reality-ezpz ]]; then
  curl -fsSL https://raw.githubusercontent.com/aleskxyz/reality-ezpz/master/reality-ezpz.sh -o "$installer"
  bash "$installer" --transport tcp --domain "$REALITY_DOMAIN" --port "$REALITY_PORT"
else
  printf 'Preserving existing /opt/reality-ezpz; skipping installer\n'
fi
[[ -d /opt/reality-ezpz ]] || { printf 'missing reality-ezpz directory\n' >&2; exit 1; }

REMOTE_SCRIPT
} | ssh "${ssh_options[@]}" "$remote" 'bash -s'

# Compare bytes remotely; replace the helper atomically only when changed.
ssh "${ssh_options[@]}" "$remote" 'set -eu
helper=$(mktemp /opt/reality-ezpz/.reality-user.XXXXXX)
trap "rm -f -- \"$helper\"" EXIT
cat > "$helper"
if ! cmp -s "$helper" /opt/reality-ezpz/reality-user; then
  chmod 0755 "$helper"
  chown root:root "$helper"
  mv -f "$helper" /opt/reality-ezpz/reality-user
fi
chmod 0755 /opt/reality-ezpz/reality-user
' < "$repo_root/scripts/reality-user.py"

{
  printf 'TAILSCALE_AUTHKEY=%q\n' "${TAILSCALE_AUTHKEY:-}"
  cat <<'REMOTE_SCRIPT'
set -euo pipefail
installer=$(mktemp)
trap 'rm -f "$installer"' EXIT
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh -o "$installer"
  sh "$installer"
fi
systemctl enable --now tailscaled
# Logged-out status may return nonzero; require valid state JSON nonetheless.
tailscale status --json > "$installer" || true
state=$(jq -er '.BackendState | select(type == "string")' "$installer")
if [[ "$state" == Running ]]; then
  printf 'Tailscale: already connected\n'
elif [[ -n "$TAILSCALE_AUTHKEY" ]]; then
  printf 'Connecting: tailscale up --hostname=goar-team --auth-key=<redacted>\n'
  tailscale up --hostname=goar-team --auth-key="$TAILSCALE_AUTHKEY"
else
  printf 'WARNING: Tailscale is %s; join skipped without TAILSCALE_AUTHKEY.\n' "$state" >&2
  printf 'Run on the VPS: tailscale up --hostname=goar-team --auth-key=<key>\n'
fi
unset TAILSCALE_AUTHKEY
[[ "$(docker inspect --format '{{.State.Running}}' reality-ezpz-engine-1)" == true ]] || {
  printf 'reality-ezpz-engine-1 is not running; inspect logs before proceeding\n' >&2
  exit 1
}
docker ps --filter name=^/reality-ezpz-engine-1$ --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
REMOTE_SCRIPT
} | ssh "${ssh_options[@]}" "$remote" 'bash -s'
