#!/usr/bin/python3
"""France-only owned lifecycle. Import is inert; commands run only from explicit main()."""
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
import time

ROOT = Path('/etc/awg-fr')
RUNTIME = Path('/run/awg-fr')
IFACE = 'awgfr'
SOCKET = Path('/run/amneziawg/awgfr.sock')
NETWORK = ipaddress.ip_network('10.214.59.0/24')
SERVER = '10.214.59.1/24'
PORT = 49381
COMMENT = ['-m', 'comment', '--comment', 'awg-fr']
PINS = {
    'awg': '1ac92ba760092d805907a322f539c923673f5924666978612c3e85c0981bb005',
    'amneziawg-go': 'b53961c848acdc18f36ebd60f7a3f900a0e195be8e582eb721c05fa9ec6b2273',
}
PROFILE_KEYS = ('Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'S3', 'S4',
                'H1', 'H2', 'H3', 'H4', 'ContentPaddingAddition', 'RandomTrailers')
NON_PUBLIC = (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24',
    '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4',
)


class Failure(Exception):
    pass


def secure(path, mode, directory=False, uid=0):
    info = path.lstat()
    if (info.st_uid != uid or stat.S_IMODE(info.st_mode) != mode
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise Failure('private file ownership/type/mode mismatch')


def write_new(path, text):
    # O_EXCL also refuses dangling symlinks; no partially public file creation.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def key_check(value):
    try:
        if len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        raise Failure('invalid key encoding (redacted)') from None


def site_check(site):
    if set(site) != {'external_ipv4', 'external_prefix', 'external_interface', 'external_gateway'}:
        raise Failure('explicit external IPv4/prefix/interface/gateway required')
    if site['external_ipv4'] != '194.87.166.59':
        raise Failure('bundle is authorized for the France address only')
    if type(site['external_prefix']) is not int or not 0 <= site['external_prefix'] <= 32:
        raise Failure('explicit external prefix invalid')
    dev = site['external_interface']
    if not isinstance(dev, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', dev) or dev == IFACE:
        raise Failure('explicit external interface invalid')
    if not isinstance(site['external_gateway'], str):
        raise Failure('explicit IPv4 gateway required')
    try:
        gateway = ipaddress.IPv4Address(site['external_gateway'])
    except ValueError:
        raise Failure('explicit IPv4 gateway invalid') from None
    if gateway.is_unspecified or gateway.is_multicast or gateway.is_loopback:
        raise Failure('explicit IPv4 gateway invalid')
    return site


def profile_check(profile):
    if set(profile) != set(PROFILE_KEYS):
        raise Failure('approved AWG compatibility fields required')
    for key in PROFILE_KEYS[:-2]:
        pattern = r'[0-9]+(?:-[0-9]+)?' if key.startswith('H') else r'[0-9]+'
        if not isinstance(profile[key], str) or not re.fullmatch(pattern, profile[key]) or len(profile[key]) > 32:
            raise Failure('AWG compatibility value invalid')
    if (int(profile['Jmin']) > int(profile['Jmax'])
            or profile['ContentPaddingAddition'] != '4-28' or profile['RandomTrailers'] != 'on'):
        raise Failure('AWG compatibility contract mismatch')
    return profile


def native_peers(text):
    """Strict native setconf subset; never put rejected values into errors."""
    sections = []
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('['):
            if line not in ('[Interface]', '[Peer]'):
                raise Failure('native config section invalid')
            sections.append((line, {}))
            continue
        if not sections or '=' not in line:
            raise Failure('native config syntax invalid')
        key, value = (part.strip() for part in line.split('=', 1))
        key = key.lower()
        if not value or key in sections[-1][1]:
            raise Failure('native config duplicate/empty setting')
        sections[-1][1][key] = value
    interface_keys = {'privatekey', 'listenport', 'headerprotectionkey'} | {k.lower() for k in PROFILE_KEYS}
    if not sections or sections[0][0] != '[Interface]' or set(sections[0][1]) != interface_keys:
        raise Failure('native interface contract mismatch')
    interface = sections[0][1]
    if interface['listenport'] != str(PORT):
        raise Failure('native listen port mismatch')
    key_check(interface['privatekey'])
    key_check(interface['headerprotectionkey'])
    profile_check({k: interface[k.lower()] for k in PROFILE_KEYS})
    peers, public_keys, psks = [], set(), set()
    for section, settings in sections[1:]:
        if section != '[Peer]' or set(settings) != {'publickey', 'presharedkey', 'allowedips'}:
            raise Failure('native peer contract mismatch')
        key_check(settings['publickey'])
        key_check(settings['presharedkey'])
        try:
            address = ipaddress.ip_interface(settings['allowedips'])
        except ValueError:
            raise Failure('peer address invalid') from None
        if (address.version != 4 or address.network.prefixlen != 32 or address.ip not in NETWORK
                or int(address.ip) - int(NETWORK.network_address) not in range(2, 255)
                or str(address) in peers or settings['publickey'] in public_keys
                or settings['presharedkey'] in psks):
            raise Failure('peer address/key duplicate or outside owned pool')
        peers.append(str(address))
        public_keys.add(settings['publickey'])
        psks.add(settings['presharedkey'])
    return peers


class Runner:
    def run(self, argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise Failure('command unavailable or timed out') from None
        return result.returncode, result.stdout


class Lifecycle:
    def __init__(self, runner=None, root=ROOT, runtime=RUNTIME, socket=SOCKET,
                 forwarding=Path('/proc/sys/net/ipv4/ip_forward'),
                 interface_path=Path('/sys/class/net/awgfr'), invocation=None,
                 clock=time.monotonic, sleep=time.sleep, platform_check=None):
        self.runner = runner or Runner()
        self.root, self.runtime, self.socket = root, runtime, socket
        self.forwarding, self.interface_path = forwarding, interface_path
        self.invocation = invocation or os.environ.get('INVOCATION_ID')
        self.clock, self.sleep = clock, sleep
        self.platform_check = platform_check or self.platform
        self.marker = runtime / 'owned.json'
        self.site, self.peers = None, []

    @staticmethod
    def platform():
        if os.uname().machine != 'x86_64' or not Path('/dev/net/tun').exists():
            raise Failure('x86_64 and pre-existing TUN device required')

    def command(self, argv, message='network command failed (redacted)'):
        code, output = self.runner.run(argv)
        if code:
            raise Failure(message)
        return output

    def json(self, argv):
        try:
            return json.loads(self.command(argv))
        except (ValueError, TypeError):
            raise Failure('network inspection invalid') from None

    def owned(self):
        if not self.invocation or not self.marker.exists():
            return None
        secure(self.marker, 0o600)
        metadata = json.loads(self.marker.read_text())
        return metadata if metadata.get('invocation') == self.invocation else None

    @staticmethod
    def rule_args(args):
        return list(args) if '--comment' in args else list(args) + COMMENT

    def rule(self, spec, add, position=1):
        tool, table, chain, args = spec
        base = [tool, '-w', '5', '-t', table]
        args = self.rule_args(args)
        code, _ = self.runner.run(base + ['-C', chain] + args)
        if code not in (0, 1):
            raise Failure('firewall check failed')
        if add and code == 1:
            self.command(base + ['-I', chain, str(position)] + args, 'firewall insert failed')
        elif not add:
            while code == 0:
                self.command(base + ['-D', chain] + args, 'firewall delete failed')
                code, _ = self.runner.run(base + ['-C', chain] + args)
                if code not in (0, 1):
                    raise Failure('firewall check failed')

    @staticmethod
    def guards():
        return [(tool, 'filter', chain, args)
                for tool in ('iptables', 'ip6tables')
                for chain, args in (
                    ('INPUT', ['-i', IFACE, '-j', 'DROP']),
                    ('FORWARD', ['-i', IFACE, '-j', 'DROP']),
                    ('FORWARD', ['-o', IFACE, '-j', 'DROP']))]

    @classmethod
    def staging(cls):
        # Separate exact matches remain at the chain head until all allows/drops exist.
        return [(tool, table, chain, args + ['-m', 'comment', '--comment', 'awg-fr-startup'])
                for tool, table, chain, args in cls.guards()]

    def permits(self):
        dev = self.site['external_interface']
        rules = []
        for peer in self.peers:
            rules += [
                ('iptables', 'nat', 'POSTROUTING', ['-s', peer, '-o', dev, '-j', 'MASQUERADE']),
                ('iptables', 'filter', 'FORWARD', ['-i', dev, '-o', IFACE, '-d', peer,
                  '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT']),
                ('iptables', 'filter', 'FORWARD', ['-i', IFACE, '-s', peer, '-o', dev, '-j', 'ACCEPT']),
            ]
        return rules + [
            ('iptables', 'filter', 'FORWARD', ['-i', IFACE, '-d', dst, '-j', 'DROP'])
            for dst in NON_PUBLIC
        ] + [('iptables', 'filter', 'INPUT', ['-i', dev, '-d', self.site['external_ipv4'],
               '-p', 'udp', '--dport', str(PORT), '-j', 'ACCEPT'])]

    def config_check(self):
        secure(self.root, 0o700, directory=True)
        for name in ('site.json', 'server.conf'):
            secure(self.root / name, 0o600)
        for name, digest in PINS.items():
            secure(self.root / name, 0o700)
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != digest:
                raise Failure('pinned executable hash mismatch')
        self.site = site_check(json.loads((self.root / 'site.json').read_text()))
        self.peers = native_peers((self.root / 'server.conf').read_text())

    def route_check(self, source, incoming=None):
        for destination in ('1.1.1.1', '8.8.8.8', '9.9.9.9'):
            argv = ['ip', '-j', '-4', 'route', 'get', destination, 'from', source]
            if incoming:
                argv += ['iif', incoming]
            routes = self.json(argv)
            if (len(routes) != 1 or routes[0].get('dev') != self.site['external_interface']
                    or routes[0].get('gateway') != self.site['external_gateway']):
                raise Failure('route differs from explicit approved interface/gateway')

    def forwarding_check(self, owned=False):
        interfaces = ['default', self.site['external_interface']] + ([IFACE] if owned else [])
        paths = [self.forwarding] + [self.forwarding.parent / 'conf' / dev / 'forwarding' for dev in interfaces]
        if any(path.read_text().strip() != '1' for path in paths):
            raise Failure('IPv4 global/default/interface forwarding must already be enabled; no sysctl writes')

    def preflight(self):
        if not self.invocation:
            raise Failure('systemd invocation identity required')
        self.config_check()
        self.platform_check()
        self.forwarding_check()
        if self.marker.exists() or self.marker.is_symlink():
            raise Failure('stale ownership metadata; refusing adoption')
        links = self.json(['ip', '-j', 'link', 'show'])
        if any(link['ifname'] == IFACE for link in links) or self.socket.exists() or self.socket.is_symlink():
            raise Failure('interface/UAPI conflict; refusing adoption')
        addresses = self.json(['ip', '-j', '-4', 'address', 'show'])
        if not any(item['ifname'] == self.site['external_interface'] and any(
                addr.get('local') == self.site['external_ipv4']
                and addr.get('prefixlen') == self.site['external_prefix']
                for addr in item.get('addr_info', [])) for item in addresses):
            raise Failure('external address/interface/prefix mismatch')
        for item in addresses:
            for addr in item.get('addr_info', []):
                if ipaddress.ip_network(f"{addr['local']}/{addr['prefixlen']}", strict=False).overlaps(NETWORK):
                    raise Failure('owned subnet overlaps existing address')
        for route in self.json(['ip', '-j', '-4', 'route', 'show', 'table', 'all']):
            if route.get('dst', 'default') != 'default' and ipaddress.ip_network(route['dst']).overlaps(NETWORK):
                raise Failure('owned subnet overlaps existing route')
        self.route_check(self.site['external_ipv4'])
        if self.command(['ss', '-H', '-lun', f'sport = :{PORT}']).strip():
            raise Failure('UDP port conflict')
        # Refuse any stale reference, not just an exact current peer rule.
        for tool, table in (('iptables', 'filter'), ('iptables', 'nat'), ('ip6tables', 'filter')):
            for line in self.command([tool, '-w', '5', '-t', table, '-S']).splitlines():
                if any(token in ('awg-fr', IFACE) for token in shlex.split(line)):
                    raise Failure('stale firewall resource; refusing adoption')
        rules = self.staging() + self.guards() + self.permits()
        for tool, table, chain, args in rules:
            code, _ = self.runner.run([tool, '-w', '5', '-t', table, '-C', chain] + self.rule_args(args))
            if code != 1:
                raise Failure('firewall preflight conflict or check failure')
        write_new(self.marker, json.dumps({'invocation': self.invocation, 'ifindex': None,
                                          'rules': rules, 'config_hashes': self.config_hashes()}) + '\n')

    def config_hashes(self):
        return {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                for name in ('site.json', 'server.conf')}

    def capture_interface(self, metadata):
        if self.interface_path.exists():
            index = int((self.interface_path / 'ifindex').read_text())
            if metadata['ifindex'] is None:
                metadata['ifindex'] = index
                # Atomic snapshot update; keep old metadata if replace fails.
                pending = self.runtime / 'owned.pending'
                write_new(pending, json.dumps(metadata) + '\n')
                os.replace(pending, self.marker)
            elif metadata['ifindex'] != index:
                raise Failure('owned interface identity changed')

    def up(self):
        metadata = self.owned()
        if not metadata:
            raise Failure('current invocation ownership required')
        # Config may have been replaced between preflight and up: reject drift.
        self.config_check()
        if (json.loads(json.dumps(self.staging() + self.guards() + self.permits())) != metadata['rules']
                or self.config_hashes() != metadata['config_hashes']):
            raise Failure('configuration changed after preflight')
        deadline = self.clock() + 10
        while True:
            self.capture_interface(metadata)
            if self.socket.is_socket() and metadata['ifindex'] is not None:
                break
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise Failure('interface/UAPI readiness exceeded ten seconds')
            self.sleep(min(0.1, remaining))
        links = self.json(['ip', '-j', 'link', 'show'])
        if not any(link['ifname'] == IFACE and link['ifindex'] == metadata['ifindex']
                   and 'UP' not in link.get('flags', []) for link in links):
            raise Failure('new owned interface must still be down')
        self.forwarding_check(owned=True)
        for spec in self.staging():
            self.rule(spec, True)
        self.command([str(self.root / 'awg'), 'setconf', IFACE, str(self.root / 'server.conf')],
                     'native configuration rejected (redacted)')
        self.command(['ip', 'address', 'add', SERVER, 'dev', IFACE])
        self.command(['ip', 'link', 'set', 'dev', IFACE, 'mtu', '1280'])
        self.command(['ip', 'link', 'set', 'dev', IFACE, 'up'])
        for peer in self.peers:
            address = peer.split('/')[0]
            self.route_check(address, IFACE)
            routes = self.json(['ip', '-j', '-4', 'route', 'get', address])
            if len(routes) != 1 or routes[0].get('dev') != IFACE:
                raise Failure('peer return route differs from owned interface')
        for spec in self.guards() + self.permits():
            # Keep both startup FORWARD drops (or one INPUT drop) ahead of changes.
            position = 3 if spec[1:3] == ('filter', 'FORWARD') else 2 if spec[1:3] == ('filter', 'INPUT') else 1
            self.rule(spec, True, position)
        for spec in self.staging():
            self.rule(spec, False)

    def down(self):
        metadata = self.owned()
        if not metadata:
            return
        links = [link for link in self.json(['ip', '-j', 'link', 'show']) if link['ifname'] == IFACE]
        if links:
            if metadata['ifindex'] is None or len(links) != 1 or links[0]['ifindex'] != metadata['ifindex']:
                raise Failure('cannot prove interface ownership; metadata retained')
            self.command(['ip', 'link', 'set', 'dev', IFACE, 'down'])
            self.command(['ip', 'link', 'delete', 'dev', IFACE])
            if any(link['ifname'] == IFACE for link in self.json(['ip', '-j', 'link', 'show'])):
                raise Failure('interface deletion not confirmed; guards and metadata retained')
        # Snapshot, not current config: revocation/config edits cannot strand old rules.
        for spec in reversed(metadata['rules']):
            self.rule(spec, False)
        self.marker.unlink()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('preflight', 'up', 'down'):
        raise Failure('expected preflight, up, or down')
    if os.geteuid() != 0:
        raise Failure('root required')
    secure(ROOT, 0o700, directory=True)
    secure(RUNTIME, 0o700, directory=True)
    with (RUNTIME / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        getattr(Lifecycle(), sys.argv[1])()


if __name__ == '__main__':
    try:
        main()
    except (Failure, OSError, ValueError, KeyError, TypeError):
        # Neither daemon errors nor config/key values enter stdout/journal.
        print('awg-fr: lifecycle failed (details redacted); preserve runtime metadata', file=sys.stderr)
        sys.exit(1)
