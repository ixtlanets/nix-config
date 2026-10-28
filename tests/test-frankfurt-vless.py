#!/usr/bin/env python3
"""Check Frankfurt endpoint and the two verified Linux routing policies."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parent.parent / 'secrets' / 'vless'
errors = []
count = 0
for path in sorted(root.glob('*.json')):
    data = json.loads(path.read_text())
    for outbound in data.get('outbounds', []):
        if outbound.get('type') == 'vless' and outbound.get('server') in ('31.58.85.163', 'wire.nikcode.xyz'):
            count += 1
            if outbound.get('server_port') != 24443:
                errors.append(f'{path.name}: Frankfurt port must be 24443')
            if path.name in ('zenbook.json', 'um790pro.json') and outbound.get('detour'):
                errors.append(f'{path.name}: Frankfurt must not use a detour')
    if path.name in ('zenbook.json', 'um790pro.json'):
        rules = [r for r in data.get('route', {}).get('rules', []) if r.get('outbound') == 'london']
        if len(rules) != 1 or rules[0].get('domain_suffix') != ['google.com']:
            errors.append(f'{path.name}: London rule must contain only google.com')
for path in sorted(root.glob('*.vless.txt')):
    u = urlsplit(path.read_text().strip())
    if u.hostname in ('31.58.85.163', 'wire.nikcode.xyz'):
        count += 1
        if u.port != 24443:
            errors.append(f'{path.name}: Frankfurt link must use 24443')
if not count:
    errors.append('No Frankfurt profiles found')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
print(f'PASS: {count} Frankfurt profiles use 24443; verified Linux routing is direct')
