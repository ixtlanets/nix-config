#!/usr/bin/python3
"""Offline file issuer. No service/network actions; real keys ONLY on explicit init/add."""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import control


class Keygen:
    def __init__(self, binary):
        self.binary = Path(binary)
        control.secure(self.binary, 0o700, uid=os.geteuid())
        if hashlib.sha256(self.binary.read_bytes()).hexdigest() != control.PINS['awg']:
            raise control.Failure('issuer requires pinned awg binary')

    def run(self, action, value=None):
        try:
            result = subprocess.run([str(self.binary), action], input=value, capture_output=True,
                                    text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            raise control.Failure('key generation failed (redacted)') from None
        if result.returncode:
            raise control.Failure('key generation failed (redacted)')
        key = result.stdout.strip()
        control.key_check(key)
        return key


def private_dir(path):
    control.secure(path, 0o700, directory=True, uid=os.geteuid())


def load(path):
    control.secure(path, 0o600, uid=os.geteuid())
    return json.loads(path.read_text())


def save(path, data):
    control.write_new(path, json.dumps(data, indent=2) + '\n')


def check_dns(values):
    if not isinstance(values, list) or not values:
        raise control.Failure('explicit public IPv4 client DNS required')
    for value in values:
        try:
            address = ipaddress.IPv4Address(value)
        except (ValueError, TypeError):
            raise control.Failure('client DNS must be public IPv4') from None
        if not address.is_global or any(address in ipaddress.ip_network(net) for net in control.NON_PUBLIC):
            raise control.Failure('client DNS must be public IPv4')
    return values


def init(directory, settings, keys):
    if set(settings) != {'site', 'profile', 'client_dns'}:
        raise control.Failure('site/profile/client_dns settings required')
    control.site_check(settings['site'])
    control.profile_check(settings['profile'])
    check_dns(settings['client_dns'])
    directory.mkdir(mode=0o700)  # Refuses existing directory, never adopts/overwrites.
    private_dir(directory)
    for name in ('users', 'clients'):
        (directory / name).mkdir(mode=0o700)
    private = keys.run('genkey')
    identity = {'private': private, 'public': keys.run('pubkey', private + '\n'),
                'header': keys.run('genpsk')}
    save(directory / 'identity.json', identity)
    save(directory / 'site.json', settings['site'])
    save(directory / 'profile.json', settings['profile'])
    save(directory / 'dns.json', settings['client_dns'])


def state(directory):
    private_dir(directory)
    private_dir(directory / 'users')
    private_dir(directory / 'clients')
    identity = load(directory / 'identity.json')
    for key in ('private', 'public', 'header'):
        control.key_check(identity[key])
    site = control.site_check(load(directory / 'site.json'))
    profile = control.profile_check(load(directory / 'profile.json'))
    dns = check_dns(load(directory / 'dns.json'))
    return identity, site, profile, dns


def users(directory):
    result = {}
    for path in sorted((directory / 'users').iterdir()):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}\.json', path.name):
            raise control.Failure('unexpected user state entry')
        user = load(path)
        if set(user) != {'address', 'private', 'public', 'psk'}:
            raise control.Failure('invalid user state')
        for field in ('private', 'public', 'psk'):
            control.key_check(user[field])
        result[path.stem] = user
    # Reuse the native parser to reject duplicate keys, PSKs and /32 addresses.
    return result


def interface_lines(identity, profile, client_private=None):
    return ['[Interface]', 'PrivateKey = ' + (client_private or identity['private']),
            *[f'{key} = {profile[key]}' for key in control.PROFILE_KEYS],
            'HeaderProtectionKey = ' + identity['header']]


def server_text(identity, profile, active):
    lines = interface_lines(identity, profile) + [f'ListenPort = {control.PORT}']
    for user in active.values():
        lines += ['', '[Peer]', 'PublicKey = ' + user['public'],
                  'PresharedKey = ' + user['psk'], 'AllowedIPs = ' + user['address']]
    text = '\n'.join(lines) + '\n'
    control.native_peers(text)
    return text


