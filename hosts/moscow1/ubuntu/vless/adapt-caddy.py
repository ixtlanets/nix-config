#!/usr/bin/env python3
"""Adapt privately to native JSON: Caddy 2.6 lacks the persist_config Caddyfile option."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def adapt(source, destination, caddy='/usr/bin/caddy'):
    result = subprocess.run([caddy, 'adapt', '--config', str(source), '--adapter', 'caddyfile'],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Adaptation failed')
    config = json.loads(result.stdout)
    if config.get('admin', {}).get('listen') != 'localhost:2019':
        raise ValueError('Unexpected admin listener')
    config['admin']['config'] = {'persist': False}
    # Exclusive creation, no symlinks/overwrite; never print adapter diagnostics or JSON.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(config, output, indent=2)
        output.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('new_json', type=Path)
    parser.add_argument('--caddy', default='/usr/bin/caddy')
    args = parser.parse_args()
    try:
        adapt(args.source, args.new_json, args.caddy)
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Private Caddy adaptation failed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
