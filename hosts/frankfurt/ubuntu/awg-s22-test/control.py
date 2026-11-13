#!/usr/bin/python3
"""Host-specific, fail-closed lifecycle. Never prints command output or config data."""
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path('/etc/awg-s22-test')
RUNTIME = Path('/run/awg-s22-test')
SOCKET = Path('/run/amneziawg/awgs22.sock')
IFACE = 'awgs22'
CLIENT = '10.213.211.2/32'
NETWORK = ipaddress.ip_network('10.213.211.0/30')
COMMENT = ['-m', 'comment', '--comment', 'awg-s22-test']
PINS = {
    'awg': '1ac92ba760092d805907a322f539c923673f5924666978612c3e85c0981bb005',
    'amneziawg-go': 'b53961c848acdc18f36ebd60f7a3f900a0e195be8e582eb721c05fa9ec6b2273',
}
# Block non-public destinations even when they use eth0's default route.
NON_PUBLIC = (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24',
    '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4',
)


class Failure(Exception):
    pass


class Runner:
    def run(self, argv):
        # stderr can contain a rejected private-key/config line; never expose it.
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise Failure('command unavailable or timed out') from None
        return result.returncode, result.stdout


class Lifecycle:
    def __init__(self, runner=None, root=ROOT, runtime=RUNTIME, socket=SOCKET,
                 forwarding=Path('/proc/sys/net/ipv4/ip_forward'), clock=time.monotonic,
                 sleep=time.sleep, interface_path=Path('/sys/class/net/awgs22'),
                 invocation=None):
        self.runner = runner or Runner()
        self.root, self.runtime, self.socket = root, runtime, socket
        self.forwarding = forwarding
        self.clock, self.sleep = clock, sleep
        self.marker = runtime / 'owned'
        self.interface_path = interface_path
        self.invocation = invocation or os.environ.get('INVOCATION_ID')

    def owned(self):
        return (bool(self.invocation) and self.marker.exists()
                and self.marker.read_text() == self.invocation)

    def command(self, argv, message='network command failed'):
        code, output = self.runner.run(argv)
        if code:
            raise Failure(message)
        return output

    def json(self, argv):
        try:
            return json.loads(self.command(argv))
        except (ValueError, TypeError):
            raise Failure('invalid network inspection result') from None

    def rule(self, spec, add):
        tool, table, chain, args = spec
        base = [tool, '-w', '5', '-t', table]
        rule = list(args) + COMMENT
        code, _ = self.runner.run(base + ['-C', chain] + rule)
        if code not in (0, 1):
            raise Failure('firewall check failed')
        if add:
            if code == 1:
                self.command(base + ['-I', chain, '1'] + rule, 'firewall insert failed')
        else:
            # Delete only exact owned matches; cope with duplicate stale owned rules.
            while code == 0:
                self.command(base + ['-D', chain] + rule, 'firewall delete failed')
                code, _ = self.runner.run(base + ['-C', chain] + rule)
                if code not in (0, 1):
                    raise Failure('firewall check failed')

    @staticmethod
    def guards():
        return [(tool, 'filter', chain, args)
                for tool in ('iptables', 'ip6tables')
                for chain, args in (
                    ('INPUT', ['-i', IFACE, '-j', 'DROP']),
                    ('FORWARD', ['-i', IFACE, '-j', 'DROP']),
                    ('FORWARD', ['-o', IFACE, '-j', 'DROP']))] + [
                        ('ip6tables', 'filter', 'INPUT',
                         ['-i', 'eth0', '-p', 'udp', '--dport', '49380', '-j', 'DROP'])]

    @staticmethod
    def permits():
        # Insert at head in this order: final order has private drops BEFORE accept.
        return [
            ('iptables', 'nat', 'POSTROUTING',
             ['-s', CLIENT, '-o', 'eth0', '-j', 'MASQUERADE']),
            ('iptables', 'filter', 'FORWARD',
             ['-i', 'eth0', '-o', IFACE, '-d', CLIENT, '-m', 'conntrack',
              '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT']),
            ('iptables', 'filter', 'FORWARD',
             ['-i', IFACE, '-s', CLIENT, '-o', 'eth0', '-j', 'ACCEPT']),
            *[('iptables', 'filter', 'FORWARD',
               ['-i', IFACE, '-d', destination, '-j', 'DROP'])
              for destination in NON_PUBLIC],
            ('iptables', 'filter', 'INPUT',
             ['-i', 'eth0', '-p', 'udp', '--dport', '49380', '-j', 'ACCEPT']),
        ]

    def secure(self, path, mode, directory=False):
        info = path.lstat()
        if (info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode
                or (not stat.S_ISDIR(info.st_mode) if directory
                    else not stat.S_ISREG(info.st_mode))):
            raise Failure('private bundle ownership/type/mode check failed')

    def config_check(self):
        self.secure(self.root, 0o700, directory=True)
        self.secure(self.root / 'server.conf', 0o600)
        for name, digest in PINS.items():
            self.secure(self.root / name, 0o700)
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != digest:
                raise Failure('pinned executable hash mismatch')
        # Do not return, log, or include config text in exception messages.
        section = None
        sections, seen, settings = [], set(), {}
        for raw in (self.root / 'server.conf').read_text().splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            if line.startswith('['):
                if line not in ('[Interface]', '[Peer]'):
                    raise Failure('native config section invalid')
                section = line
                sections.append(section)
                continue
            if section is None or '=' not in line:
                raise Failure('native config syntax invalid')
            key, value = (part.strip() for part in line.split('=', 1))
            key = key.lower()
            if (section, key) in seen:
                raise Failure('native config has duplicate setting')
            seen.add((section, key))
            if key in ('address', 'mtu', 'dns', 'table', 'preup', 'postup',
                       'predown', 'postdown', 'saveconfig', 'fwmark', 'endpoint'):
                raise Failure('native config has forbidden setting')
            settings[(section, key)] = value
        if (sections != ['[Interface]', '[Peer]']
                or settings.get(('[Interface]', 'listenport')) != '49380'
                or settings.get(('[Peer]', 'allowedips')) != CLIENT
                or not settings.get(('[Interface]', 'privatekey'))
                or not settings.get(('[Peer]', 'publickey'))):
            raise Failure('native config endpoint/peer constraints invalid')

    def preflight(self):
        if not self.invocation:
            raise Failure('systemd invocation identity required')
        self.config_check()
        if self.forwarding.read_text().strip() != '1':
            raise Failure('IPv4 forwarding must already be enabled')
        if os.uname().machine != 'x86_64' or not Path('/dev/net/tun').exists():
            raise Failure('x86_64 and existing TUN device required')
        links = self.json(['ip', '-j', 'link', 'show'])
        if any(link['ifname'] == IFACE for link in links) or self.socket.exists():
            raise Failure('interface or UAPI socket already exists; refusing adoption')
        if self.marker.exists():
            raise Failure('ownership marker already exists')
        addresses = self.json(['ip', '-j', '-4', 'address', 'show'])
        if not any(item['ifname'] == 'eth0' and any(
                addr.get('local') == '31.58.85.163' and addr.get('prefixlen') == 32
                for addr in item.get('addr_info', [])) for item in addresses):
            raise Failure('public eth0 address differs from approved host')
        for item in addresses:
            for addr in item.get('addr_info', []):
                network = ipaddress.ip_network(
                    f"{addr['local']}/{addr['prefixlen']}", strict=False)
                if network.overlaps(NETWORK):
                    raise Failure('test subnet overlaps an existing address')
        routes = self.json(['ip', '-j', '-4', 'route', 'show', 'table', 'all'])
        for route in routes:
            destination = route.get('dst', 'default')
            if destination != 'default' and ipaddress.ip_network(destination).overlaps(NETWORK):
                raise Failure('test subnet overlaps an existing route')
        if self.command(['ss', '-H', '-lun', 'sport = :49380']).strip():
            raise Failure('approved UDP port is already bound')
        for tool, table, chain, args in self.guards() + self.permits():
            code, _ = self.runner.run([tool, '-w', '5', '-t', table, '-C', chain]
                                      + list(args) + COMMENT)
            if code == 0:
                raise Failure('stale scoped firewall rule exists; refusing adoption')
            if code != 1:
                raise Failure('firewall preflight check failed')
        with self.marker.open('x') as marker:
            marker.write(self.invocation)
        self.marker.chmod(0o600)

    def up(self):
        if not self.owned():
            raise Failure('missing current service ownership marker')
        deadline = self.clock() + 10
        while True:
            # Local filesystem checks keep the readiness wait bounded to 10 seconds.
            if self.socket.is_socket() and self.interface_path.exists():
                break
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise Failure('interface/UAPI readiness exceeded 10 seconds')
            self.sleep(min(0.1, remaining))
        for spec in self.guards():
            self.rule(spec, True)
        self.command([str(self.root / 'awg'), 'setconf', IFACE,
                      str(self.root / 'server.conf')], 'native configuration rejected (details redacted)')
        self.command(['ip', 'address', 'add', '10.213.211.1/30', 'dev', IFACE])
        self.command(['ip', 'link', 'set', 'dev', IFACE, 'mtu', '1280'])
        self.command(['ip', 'link', 'set', 'dev', IFACE, 'up'])
        for destination in ('1.1.1.1', '8.8.8.8', '9.9.9.9'):
            routes = self.json(['ip', '-j', '-4', 'route', 'get', destination,
                                'from', '10.213.211.2', 'iif', IFACE])
            if (len(routes) != 1 or routes[0].get('dev') != 'eth0'
                    or routes[0].get('gateway') != '10.0.0.1'):
                raise Failure('forward route does not use approved eth0 gateway')
        routes = self.json(['ip', '-j', '-4', 'route', 'get', '10.213.211.2'])
        if len(routes) != 1 or routes[0].get('dev') != IFACE:
            raise Failure('client return route does not use own interface')
        for spec in self.permits():
            self.rule(spec, True)

    def down(self):
        # A failed preflight must never clean up an older/foreign invocation.
        if not self.owned():
            return
        links = self.json(['ip', '-j', 'link', 'show'])
        if any(link['ifname'] == IFACE for link in links):
            self.command(['ip', 'link', 'set', 'dev', IFACE, 'down'])
            self.command(['ip', 'link', 'delete', 'dev', IFACE])
        # Interface is gone before deleting any isolation rules. Keep marker on failure.
        for spec in reversed(self.permits() + self.guards()):
            self.rule(spec, False)
        self.marker.unlink()
        # The daemon owns its UAPI socket; never delete the shared parent directory.


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('preflight', 'up', 'down'):
        raise Failure('expected preflight, up, or down')
    if os.geteuid() != 0:
        raise Failure('root required')
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    with (RUNTIME / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        lifecycle = Lifecycle()
        getattr(lifecycle, sys.argv[1])()


if __name__ == '__main__':
    try:
        main()
    except (Failure, OSError, ValueError, KeyError, TypeError) as error:
        # Failure messages above are fixed operator-facing literals, never command
        # output/config values. Unexpected exceptions must remain fully redacted.
        safe_error = str(error) if isinstance(error, Failure) else 'unexpected lifecycle failure (details redacted)'
        try:
            path = RUNTIME / 'last-error.json'
            path.write_text(json.dumps({'action': sys.argv[1], 'error': safe_error}) + '\n')
            path.chmod(0o600)
        except OSError:
            pass
        print('awg-s22-test: lifecycle failed; command/config details redacted', file=sys.stderr)
        sys.exit(1)
