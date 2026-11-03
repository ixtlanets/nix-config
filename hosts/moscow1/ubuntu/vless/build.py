#!/usr/bin/env python3
"""Build a private, offline Moscow pilot bundle (stdlib only). Never prints input."""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import re
import sys
import uuid

HOST = 'moscow1.nikcode.xyz'
IP = '132.243.191.232'
FINGERPRINTS = {'chrome', 'firefox', 'edge', 'safari', '360', 'qq', 'ios', 'android',
                'random', 'randomized'}


def require(condition):
    if not condition:
        raise ValueError('Input does not match the pilot schema.')


def fields(value, required, optional=()):
    require(isinstance(value, dict))
    require(set(required) <= value.keys() <= set(required) | set(optional))


def text_match(value, pattern):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None)


def hostname(value):
    text_match(value, r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')


def key(value):
    text_match(value, r'[A-Za-z0-9_-]{43}')
    require(base64.urlsafe_b64encode(base64.urlsafe_b64decode(value + '=')).decode().rstrip('=') == value)


def short_id(value):
    text_match(value, r'(?:[0-9a-f]{2}){1,8}')


def identity(value):
    require(isinstance(value, str))
    require(str(uuid.UUID(value)) == value and uuid.UUID(value).int != 0)


def outbound(value):
    fields(value, ('type', 'server', 'server_port', 'uuid', 'flow', 'tls'),
           ('tag', 'packet_encoding'))
    require(value['type'] == 'vless' and value['server'] == '31.58.85.163')
    require(type(value['server_port']) is int and value['server_port'] == 24443)
    identity(value['uuid'])
    require(value['flow'] == 'xtls-rprx-vision')
    if 'tag' in value:
        text_match(value['tag'], r'[A-Za-z0-9_-]{1,64}')
    if 'packet_encoding' in value:
        require(value['packet_encoding'] == 'xudp')
    tls = value['tls']
    fields(tls, ('enabled', 'server_name', 'utls', 'reality'), ('insecure', 'alpn'))
    require(tls['enabled'] is True and tls.get('insecure', False) is False)
    if 'alpn' in tls:
        alpn = tls['alpn']
        require(isinstance(alpn, list) and len(alpn) > 0)
        require(all(isinstance(item, str) and item in ('h2', 'http/1.1') for item in alpn))
        require(len(set(alpn)) == len(alpn))
    hostname(tls['server_name'])
    fields(tls['utls'], ('enabled', 'fingerprint'))
    require(tls['utls']['enabled'] is True and tls['utls']['fingerprint'] in FINGERPRINTS)
    fields(tls['reality'], ('enabled', 'public_key', 'short_id'))
    require(tls['reality']['enabled'] is True)
    key(tls['reality']['public_key'])
    short_id(tls['reality']['short_id'])


def validate(data):
    fields(data, ('hostname', 'ip', 'reality_private_key', 'reality_public_key',
                  'short_id', 'frankfurt_outbound', 'devices'))
    hostname(data['hostname'])
    require(data['hostname'] == HOST and data['ip'] == IP)
    key(data['reality_private_key'])
    key(data['reality_public_key'])
    short_id(data['short_id'])
    outbound(data['frankfurt_outbound'])
    require(isinstance(data['devices'], list) and 1 <= len(data['devices']) <= 13)
    names, uuids, tokens, fallbacks = set(), set(), set(), set()
    for device in data['devices']:
        fields(device, ('name', 'uuid', 'subscription_token', 'direct_frankfurt_outbound'))
        text_match(device['name'], r'[a-z][a-z0-9-]{0,47}')
        identity(device['uuid'])
        token = device['subscription_token']
        text_match(token, r'[A-Za-z0-9_-]{43,128}')
        # Length is a lower bound, not proof of randomness; the operator uses secrets.token_urlsafe(32).
        require(len(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))) >= 32)
        outbound(device['direct_frankfurt_outbound'])
        fallback = device['direct_frankfurt_outbound']['uuid']
        require(device['name'] not in names and device['uuid'] not in uuids
                and token not in tokens and fallback not in fallbacks)
        names.add(device['name'])
        uuids.add(device['uuid'])
        tokens.add(token)
        fallbacks.add(fallback)
    # The pilot transit may use an existing authorized identity; Moscow UUIDs must be fresh.
    require(not uuids & (fallbacks | {data['frankfurt_outbound']['uuid']}))


