"""Host-specific subscription installer. No network change until explicit activate.

Run the staged copy as root on t14s. prepare only installs a cached candidate;
activate installs it into the existing vless-sing-box service and starts it.
Neither action changes Tailscale preferences. London remains a manual reserve.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/etc/nikcode-network/t14s')
STATE = Path('/var/lib/nikcode-network/t14s')
LIVE = Path('/etc/sing-box/vless.json')
DROP = Path('/etc/systemd/system/vless-sing-box.service.d/nikcode-subscription.conf')
PROGRAM = Path('/usr/local/libexec/nikcode-t14s-subscription')
SERVICE = 'vless-sing-box.service'
TIMER = 'nikcode-t14s-refresh.timer'


def run(args, timeout=45, check=True):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if check and result.returncode:
        # Do not echo downloaded content, private URLs or core diagnostics.
        raise RuntimeError('Command failed: ' + ' '.join(args[:2]))
    return result


def systemctl(*args, check=True):
    return run(['systemctl', *args], check=check)


def running():
    return systemctl('is-active', '--quiet', SERVICE, check=False).returncode == 0


def write(path, body, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(body if isinstance(body, bytes) else body.encode())
        stream.flush()
        os.fsync(stream.fileno())
    tmp.chmod(mode)
    tmp.replace(path)


def validate(body):
    if len(body) > 1024 * 1024:
        raise ValueError('Profile too large')
    profile = json.loads(body)
    out = {o['tag']: o for o in profile['outbounds']}
    for tag, kind in [('primary-naive', 'naive'), ('primary-vless', 'vless')]:
        node = out[tag]
        if node['type'] != kind or node['server'] != 'notes.nikcode.xyz' or node['server_port'] != 443:
            raise ValueError('Unexpected endpoint')
    if not out['primary-naive']['tls']['enabled'] or out['primary-naive']['tls']['server_name'] != 'notes.nikcode.xyz':
        raise ValueError('Invalid Naive TLS')
    if out['proxy']['default'] != 'primary-naive':
        raise ValueError('Primary must remain Naive')
    tun = next(i for i in profile['inbounds'] if i['type'] == 'tun')
    if tun['interface_name'] != 'nekoray-tun' or not tun['auto_route'] or not tun['auto_redirect']:
        raise ValueError('Unexpected TUN policy')
    if '100.64.0.0/10' not in tun['route_exclude_address'] or '192.168.0.0/16' not in tun['route_exclude_address']:
        raise ValueError('Private routes must be excluded')
    mixed = next(i for i in profile['inbounds'] if i['type'] == 'mixed')
    if mixed['listen'] != '127.0.0.1' or mixed['listen_port'] != 2080:
        raise ValueError('Unexpected proxy listener')
    candidate = ROOT / 'check.json'
    write(candidate, body)
    try:
        run(['/usr/bin/sing-box', 'check', '-c', str(candidate)])
    finally:
        candidate.unlink(missing_ok=True)
    return profile


def health():
    # Startup includes remote rule-set loading. Retry instead of testing once
    # immediately after systemd reports Type=simple as started.
    for attempt in range(6):
        if running():
            for url in ['https://www.cloudflare.com/cdn-cgi/trace', 'https://www.google.com/robots.txt']:
                result = run(['curl', '--fail', '--silent', '--max-time', '6', '--proxy',
                              'socks5h://127.0.0.1:2080', '-o', '/dev/null', url], timeout=8, check=False)
                if result.returncode == 0:
                    return True
        time.sleep(2)
    return False


def prepare(staged):
    if running():
        raise RuntimeError('Existing tunnel is running; preparation requires it to remain stopped')
    body = (staged / 'profile.json').read_bytes()
    url = (staged / 'subscription-url').read_text().strip()
    if not re.fullmatch(r'https://config\.nikcode\.xyz/s/[A-Za-z0-9_-]{43}', url):
        raise ValueError('Unexpected subscription URL')
    validate(body)
    original = STATE / 'original'
    if not original.exists():
        original.mkdir(mode=0o700)
        write(original / 'vless.json', LIVE.read_bytes())
        write(original / 'dropin.json', json.dumps({'exists': DROP.exists(),
              'text': DROP.read_text() if DROP.exists() else None}))
    write(ROOT / 'candidate.json', body)
    write(ROOT / 'subscription-url', url + '\n')
    write(PROGRAM, Path(__file__).read_bytes(), 0o755)
    write(Path('/etc/systemd/system/nikcode-t14s-refresh.service'),
          '[Unit]\nDescription=Refresh t14s cached subscription\nWants=network-online.target\nAfter=network-online.target\n'
          '[Service]\nType=oneshot\nExecStart=/usr/bin/python3 ' + str(PROGRAM) + ' refresh\nTimeoutStartSec=300\n', 0o644)
    write(Path('/etc/systemd/system/' + TIMER),
          '[Unit]\nDescription=Hourly t14s subscription refresh\n[Timer]\nOnActiveSec=1h\nOnUnitActiveSec=1h\n'
          'RandomizedDelaySec=120\n[Install]\nWantedBy=timers.target\n', 0o644)
    systemctl('daemon-reload')
    print('Prepared; existing profile retained, tunnel and refresh timer not started.')


def restore_original():
    original = STATE / 'original'
    write(LIVE, (original / 'vless.json').read_bytes(), 0o400)
    drop = json.loads((original / 'dropin.json').read_text())
    if drop['exists']:
        write(DROP, drop['text'], 0o644)
    else:
        DROP.unlink(missing_ok=True)
    systemctl('daemon-reload')


def activate(staged):
    if (STATE / 'activated').exists():
        raise RuntimeError('Already installed; use vless up/down to control the existing service')
    if (staged / 'profile.json').exists():
        prepare(staged)
    else:
        if running() or not (STATE / 'original/vless.json').exists():
            raise RuntimeError('Prepare a stopped tunnel first')
        validate((ROOT / 'candidate.json').read_bytes())
    try:
        write(LIVE, (ROOT / 'candidate.json').read_bytes(), 0o400)
        write(DROP, '[Service]\nWorkingDirectory=/var/lib/vless-sing-box\n', 0o644)
        systemctl('daemon-reload')
        systemctl('start', SERVICE)
        if not health():
            raise RuntimeError('New tunnel failed HTTPS health checks')
    except Exception:
        systemctl('stop', SERVICE, check=False)
        restore_original()
        raise RuntimeError('Activation failed; original profile restored, tunnel stopped') from None
    write(STATE / 'activated', 'Naive primary; London manual reserve\n')
    systemctl('enable', SERVICE)
    systemctl('enable', '--now', TIMER)
    print('Naive primary active; HTTPS passed; hourly refresh enabled; Tailscale preferences unchanged.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Subscription redirect rejected')


def refresh():
    url = (ROOT / 'subscription-url').read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=20) as response:
        body = response.read(1024 * 1024 + 1)
    profile = validate(body)
    body = (json.dumps(profile, indent=2) + '\n').encode()
    if not (STATE / 'activated').exists():
        write(ROOT / 'candidate.json', body)
        print('Candidate refreshed; tunnel not started.')
        return
    old = LIVE.read_bytes()
    if json.loads(old) == profile:
        print('Profile unchanged; service not restarted.')
        return
    active = running()
    write(STATE / 'previous.json', old)
    write(LIVE, body, 0o400)
    if active:
        try:
            systemctl('restart', SERVICE)
            if not health():
                raise RuntimeError('Updated profile failed HTTPS checks')
        except Exception:
            write(LIVE, old, 0o400)
            systemctl('restart', SERVICE, check=False)
            raise RuntimeError('Refresh failed; previous profile restored') from None
    write(ROOT / 'candidate.json', body)
    print('Profile refreshed; ' + ('running service checked.' if active else 'service remains stopped.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'activate', 'refresh', 'status', 'rollback'])
    args = parser.parse_args()
    if sys.platform != 'linux' or socket.gethostname().split('.')[0] != 't14s':
        raise RuntimeError('This installer runs only on t14s')
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo on t14s')
    os.umask(0o077)
    for path in (ROOT, STATE):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    with (STATE / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'prepare':
            prepare(Path(__file__).resolve().parent)
        elif args.action == 'activate':
            activate(Path(__file__).resolve().parent)
        elif args.action == 'refresh':
            refresh()
        elif args.action == 'rollback':
            systemctl('disable', '--now', TIMER, check=False)
            systemctl('stop', SERVICE)
            restore_original()
            (STATE / 'activated').unlink(missing_ok=True)
            print('Original profile restored and stopped; Tailscale preferences unchanged.')
        else:
            print(json.dumps({'installed': (ROOT / 'candidate.json').exists(),
                              'activated': (STATE / 'activated').exists(), 'service_running': running(),
                              'refresh_timer': systemctl('is-enabled', TIMER, check=False).returncode == 0}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Exceptions from HTTP libraries can include the private subscription URL.
        print('Operation failed (' + type(error).__name__ + '). Cached configuration retained; '
              'Tailscale preferences were not changed.', file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)
