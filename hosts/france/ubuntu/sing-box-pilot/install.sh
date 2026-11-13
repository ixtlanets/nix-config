#!/usr/bin/env bash
# Stage only. Explicit start/enable is left to the reviewed acceptance procedure.
set -euo pipefail
test "$(id -u)" = 0
test "$#" = 2 || { echo 'Usage: install.sh VERIFIED_BINARY PRIVATE_CONFIG' >&2; exit 2; }
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
binary=$1
config=$2
expected=1264361b5f8868c8768f7555d3e77e20118bf503c41ac08bb290a0d99056aa3a
test "$(sha256sum "$binary" | cut -d ' ' -f 1)" = "$expected"
"$binary" check -c "$config" >/dev/null 2>&1
unit=/etc/systemd/system/nikcode-singbox-pilot.service
if test -e "$unit" || test -e /opt/nikcode-singbox-pilot || test -e /etc/nikcode-singbox-pilot; then
  if cmp -s "$binary" /opt/nikcode-singbox-pilot/sing-box &&
     cmp -s "$config" /etc/nikcode-singbox-pilot/config.json &&
     cmp -s "$bundle_dir/nikcode-singbox-pilot.service" "$unit"; then
    echo 'Identical pilot already staged; nothing changed or restarted.'
    exit 0
  fi
  echo 'Pilot paths already exist; refusing to replace a staged or running deployment.' >&2
  exit 1
fi
python3 - "$config" <<'PY'
import json, socket, subprocess, sys
cfg = json.load(open(sys.argv[1]))
inbound = cfg['inbounds'][0]
host, port = inbound['listen'], inbound['listen_port']
assert (host, port) in [('194.87.166.59', 443), ('31.58.85.163', 34443),
                        ('193.124.205.153', 34443), ('81.29.155.74', 34443)]
addresses = json.loads(subprocess.check_output(['ip', '-j', 'address']))
assert any(a.get('local') == host for link in addresses for a in link.get('addr_info', [])), 'Wrong host'
with socket.socket() as listener:
    listener.bind((host, port))
PY
getent group nikcode-singbox-pilot >/dev/null || groupadd --system nikcode-singbox-pilot
if ! id nikcode-singbox-pilot >/dev/null 2>&1; then
  useradd --system --gid nikcode-singbox-pilot --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin nikcode-singbox-pilot
fi
install -d -o root -g root -m 0755 /opt/nikcode-singbox-pilot
install -o root -g root -m 0755 "$binary" /opt/nikcode-singbox-pilot/sing-box
install -d -o root -g nikcode-singbox-pilot -m 0750 /etc/nikcode-singbox-pilot
install -o root -g nikcode-singbox-pilot -m 0640 "$config" /etc/nikcode-singbox-pilot/config.json
install -o root -g root -m 0644 "$bundle_dir/nikcode-singbox-pilot.service" "$unit"
systemctl daemon-reload
echo 'Staged only; existing services and networking unchanged. New pilot has not been started.'
