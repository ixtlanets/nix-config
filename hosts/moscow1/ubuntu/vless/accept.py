#!/usr/bin/env python3
"""Parent-run native acceptance; private evidence, owned loopback clients, no TUN/restarts."""
import argparse
from contextlib import contextmanager
import copy
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import uuid

HOST = 'moscow1.nikcode.xyz'
ENGINE_SHA = 'a056076cff3aa1ced5ed794743b9f87b2dee7dc068280d2665c1e0b45533e793'


def require(condition):
    if not condition:
        raise ValueError('Acceptance gate failed; inspect private evidence.')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def test_server(server, port, blocked_port=None):
    result = copy.deepcopy(server)
    inbound = result['inbounds'][0]
    inbound.update(listen='127.0.0.1', listen_port=port, tag='TESTSERVER')
    if blocked_port is not None:
        result['outbounds'][0].update(server='127.0.0.1', server_port=blocked_port)
    return result


@contextmanager
def running(engine, config, directory, label, port):
    # Refuse occupied ports; never kill or adopt an existing listener.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
    path = directory / (label + '.json')
    write_json(path, config)
    check = subprocess.run([engine, 'check', '-c', str(path)], capture_output=True, timeout=15)
    require(check.returncode == 0)
    with (directory / (label + '.log')).open('wb') as log:
        process = subprocess.Popen([engine, 'run', '-c', str(path)], stdout=log, stderr=log)
        try:
            for _ in range(100):
                require(process.poll() is None)
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        pass
                    time.sleep(0.1)
                    require(process.poll() is None)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise ValueError('Owned listener did not become ready.')
            yield
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def egress(expected, should_succeed):
    result = subprocess.run(
        ['curl', '--silent', '--show-error', '--fail', '--noproxy', '',
         '--proxy', 'socks5h://127.0.0.1:11808', '--connect-timeout', '5',
         '--max-time', '20', 'https://api.ipify.org'], capture_output=True, timeout=25)
    if should_succeed:
        require(result.returncode == 0 and result.stdout.decode().strip() == expected)
    else:
        # An unexpected egress of ANY address fails the negative control.
        require(result.returncode != 0 and not result.stdout)


def subscriptions(bundle, directory):
    files = sorted((bundle / 'subscriptions' / 's').glob('*/incy.json'))
    require(bool(files))
    for index, source in enumerate(files):
        path = '/s/' + source.parent.name + '/incy.json'
        cases = [('GET', path, 200), ('HEAD', path, 200),
                 ('POST', path, 404), ('GET', path + '?x=1', 404),
                 ('GET', path + '/', 404), ('GET', path.rsplit('/', 1)[0] + '/', 404),
                 ('GET', path.replace('/s/', '/%73/', 1), 404),
                 ('GET', '/extra/../' + path.lstrip('/'), 404),
                 ('GET', path.replace('/s/', '//s/', 1), 404),
                 ('GET', '/s/' + uuid.uuid4().hex * 2 + '/incy.json', 404)]
        for method, target, status in cases:
            connection = http.client.HTTPSConnection(HOST, timeout=15)
            try:
                connection.request(method, target)
                response = connection.getresponse()
                body = response.read()
                require(response.status == status)
                require(response.getheader('Cache-Control') == 'no-store')
                if status == 200 and method == 'GET':
                    require(body == source.read_bytes())
                if method == 'HEAD':
                    require(not body)
            finally:
                connection.close()
        connection = http.client.HTTPConnection(HOST, timeout=10)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            response.read()
            require(response.status == 404 and response.getheader('Location') is None)
            require(response.getheader('Cache-Control') == 'no-store')
        finally:
            connection.close()
        write_json(directory / ('subscription-' + str(index) + '.receipt.json'), {'passed': True})


