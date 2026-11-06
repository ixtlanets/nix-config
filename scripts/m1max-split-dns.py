#!/usr/bin/env python3
"""M1 Max public SFM DNS with separate Tailscale DNS and timed rollback."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import time

BASE = Path('/var/db/nikcode-network/m1max-dns-20261106')
RESOLVER = Path('/etc/resolver/tailf108.ts.net')
PLIST = Path('/Library/LaunchDaemons/xyz.nikcode.m1max-split-dns.plist')
JOB = 'system/xyz.nikcode.m1max-split-dns'
GUARD = 'system/xyz.nikcode.m1max-dns-guard'
SFM = 'D8EB2DF8-3555-47D1-AB44-FAF0FCE46B0D'
CLI = ['/bin/launchctl', 'asuser', '501', '/usr/bin/sudo', '-u', 'nik', '/opt/homebrew/bin/tailscale']


def run(args, check=True, timeout=20):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return p


def write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    tmp.write_bytes(text if isinstance(text, bytes) else text.encode())
    tmp.chmod(mode)
    tmp.replace(path)


def reconcile():
    state = json.loads(run(CLI + ['status', '--json']).stdout)
    baseline = json.loads((BASE / 'before.json').read_text())
    if state.get('BackendState') != 'Running' or state['TailscaleIPs'] != baseline['tailnet_ips']:
        raise RuntimeError('Tailscale identity is not the verified baseline')
    own = next(x for x in state['TailscaleIPs'] if ':' not in x)
    interfaces = run(['/sbin/ifconfig']).stdout.splitlines()
    current = None
    selected = None
    for line in interfaces:
        if line and not line[0].isspace():
            current = line.split(':', 1)[0]
        if re.search(r'\binet\s+' + re.escape(own) + r'\s', line):
            selected = current
    if not selected or not selected.startswith('utun'):
        raise RuntimeError('Cannot identify Tailscale tunnel')
    route = run(['/sbin/route', '-n', 'get', '100.100.100.100'], check=False).stdout
    if not re.search(r'interface:\s*' + re.escape(selected) + r'\s*$', route, re.M):
        cmd = ['/sbin/route', '-n', 'add', '-host', '100.100.100.100', '-interface', selected]
        run(cmd)


def flush():
    run(['/usr/bin/dscacheutil', '-flushcache'])
    run(['/usr/bin/killall', '-HUP', 'mDNSResponder'], check=False)


@contextmanager
def transaction():
    with (BASE / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def rollback():
    with transaction():
        if (BASE / 'accepted').exists():
            return
        write(BASE / 'result.json', json.dumps({'status': 'rolling-back'}))
        stop_error = None
        try:
            run(['/bin/launchctl', 'bootout', JOB], check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            stop_error = error
        before = json.loads((BASE / 'before.json').read_text())
        # Restore files before the remote CLI operation, which may time out.
        if before['resolver_existed']:
            write(RESOLVER, (BASE / 'resolver-before').read_bytes(), before['resolver_mode'])
        else:
            RESOLVER.unlink(missing_ok=True)
        PLIST.unlink(missing_ok=True)
        try:
            run(CLI + ['set', '--accept-dns=' + str(before['corp_dns']).lower()])
            flush()
            if stop_error:
                raise stop_error
        except Exception as error:
            write(BASE / 'result.json', json.dumps({'status': 'rollback-failed', 'error': type(error).__name__}))
            raise
        write(BASE / 'result.json', json.dumps({'status': 'rolled-back'}))


def watchdog():
    deadline = json.loads((BASE / 'armed.json').read_text())['deadline']
    while time.time() < deadline:
        if (BASE / 'accepted').exists():
            write(BASE / 'guard-result.json', json.dumps({'status': 'accepted'}))
            return
        time.sleep(2)
    while not (BASE / 'accepted').exists():
        try:
            rollback()
            return
        except Exception:
            time.sleep(15)


def make_plist(label, arguments, interval=None):
    data = {'Label': label, 'ProgramArguments': arguments, 'RunAtLoad': True,
            'StandardOutPath': str(BASE / 'daemon.log'), 'StandardErrorPath': str(BASE / 'daemon.log')}
    if interval:
        data['StartInterval'] = interval
    return plistlib.dumps(data)


def apply():
    if BASE.exists() or PLIST.exists():
        raise RuntimeError('Refusing to overwrite existing deployment')
    status = run(['/usr/sbin/scutil', '--nc', 'status', SFM]).stdout.splitlines()[0]
    if status != 'Connected':
        raise RuntimeError('Keep the current SFM connection active')
    prefs = json.loads(run(CLI + ['debug', 'prefs']).stdout)
    state = json.loads(run(CLI + ['status', '--json']).stdout)
    trace = run(['/usr/bin/curl', '-fsS', '--max-time', '12', 'https://www.cloudflare.com/cdn-cgi/trace']).stdout
    exit_ip = next(line[3:] for line in trace.splitlines() if line.startswith('ip='))
    BASE.mkdir(parents=True, mode=0o700)
    write(BASE / 'before.json', json.dumps({
        'corp_dns': prefs['CorpDNS'], 'tailnet_ips': state['TailscaleIPs'],
        'exit_node': prefs.get('ExitNodeID'), 'route_all': prefs.get('RouteAll'),
        'exit_ip': exit_ip,
        'resolver_existed': RESOLVER.exists(),
        'resolver_mode': RESOLVER.stat().st_mode & 0o777 if RESOLVER.exists() else 0o644,
    }))
    if RESOLVER.exists():
        write(BASE / 'resolver-before', RESOLVER.read_bytes())
    write(BASE / 'helper.py', Path(__file__).read_bytes(), 0o700)
    run(['/usr/sbin/scutil', '--dns'])
    write(BASE / 'dns-before.txt', run(['/usr/sbin/scutil', '--dns']).stdout)
    write(BASE / 'armed.json', json.dumps({'deadline': time.time() + 480}))
    guard_plist = BASE / 'guard.plist'
    write(guard_plist, make_plist(GUARD.removeprefix('system/'), ['/usr/bin/python3', str(BASE / 'helper.py'), 'watchdog']), 0o644)
    run(['/bin/launchctl', 'bootstrap', 'system', str(guard_plist)])
    for _ in range(20):
        if 'state = running' in run(['/bin/launchctl', 'print', GUARD]).stdout:
            break
        time.sleep(.1)
    else:
        raise RuntimeError('Rollback watchdog is not running')
    try:
        if not RESOLVER.parent.exists():
            RESOLVER.parent.mkdir(mode=0o755)
            RESOLVER.parent.chmod(0o755)
        write(RESOLVER, 'domain tailf108.ts.net\nnameserver 100.100.100.100\nsearch tailf108.ts.net\nsearch_order 100000\ntimeout 2\n', 0o644)
        write(PLIST, make_plist(JOB.removeprefix('system/'), ['/usr/bin/python3', str(BASE / 'helper.py'), 'reconcile'], 15), 0o644)
        run(['/bin/launchctl', 'bootstrap', 'system', str(PLIST)])
        run(CLI + ['set', '--accept-dns=false'])
        reconcile()
        flush()
        print('DNS applied; watchdog armed. Verify fresh SSH, DNS and unchanged exit, then accept.')
    except Exception:
        rollback()
        raise


def accept():
    reconcile()
    assert run(['/usr/sbin/scutil', '--nc', 'status', SFM]).stdout.startswith('Connected\n')
    before = json.loads((BASE / 'before.json').read_text())
    prefs = json.loads(run(CLI + ['debug', 'prefs']).stdout)
    assert prefs['CorpDNS'] is False
    assert prefs.get('ExitNodeID') == before['exit_node']
    assert prefs.get('RouteAll') == before['route_all']
    dns_test = '''import socket
for host in ['ifconfig.me', 'mail.google.com']:
    rows=socket.getaddrinfo(host,443,socket.AF_UNSPEC,socket.SOCK_STREAM)
    assert rows and all(row[0]==socket.AF_INET for row in rows)
assert socket.gethostbyname('zenbook.tailf108.ts.net')=='100.114.155.30'
'''
    run(['/usr/bin/python3', '-c', dns_test], timeout=12)
    trace = run(['/usr/bin/curl', '-fsS', '--max-time', '12', 'https://www.cloudflare.com/cdn-cgi/trace']).stdout
    assert next(line[3:] for line in trace.splitlines() if line.startswith('ip=')) == before['exit_ip']
    with transaction():
        deadline = json.loads((BASE / 'armed.json').read_text())['deadline']
        receipt = BASE / 'result.json'
        if time.time() >= deadline or receipt.exists():
            raise RuntimeError('Acceptance deadline elapsed or rollback started')
        write(BASE / 'result.json', json.dumps({'status': 'accepted', 'public_dns': 'SFM', 'tailnet_dns': 'Tailscale'}))
        write(BASE / 'accepted', 'accepted\n')
    run(['/bin/launchctl', 'bootout', GUARD], check=False)
    print('Split DNS accepted; watchdog unloaded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply', 'reconcile', 'watchdog', 'rollback', 'accept'])
    args = parser.parse_args()
    if os.geteuid() != 0 or socket.gethostname().split('.')[0].lower() != 'm1max':
        raise SystemExit('Run as root on M1 Max')
    os.umask(0o077)
    globals()[args.action]()
