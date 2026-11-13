#!/usr/bin/env python3
"""Render one additive server from private pilot state; never print secrets."""
import argparse
import json
import os
from pathlib import Path
import uuid


def render(state, keys, node_id, canary=None):
    node = next(n for n in state['nodes'] if n['id'] == node_id)
    expected = {'france': ('194.87.166.59', 443),
                'frankfurt': ('31.58.85.163', 34443),
                'poland': ('193.124.205.153', 34443),
                'italy': ('81.29.155.74', 34443)}
    if (node['host'], node['port']) != expected[node_id] or not node['enabled']:
        raise ValueError('Unexpected pilot endpoint')
    key = keys[node_id]
    if key['public_key'] != node['public_key']:
        raise ValueError('Public/private state key mismatch')
    users = []
    for device in state['devices']:
        if device['enabled']:
            value = str(uuid.UUID(device['credentials'][node_id]['uuid']))
            users.append({'name': device['id'], 'uuid': value,
                          'flow': 'xtls-rprx-vision'})
    if canary:
        users.append({'name': 'pilot-canary', 'uuid': str(uuid.UUID(canary)),
                      'flow': 'xtls-rprx-vision'})
    if not users or len({u['uuid'] for u in users}) != len(users):
        raise ValueError('Missing or duplicate users')
    return {
        'log': {'level': 'warn', 'timestamp': True},
        'dns': {'servers': [{'type': 'local', 'tag': 'local'}]},
        'inbounds': [{
            'type': 'vless', 'tag': 'pilot-vless', 'listen': node['host'],
            'listen_port': node['port'], 'users': users,
            'tls': {'enabled': True, 'server_name': node['server_name'],
                    'reality': {'enabled': True,
                                'handshake': {'server': node['server_name'],
                                              'server_port': 443},
                                'private_key': key['private_key'],
                                'short_id': [node['short_id']]}}
        }],
        'outbounds': [{'type': 'direct', 'tag': 'direct'}],
        'route': {'default_domain_resolver': 'local',
                  'rules': [{'action': 'resolve', 'strategy': 'ipv4_only'},
                            {'ip_is_private': True, 'action': 'reject'},
                            {'ip_cidr': ['100.64.0.0/10', '224.0.0.0/4',
                                         '240.0.0.0/4', 'ff00::/8'],
                             'action': 'reject'}],
                  'final': 'direct'}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--keys', required=True, type=Path)
    parser.add_argument('--node', required=True, choices=['france', 'frankfurt', 'poland', 'italy'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--canary-uuid')
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[4]
    if args.output.resolve().is_relative_to(repository):
        parser.error('Private output must be outside the repository')
    config = render(json.loads(args.state.read_text()),
                    json.loads(args.keys.read_text()), args.node, args.canary_uuid)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, 'w') as target:
        json.dump(config, target, indent=2)
        target.write('\n')


if __name__ == '__main__':
    main()