def accept(args):
    require(re.fullmatch(r'[a-z][a-z0-9-]{0,47}', args.device) is not None)
    require(hashlib.sha256(args.engine.read_bytes()).hexdigest() == ENGINE_SHA)
    require(ipaddress.ip_address(args.expected_egress).is_global)
    # This helper is deliberately local to the new Moscow host.
    addresses = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'scope', 'global'],
                               capture_output=True, text=True, check=True).stdout
    require(any(word.split('/')[0] == '132.243.191.232' for word in addresses.split()))
    args.evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
    args.evidence.chmod(0o700)
    receipts = {}

    def gate(name, action):
        try:
            action()
        except Exception:
            receipts[name] = 'FAIL'
            write_json(args.evidence / 'receipt.json', receipts)
            raise
        receipts[name] = 'PASS'
        write_json(args.evidence / 'receipt.json', receipts)

    clients = args.bundle / 'client-tests' / args.device
    primary = json.loads((clients / 'moscow.json').read_text())
    fallback = json.loads((clients / 'frankfurt.json').read_text())
    server = json.loads((args.bundle / 'server.json').read_text())
    engine = str(args.engine)

    def probe(config, label, success):
        require(config['inbounds'] == [{'type': 'mixed', 'tag': 'test',
                                      'listen': '127.0.0.1', 'listen_port': 11808}])
        with running(engine, config, args.evidence, label, 11808):
            egress(args.expected_egress, success)

    gate('moscow-egress', lambda: probe(primary, 'moscow', True))
    gate('direct-reserve-egress', lambda: probe(fallback, 'reserve', True))
    invalid = copy.deepcopy(primary)
    invalid['outbounds'][0]['uuid'] = str(uuid.uuid4())
    gate('bad-uuid-rejected', lambda: probe(invalid, 'bad-uuid', False))

    def failclosed():
        testclient = copy.deepcopy(primary)
        testclient['outbounds'][0].update(server='127.0.0.1', server_port=12443)
        # Positive control proves this exact isolated REALITY server/client works first.
        with running(engine, test_server(server, 12443), args.evidence, 'testserver-control', 12443):
            probe(testclient, 'testclient-control', True)
        # Bind without listening: an exclusively owned, guaranteed unreachable port.
        with socket.socket() as blocked:
            blocked.bind(('127.0.0.1', 0))
            closed = test_server(server, 12443, blocked.getsockname()[1])
            with running(engine, closed, args.evidence, 'testserver-blocked', 12443):
                probe(testclient, 'testclient-blocked', False)
    gate('isolated-failclosed', failclosed)
    gate('https-subscriptions', lambda: subscriptions(args.bundle, args.evidence))

    def readback():
        state = {}
        for unit in ('caddy.service', 'moscow1-vless.service', 'nginx.service', 'certbot.timer'):
            state[unit] = {}
            for kind in ('is-active', 'is-enabled'):
                result = subprocess.run(['systemctl', kind, unit], capture_output=True, text=True, timeout=10)
                state[unit][kind] = result.stdout.strip()
            wanted = ('active', 'enabled') if unit in ('caddy.service', 'moscow1-vless.service') else ('inactive', 'disabled')
            require(tuple(state[unit].values()) == wanted)
        write_json(args.evidence / 'service-readback.json', state)
    gate('final-service-readback', readback)

    def journal():
        result = subprocess.run(['journalctl', '-u', 'caddy.service', '-u', 'moscow1-vless.service',
                                 '--since', args.journal_since, '--no-pager', '-o', 'cat'],
                                capture_output=True, timeout=30)
        require(result.returncode == 0 and bool(result.stdout))
        secrets = [p.parent.name for p in (args.bundle / 'subscriptions/s').glob('*/incy.json')]
        secrets += [u['uuid'] for u in server['inbounds'][0]['users']]
        secrets += [server['outbounds'][0]['uuid']]
        require(not any(secret.encode() in result.stdout + result.stderr for secret in secrets))
        # Do not persist raw journals: receipt records only the secret-scan result.
    gate('journal-no-secrets', journal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('device')
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--engine', type=Path, default=Path('/usr/local/lib/moscow1/sing-box'))
    parser.add_argument('--expected-egress', required=True)
    parser.add_argument('--journal-since', default='1 hour ago')
    args = parser.parse_args()
    os.umask(0o077)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(130))
    try:
        accept(args)
    except (Exception, KeyboardInterrupt):
        print('Native acceptance failed; inspect private receipts. No service restart performed.', file=sys.stderr)
        return 1
    print('Native scripted gates passed. Incy, London routes and throughput remain separate gates.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