def server_config(data):
    transit = copy.deepcopy(data['frankfurt_outbound'])
    transit['tag'] = 'frankfurt'
    return {
        'log': {'disabled': True},
        'inbounds': [{'type': 'vless', 'tag': 'moscow', 'listen': '::', 'listen_port': 24443,
                      'users': [{'name': d['name'], 'uuid': d['uuid'], 'flow': 'xtls-rprx-vision'}
                                for d in data['devices']],
                      'tls': {'enabled': True, 'server_name': 'www.google.com',
                              'reality': {'enabled': True,
                                          'handshake': {'server': 'www.google.com', 'server_port': 443},
                                          'private_key': data['reality_private_key'],
                                          'short_id': [data['short_id']]}}}],
        'outbounds': [transit],
        'route': {'rules': [{'action': 'sniff'},
                            {'ip_is_private': True, 'action': 'reject'},
                            {'domain_suffix': ['localhost', 'local', 'lan', 'home.arpa'],
                             'action': 'reject'}], 'final': 'frankfurt'},
    }


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result)
        result[name] = value
    return result


def moscow_outbound(data, device):
    return {'type': 'vless', 'tag': 'proxy', 'server': HOST, 'server_port': 24443,
            'uuid': device['uuid'], 'flow': 'xtls-rprx-vision', 'packet_encoding': 'xudp',
            'tls': {'enabled': True, 'server_name': 'www.google.com',
                    'utls': {'enabled': True, 'fingerprint': 'firefox'},
                    'reality': {'enabled': True, 'public_key': data['reality_public_key'],
                                'short_id': data['short_id']}}}


def xray_outbound(value):
    tls = value['tls']
    result = {
        'tag': 'proxy', 'protocol': 'vless',
        'settings': {'vnext': [{'address': value['server'], 'port': value['server_port'],
                                'users': [{'id': value['uuid'], 'encryption': 'none',
                                           'flow': value['flow']}]}]},
        'streamSettings': {'network': 'tcp', 'security': 'reality',
                           'sockopt': {'domainStrategy': 'UseIPv4'},
                           'realitySettings': {'serverName': tls['server_name'],
                                               'fingerprint': tls['utls']['fingerprint'],
                                               'publicKey': tls['reality']['public_key'],
                                               'shortId': tls['reality']['short_id']}},
    }
    if 'packet_encoding' in value:
        result['settings']['packetEncoding'] = value['packet_encoding']
    if 'alpn' in tls:
        result['streamSettings']['realitySettings']['alpn'] = tls['alpn'][:]
    return result


def xray_profile(label, value):
    return {
        'remarks': label,
        'log': {'loglevel': 'none', 'access': 'none', 'error': 'none'},
        # Static direct bootstrap: the proxy dial never needs its own proxied DNS.
        'dns': {'hosts': {HOST: IP}, 'servers': ['https://1.1.1.1/dns-query'],
                'queryStrategy': 'UseIPv4', 'tag': 'dns-internal'},
        'inbounds': [
            {'tag': 'socks', 'listen': '127.0.0.1', 'port': 10808, 'protocol': 'socks',
             'settings': {'auth': 'noauth', 'udp': True},
             'sniffing': {'enabled': True, 'destOverride': ['http', 'tls', 'quic'], 'routeOnly': True}},
            {'tag': 'http', 'listen': '127.0.0.1', 'port': 10809, 'protocol': 'http', 'settings': {}},
        ],
        'outbounds': [xray_outbound(value),
                      {'tag': 'direct', 'protocol': 'freedom', 'settings': {'domainStrategy': 'UseIPv4'}},
                      {'tag': 'block', 'protocol': 'blackhole', 'settings': {}}],
        # Keep the first outbound as the default: a catch-all rule would prevent
        # IPIfNonMatch from resolving domains for the private/RU IP exceptions.
        'routing': {'domainStrategy': 'IPIfNonMatch', 'rules': [
            {'type': 'field', 'network': 'udp', 'port': '443', 'outboundTag': 'block'},
            {'type': 'field', 'inboundTag': ['dns-internal'], 'outboundTag': 'proxy'},
            {'type': 'field', 'domain': ['full:' + HOST, 'geosite:private',
                                        'domain:localhost', 'domain:local', 'domain:lan',
                                        'domain:home.arpa', 'geosite:category-ru'], 'outboundTag': 'direct'},
            {'type': 'field', 'ip': ['geoip:private', 'geoip:ru'], 'outboundTag': 'direct'},
        ]},
    }


