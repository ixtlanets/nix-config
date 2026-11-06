#!/usr/bin/env python3
"""Apply a checked IPv4-only VPN profile with a timed local rollback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

LIVE = Path('/etc/sing-box/vless.json')
CANDIDATE = Path('/etc/nikcode-network/t14s/candidate.json')
DROP = Path('/etc/systemd/system/vless-sing-box.service.d/40-public-ipv4.conf')
HELPER = Path('/usr/local/libexec/nikcode-t14s-vpn-dns')
BASE = Path('/var/lib/nikcode-network/t14s/public-ipv4-20261106')
UNIT = 'nikcode-t14s-ipv4-rollback'


def process_start_time(pid):
    # comm can contain spaces and parentheses; fields after its final ')' start
    # with field 3, making starttime (field 22) index 19.
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


def stop_expired_apply(pid, started):
    # The apply process owns a separate process group. Kill it and its commands
    # before taking its lock, so a stuck check cannot delay the watchdog. Check
    # starttime as well as PID to avoid signalling an unrelated reused PID.
    try:
        if process_start_time(pid) == started and os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except FileNotFoundError:
        pass


def cancel_watchdog():
    # Once accepted, rollback is deliberately a no-op. Timer cleanup failure
    # must not turn a completed transaction into a misleading apply failure.
    try:
        result = run(['systemctl', 'stop', UNIT + '.timer'], check=False)
        if result.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    print('Warning: watchdog timer cleanup failed; accepted state is retained.', file=sys.stderr)


def run(args, check=True, timeout=40):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Command failed: ' + args[0])
    return result


def write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode())
    tmp.chmod(mode)
    tmp.replace(path)


def rollback():
    receipt = BASE / 'result.json'
    if receipt.exists() and json.loads(receipt.read_text()).get('status') == 'accepted':
        return
    try:
        for key, target in [('live', LIVE), ('candidate', CANDIDATE), ('drop', DROP), ('helper', HELPER)]:
            if (BASE / key).exists():
                write(target, (BASE / key).read_bytes(), 0o755 if key == 'helper' else 0o600)
            elif key in ('drop', 'helper'):
                target.unlink(missing_ok=True)
        state = json.loads((BASE / 'before.json').read_text())
        try:
            # The old dual-stack TUN must be recreated before restoring a
            # baseline that may have disabled IPv6 after the service started.
            enable_kernel_ipv6()
            run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'restart', 'vless-sing-box.service'])
        finally:
            for name, value in state['sysctl'].items():
                run(['sysctl', '-w', f'{name}={value}'])
            # Aggregate 'all' changes can overwrite interface flags. Restore
            # each surviving interface afterwards, including dotted names.
            for name, value in state.get('interface_ipv6', {}).items():
                path = Path('/proc/sys/net/ipv6/conf') / name / 'disable_ipv6'
                if path.exists():
                    path.write_text(value + '\n')
        if state['refresh_timer_active']:
            run(['systemctl', 'start', 'nikcode-t14s-refresh.timer'])
        write(receipt, json.dumps({'status': 'rolled-back'}))
    except Exception as error:
        write(receipt, json.dumps({'status': 'rollback-failed', 'error': type(error).__name__}))
        raise


def interface_ipv6_state():
    return {path.parent.name: path.read_text().strip()
            for path in Path('/proc/sys/net/ipv6/conf').glob('*/disable_ipv6')
            if path.parent.name not in ('all', 'default')}


def enable_kernel_ipv6():
    run(['sysctl', '-w', 'net.ipv6.conf.default.disable_ipv6=0', 'net.ipv6.conf.all.disable_ipv6=0'])
    for path in Path('/proc/sys/net/ipv6/conf').glob('*/disable_ipv6'):
        path.write_text('0\n')


def dns_checks():
    import dns.message
    import dns.query
    import dns.rcode
    import dns.rdatatype
    for server in ['198.19.0.2', '127.0.0.53']:
        for kind in ['A', 'AAAA']:
            reply = dns.query.udp(dns.message.make_query('ifconfig.me', kind), server, timeout=5)
            assert reply.rcode() == dns.rcode.NOERROR, 'DNS response must be NOERROR'
            answers = [r for rr in reply.answer for r in rr if rr.rdtype == dns.rdatatype.from_text(kind)]
            assert bool(answers) == (kind == 'A'), 'Unexpected public DNS family answer'


def restore_tailnet_ipv6():
    state = json.loads(run(['tailscale', 'status', '--json']).stdout)
    expected = {x for x in state['TailscaleIPs'] if ':' in x}
    def assigned():
        interfaces = json.loads(run(['ip', '-j', '-6', 'address', 'show', 'dev', 'tailscale0']).stdout)
        return {a['local'] for i in interfaces for a in i.get('addr_info', [])}
    if not expected.issubset(assigned()):
        # A previous all.disable_ipv6=1 removes daemon-managed addresses and
        # routes. Recreate them through their owner, preserving its state.
        run(['systemctl', 'restart', 'tailscaled.service'])
    for _ in range(20):
        if expected.issubset(assigned()):
            return
        time.sleep(.5)
    raise RuntimeError('Tailscale IPv6 addresses were not restored')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--dns-helper', type=Path)
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--apply-pid', type=int)
    parser.add_argument('--apply-start-time')
    args = parser.parse_args()
    if os.geteuid() != 0 or socket.gethostname().split('.')[0] != 't14s':
        raise RuntimeError('Run as root on t14s')
    os.umask(0o077)
    if args.rollback and args.apply_pid is not None:
        if args.apply_pid <= 1 or not args.apply_start_time:
            raise RuntimeError('Watchdog requires a valid apply PID and start time')
        receipt = BASE / 'result.json'
        if not (receipt.exists() and json.loads(receipt.read_text()).get('status') == 'accepted'):
            stop_expired_apply(args.apply_pid, args.apply_start_time)
    with open('/var/lib/nikcode-network/t14s/lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        apply_locked(args)


def apply_locked(args):
    if args.rollback:
        rollback()
        return
    if not args.profile or not args.dns_helper or BASE.exists():
        raise RuntimeError('Need new staged profile/helper and an unused backup directory')
    profile = json.loads(args.profile.read_text())
    rules = profile['route']['rules']
    private = next(i for i, r in enumerate(rules) if r.get('ip_is_private') and r.get('outbound') == 'direct')
    reject = next(i for i, r in enumerate(rules) if r.get('ip_version') == 6 and r.get('action') == 'reject')
    assert private < reject
    assert any(r.get('query_type') == ['AAAA'] or r.get('query_type') == 'AAAA' for r in profile['dns']['rules'])
    tun = next(i for i in profile['inbounds'] if i['type'] == 'tun')
    assert tun['address'] == ['198.19.0.1/30', 'fdfe:dcba:9876::1/126']
    assert 'fc00::/7' in tun['route_exclude_address']
    run(['sing-box', 'check', '-c', str(args.profile)])
    BASE.mkdir(parents=True, mode=0o700)
    for key, path in [('live', LIVE), ('candidate', CANDIDATE), ('drop', DROP), ('helper', HELPER)]:
        if path.exists():
            write(BASE / key, path.read_bytes())
    keys = ['net.ipv6.conf.all.disable_ipv6', 'net.ipv6.conf.default.disable_ipv6']
    state = {'sysctl': {k: run(['sysctl', '-n', k]).stdout.strip() for k in keys},
             'interface_ipv6': interface_ipv6_state(),
             'refresh_timer_active': run(['systemctl', 'is-active', '--quiet', 'nikcode-t14s-refresh.timer'], check=False).returncode == 0}
    write(BASE / 'before.json', json.dumps(state))
    write(BASE / 'apply.py', Path(__file__).read_bytes(), 0o700)
    # Isolate the process group before arming a watchdog that may terminate it.
    if os.getpgrp() != os.getpid():
        os.setpgrp()
    try:
        run(['systemctl', 'stop', 'nikcode-t14s-refresh.timer'])
        run(['systemd-run', '--unit=' + UNIT, '--on-active=240s', '/usr/bin/python3', str(BASE / 'apply.py'),
             '--rollback', '--apply-pid', str(os.getpid()), '--apply-start-time', process_start_time(os.getpid())])
        write(LIVE, args.profile.read_bytes(), 0o400)
        write(CANDIDATE, args.profile.read_bytes())
        write(HELPER, args.dns_helper.read_bytes(), 0o755)
        write(DROP, '[Service]\nExecStartPost=\nExecStartPost=/usr/local/libexec/vless-restore-ipv6-ra\nExecStartPost=/usr/bin/python3 /usr/local/libexec/nikcode-t14s-vpn-dns\n', 0o644)
        # Isolated policy checks must pass before invoking this script.  Enable
        # kernel IPv6 before recreating the dual-stack TUN interface.
        enable_kernel_ipv6()
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'restart', 'vless-sing-box.service'])
        restore_tailnet_ipv6()
        for _ in range(12):
            try:
                dns_checks()
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError('DNS family checks failed')
        for url in ['https://www.cloudflare.com/cdn-cgi/trace', 'https://www.google.com/generate_204']:
            run(['curl', '--fail', '--silent', '--show-error', '--max-time', '12', url])
        # Reject an explicit public IPv6 request through SOCKS quickly.
        ipv6 = run(['curl', '--silent', '--max-time', '4', '--proxy', 'socks5h://127.0.0.1:2080', '--noproxy', '',
                    'http://[2600:1901:0:b2bd::]/ip'], check=False, timeout=6)
        assert ipv6.returncode not in (0, 28), 'Public IPv6 must fail promptly'
        run(['tailscale', 'ping', '--c=1', '--timeout=5s', 'zenbook'])
        run(['getent', 'ahostsv4', 'zenbook.tailf108.ts.net'])
        for k in keys:
            assert run(['sysctl', '-n', k]).stdout.strip() == '0'
        if state['refresh_timer_active']:
            run(['systemctl', 'start', 'nikcode-t14s-refresh.timer'])
        write(BASE / 'result.json', json.dumps({'status': 'accepted', 'kernel_ipv6': 'enabled', 'public_vpn': 'ipv4-only'}))
        cancel_watchdog()
        print('Policy accepted; public A/AAAA, HTTPS, fast IPv6 rejection and Tailscale checks passed; kernel IPv6 enabled.')
    except Exception:
        rollback()
        run(['systemctl', 'stop', UNIT + '.timer'], check=False)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Operation failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