def add(directory, name, keys):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', name):
        raise control.Failure('invalid user name')
    identity, site, profile, dns = state(directory)
    active = users(directory)
    server_text(identity, profile, active)
    client_path, user_path = directory / 'clients' / (name + '.conf'), directory / 'users' / (name + '.json')
    if client_path.exists() or client_path.is_symlink() or user_path.exists() or user_path.is_symlink():
        raise control.Failure('user already exists; no overwrite')
    taken = {user['address'] for user in active.values()}
    address = next((f'{control.NETWORK.network_address + index}/32'
                    for index in range(2, 255)
                    if f'{control.NETWORK.network_address + index}/32' not in taken), None)
    if not address:
        raise control.Failure('peer pool exhausted')
    private = keys.run('genkey')
    user = {'address': address, 'private': private,
            'public': keys.run('pubkey', private + '\n'), 'psk': keys.run('genpsk')}
    server_text(identity, profile, {**active, name: user})
    if private == identity['private'] or any(private == other['private'] for other in active.values()):
        raise control.Failure('generated private key reused; refusing issue')
    lines = interface_lines(identity, profile, private) + [
        'Address = ' + address, 'MTU = 1280', 'DNS = ' + ', '.join(dns), '', '[Peer]',
        'PublicKey = ' + identity['public'], 'PresharedKey = ' + user['psk'],
        f'Endpoint = {site["external_ipv4"]}:{control.PORT}',
        'AllowedIPs = 0.0.0.0/0, ::/0', 'PersistentKeepalive = 25']
    # Save allocation first: a subsequent write failure never silently reallocates it.
    save(user_path, user)
    control.write_new(client_path, '\n'.join(lines) + '\n')


def render(directory, output, exclude):
    identity, _, profile, _ = state(directory)
    active = users(directory)
    if not set(exclude) <= set(active):
        raise control.Failure('cannot exclude unknown user')
    for name in exclude:
        del active[name]
    private_dir(output.parent)
    control.write_new(output, server_text(identity, profile, active))
    # Deliberately no replace, service calls, live revocation or client reissue.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    actions = parser.add_subparsers(dest='action', required=True)
    init_parser = actions.add_parser('init')
    init_parser.add_argument('--settings', type=Path, required=True)
    add_parser = actions.add_parser('add')
    add_parser.add_argument('name')
    for command in (init_parser, add_parser):
        command.add_argument('--generate-new-keys', action='store_true', required=True)
        command.add_argument('--awg', type=Path, required=True)
    render_parser = actions.add_parser('render')
    render_parser.add_argument('--output', type=Path, required=True)
    render_parser.add_argument('--exclude', action='append', default=[])
    args = parser.parse_args()
    directory = args.directory.resolve()
    repo = Path(__file__).resolve().parents[4]
    targets = [directory]
    if args.action == 'render':
        targets.append(args.output.resolve())
    if any(target == repo or repo in target.parents for target in targets):
        raise control.Failure('runtime state/output must be outside repository')
    if args.action == 'init':
        # Input is public reviewed settings, not a client/private configuration.
        init(directory, json.loads(args.settings.read_text()), Keygen(args.awg))
        return
    private_dir(directory)
    # Serialize issuance/render; lock and every secret file are 0600.
    fd = os.open(directory / 'issuer.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        control.secure(directory / 'issuer.lock', 0o600, uid=os.geteuid())
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == 'add':
            add(directory, args.name, Keygen(args.awg))
        else:
            render(directory, args.output.resolve(), args.exclude)


if __name__ == '__main__':
    try:
        main()
    except (control.Failure, OSError, ValueError, KeyError, TypeError):
        print('awg-uk issuer failed (details redacted); inspect private state, do not overwrite', file=sys.stderr)
        sys.exit(1)
