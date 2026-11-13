#!/usr/bin/env python3
"""Run on physical PVE, receiving zenbook's proxy outbound JSON on stdin.
Never print credentials. Use the owner's exact currently working proxy profile;
legacy PVE credentials were rejected by this endpoint during recovery.
Only stages a candidate and probes an isolated loopback-only listener.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import hashlib
from pathlib import Path

assert socket.gethostname() == 'pve-um790'
transport = json.load(sys.stdin)
current_path = Path('/etc/sing-box/pve-guests.json')
current_bytes = current_path.read_bytes()
current = json.loads(current_bytes)
assert isinstance(transport.get('uuid'), str) and transport['uuid']
transport.update(bind_interface='pvewifi0', domain_resolver='dns-bootstrap')
assert transport['type'] == 'vless'
assert transport['server'] == '31.58.85.163' and transport['server_port'] == 24443
assert transport['tls']['enabled'] and transport['tls']['reality']['enabled']
assert not transport['tls'].get('insecure', False)
print('Transport:', {k: transport[k] for k in ['type', 'server', 'server_port', 'bind_interface']})
print('Profile identity hash:', hashlib.sha256(transport['uuid'].encode()).hexdigest()[:16])
current['outbounds'] = [transport if o['tag'] == 'proxy' else o for o in current['outbounds']]
base = Path('/root/pve-network-recovery-20261112')
base.mkdir(mode=0o700, exist_ok=True)
candidate = base / 'pve-guests-frankfurt.json'
with candidate.open('w') as f:
    os.fchmod(f.fileno(), 0o600)
    json.dump(current, f, indent=2)
current['inbounds'] = [{'type': 'mixed', 'tag': 'diagnostic', 'listen': '127.0.0.1', 'listen_port': 22081}]
current['log'] = {'disabled': True}
fd, name = tempfile.mkstemp(prefix='pve-vless-acceptance-', suffix='.json', dir='/run')
p = Path(name)
proc = None
ok = True
try:
    with os.fdopen(fd, 'w') as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(current, f)
    check = subprocess.run(['/usr/local/bin/sing-box-pve-guests', 'check', '-c', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Config check exit:', check.returncode)
    if check.returncode:
        raise SystemExit(check.returncode)
    proc = subprocess.Popen(['/usr/local/bin/sing-box-pve-guests', 'run', '-c', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError('isolated VPN exited')
        try:
            s = socket.create_connection(('127.0.0.1', 22081), timeout=.1)
            s.close()
            break
        except OSError:
            time.sleep(.05)
    else:
        raise RuntimeError('listener failed')
    for url in ['https://1.1.1.1/cdn-cgi/trace', 'https://example.com/', 'https://controlplane.tailscale.com/key?v=148']:
        r = subprocess.run(['curl', '--noproxy', '', '--proxy', 'http://127.0.0.1:22081', '-sS', '--connect-timeout', '5', '--max-time', '10', '-w', '\nHTTP %{http_code}\n', url], capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if l.startswith(('ip=', 'loc=', 'colo=', 'HTTP '))]
        print('Probe:', url, 'exit', r.returncode, '; '.join(lines), r.stderr[:200])
        ok = ok and r.returncode == 0 and 'HTTP 200' in r.stdout
finally:
    if proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    assert p.resolve().parent == Path('/run') and p.name.startswith('pve-vless-acceptance-')
    p.unlink()
receipt = {'accepted': ok, 'tested_at': time.time(), 'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(), 'baseline_sha256': hashlib.sha256(current_bytes).hexdigest()}
(base / 'frankfurt-acceptance.json').write_text(json.dumps(receipt, indent=2))
print('Candidate accepted:', ok)
sys.exit(0 if ok else 1)
