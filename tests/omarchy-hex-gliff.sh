#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash -n "$repo_root/scripts/hex-gliff-service.sh" "$repo_root/scripts/omarchy-apply-user.sh"
python - "$repo_root" <<'PY'
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
apply = (root / 'scripts/omarchy-apply-user.sh').read_text()
function = apply.split('configure_hex_gliff() {', 1)[1].split('\nconfigure_host_gpu()', 1)[0]
assert '\nconfigure_hex_gliff\n' in apply
assert 'restart' not in function.split('# Do not interrupt', 1)[0]
# Exercise only the installer function, mocking all filesystem/systemd writes.
for host, installed, expected in [('zenbook', True, 3), ('t14s', True, 0), ('zenbook', False, 0)]:
    script = '''
set -euo pipefail
install_file() { printf 'install:%s:%s\\n' "$1" "$2"; }
chmod() { :; }
systemctl() { printf 'systemctl:%s\\n' "$*"; }
log() { :; }
'''
    # Mock command discovery so this test never depends on Hex being installed.
    script += 'command() { return ' + ('0' if installed else '1') + '; }\n'
    script += 'expected_host=' + host + '\nsource_root=/repo\nHOME=/home/test\n'
    script += 'configure_hex_gliff() {' + function + '\nconfigure_hex_gliff\n'
    result = subprocess.run(['bash'], input=script, text=True, capture_output=True, check=True)
    assert result.stdout.count('install:') == expected, result.stdout
    if expected:
        assert '/repo/scripts/hex-gliff-wtype.py:/home/test/.local/lib/hex-gliff/bin/wtype' in result.stdout
        assert '/repo/scripts/hex-gliff-service.sh:/home/test/.local/lib/hex-gliff/service' in result.stdout
        assert 'systemctl:--user daemon-reload' in result.stdout

binding = (root / 'dotfiles/omarchy/hypr/hosts/zenbook.lua').read_text()
line = next(line for line in binding.splitlines() if 'o.bind("ALT + Alt_R"' in line)
for option in ('ignore_mods = true', 'transparent = true', 'dont_inhibit = true'):
    assert option in line, option
assert 'anomaly.hex:dictation-F8' in line
wrapper = (root / 'scripts/hex-gliff-service.sh').read_text()
assert 'export PATH="$HOME/.local/lib/hex-gliff/bin:$PATH"' in wrapper
assert 'export HEX_GLIFF_PASTE=1' in wrapper
assert 'exec /usr/bin/hex service "$@"' in wrapper
unit = (root / 'dotfiles/omarchy/systemd/hex.service.d/gliff-paste.conf').read_text()
assert unit == '[Service]\nExecStart=\nExecStart=%h/.local/lib/hex-gliff/service\n'
PY
printf 'PASS: Hex Gliff binding and persistent service installation\n'
