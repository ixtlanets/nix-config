#!/usr/bin/env bash
# Install only these new services on the owner-approved, previously unused UK VPS.
set -euo pipefail
test "$(id -u)" = 0
test "$#" = 1 || { echo 'Usage: install.sh ROOT_ONLY_STAGE_DIRECTORY' >&2; exit 2; }
stage=$1
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test ! -e /opt/nikcode-subscriptions
test ! -e /etc/nikcode-subscriptions
test ! -e /etc/systemd/system/nikcode-subscriptions.service
test ! -e /etc/systemd/system/nikcode-subscriptions-https.service
python3 - "$bundle/pin.json" "$stage" <<'PY'
import hashlib,json,pathlib,subprocess,sys,socket
pins=json.loads(pathlib.Path(sys.argv[1]).read_text());stage=pathlib.Path(sys.argv[2])
addresses=json.loads(subprocess.check_output(['ip','-j','address']))
assert any(a.get('local')=='91.108.225.14' for link in addresses for a in link.get('addr_info',[])), 'Not the approved UK host'
for name in ['node','caddy']:
 assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==pins[name]['binary_sha256'], 'Runtime hash mismatch'
assert hashlib.sha256((stage/'geoip-ru.srs').read_bytes()).hexdigest()==pins['rules']['sha256'], 'Rules hash mismatch'
state=json.loads((stage/'pilot.json').read_text())
assert all('token' not in d for d in state['devices']), 'Do not transfer operator enrollment tokens'
for port in [80,443,8787]:
 with socket.socket() as listener:listener.bind(('0.0.0.0',port))
PY
"$stage/node" --check "$stage/src/server.js"
"$stage/caddy" validate --config "$bundle/Caddyfile" --adapter caddyfile >/dev/null
for account in nikcode-subscriptions nikcode-subscriptions-caddy; do
  getent group "$account" >/dev/null || groupadd --system "$account"
  id "$account" >/dev/null 2>&1 || useradd --system --gid "$account" --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin "$account"
done
install -d -o root -g root -m 0755 /opt/nikcode-subscriptions /opt/nikcode-subscriptions/src /etc/nikcode-subscriptions
install -o root -g root -m 0755 "$stage/node" "$stage/caddy" /opt/nikcode-subscriptions/
install -o root -g root -m 0644 "$stage/package.json" "$stage/geoip-ru.srs" /opt/nikcode-subscriptions/
install -o root -g root -m 0644 "$stage/src/server.js" "$stage/src/worker.js" "$stage/src/geoip-ru.js" /opt/nikcode-subscriptions/src/
install -o root -g nikcode-subscriptions -m 0640 "$stage/pilot.json" /etc/nikcode-subscriptions/pilot.json
install -o root -g root -m 0644 "$bundle/Caddyfile" /etc/nikcode-subscriptions/Caddyfile
install -o root -g root -m 0644 "$bundle/nikcode-subscriptions.service" "$bundle/nikcode-subscriptions-https.service" /etc/systemd/system/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/nikcode-subscriptions.service /etc/systemd/system/nikcode-subscriptions-https.service
echo 'Installed only; services not started or enabled. Review adapter and acceptance before starting.'