def loopback_client(data, value):
    proxy = copy.deepcopy(value)
    proxy['tag'] = 'proxy'
    # Use the fixed IP offline; the VLESS payload still carries destination hostnames.
    return {'log': {'disabled': True},
            'dns': {'servers': [{'type': 'hosts', 'tag': 'bootstrap',
                                 'predefined': {HOST: [IP]}}], 'final': 'bootstrap',
                    'strategy': 'ipv4_only'},
            'inbounds': [{'type': 'mixed', 'tag': 'test', 'listen': '127.0.0.1', 'listen_port': 11808}],
            'outbounds': [proxy], 'route': {'final': 'proxy', 'default_domain_resolver': 'bootstrap'}}


def caddy_site(data):
    # No access log is configured. Drop request/error and admin API runtime loggers,
    # which can include full URIs or configs; keep TLS/ACME operational messages.
    routes = []
    for index, device in enumerate(data['devices']):
        path = '/s/' + device['subscription_token'] + '/incy.json'
        routes.append(
            '    @device' + str(index) + ' expression `'
            '{http.request.orig_uri} == "' + path + '" && '
            '{http.request.method} in ["GET", "HEAD"]`\n'
            '    handle @device' + str(index) + ' {\n'
            '        rewrite * ' + path + '\n'
            '        file_server {\n'
            '            root /var/lib/moscow1/subscriptions\n'
            '        }\n'
            '    }\n')
    return '''# Managed by moscow1-vless pilot
{
    admin localhost:2019
    auto_https disable_redirects
    storage file_system /var/lib/caddy/moscow1
    log default {
        exclude http.log.access http.log.error admin.api
    }
}
https://moscow1.nikcode.xyz {
    header {
        Cache-Control "no-store"
        X-Content-Type-Options "nosniff"
    }
    @health expression `{http.request.orig_uri} == "/healthz" && {http.request.method} in ["GET", "HEAD"]`
    handle @health {
        respond "ok" 200
    }
''' + ''.join(routes) + '''    handle {
        respond "" 404
    }
    handle_errors {
        header Cache-Control "no-store"
        respond "" 404
    }
}
:80 {
    header Cache-Control "no-store"
    respond "" 404
}
'''


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def build(source, destination):
    data = json.loads(source.read_text(), object_pairs_hook=unique_object)
    validate(data)
    destination.mkdir(mode=0o700, exist_ok=False)
    write_json(destination / 'server.json', server_config(data))
    (destination / 'Caddyfile').write_text(caddy_site(data))
    for name in ('moscow1-vless.service', 'caddy-override.conf'):
        (destination / name).write_text((Path(__file__).parent / name).read_text())
    for device in data['devices']:
        directory = destination / 'subscriptions' / 's' / device['subscription_token']
        directory.mkdir(parents=True, mode=0o700)
        primary = moscow_outbound(data, device)
        fallback = device['direct_frankfurt_outbound']
        write_json(directory / 'incy.json', [xray_profile('Moscow', primary),
                                           xray_profile('Frankfurt direct backup', fallback)])
        tests = destination / 'client-tests' / device['name']
        tests.mkdir(parents=True, mode=0o700)
        write_json(tests / 'moscow.json', loopback_client(data, primary))
        write_json(tests / 'frankfurt.json', loopback_client(data, fallback))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_input', type=Path)
    parser.add_argument('new_output_directory', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        build(args.private_input, args.new_output_directory)
    except (ValueError, TypeError, KeyError, OSError):
        print('Bundle rejected: invalid schema or unavailable new output directory.', file=sys.stderr)
        return 1
    print('Private bundle created.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
