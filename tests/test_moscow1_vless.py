#!/usr/bin/env python3
"""Offline generator contracts; all credentials are synthetic test data."""
import base64
import configparser
import copy
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'hosts/moscow1/ubuntu/vless/build.py'
DEPLOY = BUILD.with_name('deploy.sh')
ENGINE_SHA = 'a056076cff3aa1ced5ed794743b9f87b2dee7dc068280d2665c1e0b45533e793'


def key():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')


def fixture():
    outbound = {
        'type': 'vless', 'tag': 'existing', 'server': '31.58.85.163',
        'server_port': 24443, 'uuid': str(uuid.uuid4()), 'flow': 'xtls-rprx-vision',
        'packet_encoding': 'xudp',
        'tls': {'enabled': True, 'server_name': 'www.google.com', 'alpn': ['h2', 'http/1.1'],
                'utls': {'enabled': True, 'fingerprint': 'firefox'},
                'reality': {'enabled': True, 'public_key': key(), 'short_id': '1234abcd'}},
    }
    fallback = copy.deepcopy(outbound)
    fallback['uuid'] = str(uuid.uuid4())
    return {
        'hostname': 'moscow1.nikcode.xyz', 'ip': '132.243.191.232',
        'reality_private_key': key(), 'reality_public_key': key(), 'short_id': 'abcd1234',
        'frankfurt_outbound': outbound,
        'devices': [{'name': 'pilot', 'uuid': str(uuid.uuid4()),
                     'subscription_token': secrets.token_urlsafe(32),
                     'direct_frankfurt_outbound': fallback}],
    }


class DeployTests(unittest.TestCase):
    def test_health_window_is_finite_and_accepts_late_tls_without_bypass(self):
        source = DEPLOY.read_text()
        health = source.split('healthy=0\n', 1)[1].split('# Success gate:', 1)[0]
        self.assertIn('for ((attempt=0; attempt<180; attempt++)); do', health)
        for ready_at in (0, 61, 180):
            with self.subTest(ready_at=ready_at), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = '''
set -Eeuo pipefail
backup=$TEST_ROOT
healthy=0
curl() {
  printf '%s\\n' "$@" >"$TEST_ROOT/curl.args"
  echo attempt >>"$TEST_ROOT/attempts"
  if [[ $READY_AT != 0 && $attempt -ge $((READY_AT - 1)) ]]; then
    printf ok
  else
    return 35
  fi
}
sleep() { [[ $# == 1 && $1 == 2 ]] || return 99; echo pause >>"$TEST_ROOT/pauses"; }
all_services_active() { [[ $* == 'caddy.service moscow1-vless.service' ]]; }
''' + health + '\necho accepted\n'
                result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                        timeout=10, env={**os.environ, 'TEST_ROOT': directory,
                                                        'READY_AT': str(ready_at)})
                attempts = ready_at or 180
                self.assertEqual(result.returncode, 0 if ready_at else 1)
                self.assertEqual(result.stdout, 'accepted\n' if ready_at else '')
                self.assertEqual(result.stderr, '')
                self.assertEqual(len((root / 'attempts').read_text().splitlines()), attempts)
                self.assertEqual(len((root / 'pauses').read_text().splitlines()),
                                 attempts - 1 if ready_at else attempts)
                # Exact argv rejects -k/--insecure, token URLs and timeout changes.
                self.assertEqual((root / 'curl.args').read_text().splitlines(), [
                    '--silent', '--show-error', '--fail', '--noproxy', '*',
                    '--connect-timeout', '2', '--max-time', '5', '--resolve',
                    'moscow1.nikcode.xyz:443:127.0.0.1',
                    'https://moscow1.nikcode.xyz/healthz',
                ])

    def shell_function(self, name):
        match = re.search(r'^' + name + r'\(\) \{\n.*?^\}[^\n]*', DEPLOY.read_text(), re.M | re.S)
        self.assertIsNotNone(match, 'Missing deploy function: ' + name)
        return match.group()

    def test_health_requires_every_service_with_mixed_state_controls(self):
        function = self.shell_function('all_services_active')
        for active in ('both', 'caddy.service', 'moscow1-vless.service', 'neither'):
            with self.subTest(active=active):
                script = function + '''
systemctl() {
  [[ $# == 3 && $1 == is-active && $2 == --quiet ]] || return 99
  [[ $ACTIVE == both || $ACTIVE == "$3" ]]
}
all_services_active caddy.service moscow1-vless.service
'''
                result = subprocess.run(['bash', '-c', script], capture_output=True,
                                        env={**os.environ, 'ACTIVE': active})
                self.assertEqual(result.returncode, 0 if active == 'both' else 1)
        self.assertIn('&& all_services_active caddy.service moscow1-vless.service', DEPLOY.read_text())

    def test_interruption_before_caddy_rename_removes_only_owned_temp_and_restores(self):
        function = self.shell_function('rollback_on_failure')
        for signal, code in [('INT', 130), ('TERM', 143)]:
            with self.subTest(signal=signal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                owned = root / '.moscow1.candidate'
                unrelated = root / '.other'
                owned.write_text('synthetic-token')
                unrelated.write_text('preserved')
                script = function + '''
restore() { touch "$RESTORED"; }
backup=$TEST_ROOT
next_config=$OWNED
trap 'rollback_on_failure 130' INT
trap 'rollback_on_failure 143' TERM
kill -s "$SIGNAL" "$$"
exit 99
'''
                result = subprocess.run(['bash', '-c', script], capture_output=True,
                                        env={**os.environ, 'OWNED': str(owned), 'SIGNAL': signal,
                                             'RESTORED': str(root / 'restored'), 'TEST_ROOT': directory})
                self.assertEqual(result.returncode, code)
                self.assertFalse(owned.exists())
                self.assertTrue((root / 'restored').exists())
                self.assertEqual(unrelated.read_text(), 'preserved')
                self.assertNotIn(b'synthetic-token', result.stdout + result.stderr)

    def test_subscription_filesystem_errors_are_private_and_preserve_failure(self):
        source = DEPLOY.read_text()
        operations = source.split('cp -a "$bundle/subscriptions"', 1)[1].split('# The candidate', 1)[0]
        operations = ('cp -a "$bundle/subscriptions"' + operations).replace(
            '/var/lib/moscow1/subscriptions', '"$TEST_ROOT/live/subscriptions"')
        for failure in ('none', 'cp', 'chown', 'directories', 'files'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                token = 'synthetic-token-for-filesystem-errors'
                subscription = root / 'bundle/subscriptions/s' / token
                subscription.mkdir(parents=True)
                (subscription / 'incy.json').write_text('synthetic')
                (root / 'live').mkdir()
                (root / 'unrelated').write_text('preserved')
                script = self.shell_function('rollback_on_failure') + '''
set -Eeuo pipefail
umask 077
backup=$TEST_ROOT
bundle=$TEST_ROOT/bundle
next_config=''
restore() { echo "$TOKEN rollback diagnostic" >&2; return 1; }
inject() { echo "$TOKEN injected $1 failure"; echo "$TOKEN diagnostic" >&2; return 37; }
cp() { if [[ $FAILURE == cp ]]; then inject cp; else command cp "$@"; fi; }
chown() { if [[ $FAILURE == chown ]]; then inject chown; fi; }
find() {
  if [[ $FAILURE == directories && $* == *'-type d'* || $FAILURE == files && $* == *'-type f'* ]]; then
    inject find
  else command find "$@"; fi
}
trap 'rollback_on_failure $?' ERR
''' + operations
                result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                        env={**os.environ, 'TEST_ROOT': directory,
                                             'TOKEN': token, 'FAILURE': failure})
                self.assertEqual(result.returncode, 0 if failure == 'none' else 37)
                self.assertNotIn(token, result.stdout + result.stderr)
                self.assertEqual(result.stdout, '')
                if failure != 'none':
                    # An inherited ERR trap may still be under the command's private redirection.
                    self.assertIn(result.stderr, ('',
                                  'Install interrupted/failed; restoring task files and prior service states.\n'
                                  'Rollback incomplete; inspect the private backup.\n'))
                    self.assertIn(token, (root / 'filesystem.log').read_text())
                    self.assertIn(token, (root / 'rollback.log').read_text())
                    for log in ('filesystem.log', 'rollback.log'):
                        self.assertEqual((root / log).stat().st_mode & 0o077, 0)
                else:
                    self.assertEqual(result.stderr, '')
                    self.assertEqual((root / 'live/subscriptions/s' / token / 'incy.json').read_text(),
                                     'synthetic')
                self.assertEqual((root / 'unrelated').read_text(), 'preserved')

    def test_subscription_preflight_find_failure_is_private_and_not_accepted(self):
        source = DEPLOY.read_text()
        start = source.index('[[ -d $bundle/subscriptions')
        preflight = source[start:source.index('if getent passwd moscow1', start)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'subscriptions').mkdir()
            script = '''
set -Eeuo pipefail
umask 077
backup=$TEST_ROOT
bundle=$TEST_ROOT
fail() { echo "$1" >&2; exit 1; }
find() { echo 'synthetic-token preflight diagnostic' >&2; return 37; }
''' + preflight
            result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                    env={**os.environ, 'TEST_ROOT': directory})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('synthetic-token', result.stdout + result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, 'Unable to inspect subscriptions; inspect private diagnostics.\n')
            self.assertIn('synthetic-token', (root / 'filesystem.log').read_text())

    def test_restore_filesystem_errors_and_other_diagnostics_are_private(self):
        for failure in ('none', 'rm', 'cp', 'systemctl'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / '.moscow1-backup').write_text('132.243.191.232\n')
                owned = root / 'owned'
                owned.mkdir()
                (root / ('before' + str(owned))).mkdir(parents=True)
                (root / 'unrelated').write_text('preserved')
                script = self.shell_function('restore') + '''
umask 077
backup=$TEST_ROOT
expected_ip=132.243.191.232
paths=("$TEST_ROOT/owned")
services=()
inject() { echo 'synthetic-token rollback diagnostic' >&2; return 37; }
rm() { if [[ $FAILURE == rm ]]; then inject; else command rm "$@"; fi; }
cp() { if [[ $FAILURE == cp ]]; then inject; else command cp "$@"; fi; }
systemctl() {
  if [[ $FAILURE == systemctl ]]; then inject; return; fi
  if [[ $1 == show ]]; then echo not-found; fi
}
restore
'''
                result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                        env={**os.environ, 'TEST_ROOT': directory, 'FAILURE': failure})
                self.assertEqual(result.returncode, 0 if failure == 'none' else 1)
                self.assertEqual(result.stdout + result.stderr, '')
                if failure != 'none':
                    self.assertIn('synthetic-token', (root / 'rollback.log').read_text())
                self.assertEqual((root / 'unrelated').read_text(), 'preserved')

    def test_failed_temporary_cleanup_keeps_diagnostics_private_and_original_status(self):
        with tempfile.TemporaryDirectory() as directory:
            script = self.shell_function('rollback_on_failure') + '''
umask 077
backup=$TEST_ROOT
next_config=$TEST_ROOT/owned
rm() { echo 'synthetic-token cleanup diagnostic' >&2; return 37; }
restore() { echo 'synthetic-token restore diagnostic' >&2; return 1; }
rollback_on_failure 42
'''
            result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                    env={**os.environ, 'TEST_ROOT': directory})
            self.assertEqual(result.returncode, 42)
            self.assertNotIn('synthetic-token', result.stdout + result.stderr)
            self.assertIn('synthetic-token', (Path(directory) / 'rollback.log').read_text())


class AcceptanceHelperTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('moscow_accept', BUILD.with_name('accept.py'))
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def test_failclosed_variant_preserves_policy_and_credentials_without_mutating_source(self):
        spec = importlib.util.spec_from_file_location('moscow_build', BUILD)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        original = builder.server_config(fixture())
        before = copy.deepcopy(original)
        control = self.helper.test_server(original, 12443)
        blocked = self.helper.test_server(original, 12443, 19999)
        self.assertEqual(original, before)
        self.assertEqual(blocked['route'], original['route'])
        self.assertEqual(blocked['inbounds'][0]['users'], original['inbounds'][0]['users'])
        self.assertEqual(blocked['inbounds'][0]['tls'], original['inbounds'][0]['tls'])
        self.assertEqual(blocked['inbounds'][0]['listen'], '127.0.0.1')
        self.assertEqual([o['type'] for o in blocked['outbounds']], ['vless'])
        expected = copy.deepcopy(control)
        expected['outbounds'][0].update(server='127.0.0.1', server_port=19999)
        self.assertEqual(blocked, expected)

    def test_owned_child_is_killed_and_reaped_after_failure_and_terminate_timeout(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(self.helper.socket, 'socket'), \
                mock.patch.object(self.helper.socket, 'create_connection'), \
                mock.patch.object(self.helper.time, 'sleep'), \
                mock.patch.object(self.helper.subprocess, 'run') as check, \
                mock.patch.object(self.helper.subprocess, 'Popen') as popen:
            check.return_value.returncode = 0
            process = popen.return_value
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired('owned-child', 5), 0]
            with self.assertRaisesRegex(ValueError, 'injected failure'):
                with self.helper.running('/synthetic/engine', {}, Path(directory), 'owned', 11808):
                    raise ValueError('injected failure')
            process.terminate.assert_called_once_with()
            process.kill.assert_called_once_with()
            self.assertEqual(process.wait.call_count, 2)

    def test_negative_egress_rejects_any_success_and_any_unexpected_body(self):
        with mock.patch.object(self.helper.subprocess, 'run') as run:
            for code, body, valid in [(7, b'', True), (0, b'31.58.85.163', False),
                                      (0, b'132.243.191.232', False), (22, b'error', False)]:
                run.return_value.returncode = code
                run.return_value.stdout = body
                with self.subTest(code=code, body=body):
                    if valid:
                        self.helper.egress('31.58.85.163', False)
                    else:
                        with self.assertRaises(ValueError):
                            self.helper.egress('31.58.85.163', False)


class HardeningTests(unittest.TestCase):
    def test_rollback_touches_only_owned_paths_and_keeps_timer_when_recovery_fails(self):
        source = BUILD.with_name('harden.sh').read_text()
        function = re.search(r'^restore\(\) \{\n.*?^\}', source, re.M | re.S).group()
        for fail_reload in ('0', '1'):
            with self.subTest(fail_reload=fail_reload), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'ready').write_text('132.243.191.232\n')
                owned = [root / 'ssh-dropin', root / 'firewall-unit']
                for path in owned:
                    path.write_text('owned')
                (root / 'firewall-dir').mkdir()
                (root / 'unrelated').write_text('preserved')
                script = function + '''
backup=$TEST_ROOT
address=132.243.191.232
ssh_dropin=$backup/ssh-dropin
firewall_unit=$backup/firewall-unit
firewall_dir=$backup/firewall-dir
timer=owned-rollback
systemctl() {
  printf '%s\\n' "$*" >>"$backup/calls"
  case "$*" in
    'show -p LoadState --value moscow1-firewall.service') echo loaded ;;
    'disable --now moscow1-firewall.service'|'daemon-reload'|'stop owned-rollback.timer') return 0 ;;
    'reload ssh.service') return "$FAIL_RELOAD" ;;
    *) return 99 ;;
  esac
}
nft() {
  printf '%s\\n' "$*" >>"$backup/calls"
  [[ "$*" == 'list table inet moscow1_guard' || "$*" == 'delete table inet moscow1_guard' ]]
}
function /usr/sbin/sshd { [[ "$*" == '-t' ]]; }
restore
'''
                result = subprocess.run(['bash', '-c', script], capture_output=True,
                                        env={**os.environ, 'TEST_ROOT': directory, 'FAIL_RELOAD': fail_reload})
                self.assertEqual(result.returncode, int(fail_reload), result.stderr)
                self.assertFalse(any(p.exists() for p in owned))
                self.assertFalse((root / 'firewall-dir').exists())
                self.assertEqual((root / 'unrelated').read_text(), 'preserved')
                calls = (root / 'calls').read_text()
                self.assertIn('delete table inet moscow1_guard\n', calls)
                self.assertNotIn('flush', calls)
                self.assertEqual('stop owned-rollback.timer\n' in calls, fail_reload == '0')


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='moscow1-offline-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = fixture()

    def generate(self, data=None, destination='bundle'):
        source = self.root / 'input.json'
        source.write_text(json.dumps(self.data if data is None else data))
        source.chmod(0o600)
        result = subprocess.run([sys.executable, str(BUILD), str(source),
                                 str(self.root / destination)], capture_output=True, text=True)
        return result, self.root / destination

    def test_optional_alpn_preserves_native_and_xray_order(self):
        cases = ((None, None), (['h2'], None), (None, ['h2']),
                 (['h2'], ['http/1.1']), (['http/1.1'], ['h2']),
                 (['h2', 'http/1.1'], ['http/1.1', 'h2']),
                 (['http/1.1', 'h2'], ['h2', 'http/1.1']))
        for index, (transit_alpn, fallback_alpn) in enumerate(cases):
            with self.subTest(transit=transit_alpn, fallback=fallback_alpn):
                data = copy.deepcopy(self.data)
                transit = data['frankfurt_outbound']
                fallback = data['devices'][0]['direct_frankfurt_outbound']
                for outbound, alpn in ((transit, transit_alpn), (fallback, fallback_alpn)):
                    if alpn is None:
                        outbound['tls'].pop('alpn', None)
                    else:
                        outbound['tls']['alpn'] = alpn[:]
                result, bundle = self.generate(data, 'alpn-' + str(index))
                self.assertEqual(result.returncode, 0, result.stderr)
                server = json.loads((bundle / 'server.json').read_text())
                client = json.loads((bundle / 'client-tests/pilot/frankfurt.json').read_text())
                profiles = json.loads((bundle / 'subscriptions/s' / data['devices'][0]['subscription_token'] /
                                       'incy.json').read_text())
                targets = [(server['outbounds'][0]['tls'], transit_alpn),
                           (client['outbounds'][0]['tls'], fallback_alpn),
                           (profiles[1]['outbounds'][0]['streamSettings']['realitySettings'], fallback_alpn)]
                for target, alpn in targets:
                    if alpn is None:
                        self.assertNotIn('alpn', target)
                    else:
                        self.assertEqual(target['alpn'], alpn)

    def test_invalid_alpn_on_either_input_is_rejected_without_output(self):
        invalid = (None, 'h2', {}, [], ['h2', 'h2'], ['h3'], ['H2'], [''], [1], [True], [[]], [{}], ['h2', None])
        for location in ('transit', 'fallback'):
            for index, alpn in enumerate(invalid):
                with self.subTest(location=location, alpn=alpn):
                    data = copy.deepcopy(self.data)
                    outbound = (data['frankfurt_outbound'] if location == 'transit' else
                                data['devices'][0]['direct_frankfurt_outbound'])
                    outbound['tls']['alpn'] = alpn
                    result, directory = self.generate(data, location + '-alpn-bad-' + str(index))
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse(directory.exists())
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(result.stderr, 'Bundle rejected: invalid schema or unavailable new output directory.\n')

    def test_server_has_one_fail_closed_exit_and_no_client_override(self):
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((bundle / 'server.json').read_text())
        self.assertEqual([o['type'] for o in server['outbounds']], ['vless'])
        self.assertEqual(server['route']['final'], 'frankfurt')
        self.assertEqual(server['route']['rules'][0], {'action': 'sniff'})
        self.assertIn({'ip_is_private': True, 'action': 'reject'}, server['route']['rules'])
        self.assertEqual(server['log'], {'disabled': True})
        self.assertEqual(server['inbounds'][0]['listen_port'], 24443)
        self.assertEqual([i['type'] for i in server['inbounds']], ['vless'])
        self.assertNotIn('experimental', server)
        unit = configparser.ConfigParser(interpolation=None)
        unit.read_string((bundle / 'moscow1-vless.service').read_text())
        service = unit['Service']
        self.assertEqual(set(service['RestrictAddressFamilies'].split()),
                         {'AF_INET', 'AF_INET6', 'AF_UNIX', 'AF_NETLINK'})
        self.assertEqual(service['User'], 'moscow1')
        self.assertEqual(service['Group'], 'moscow1')
        self.assertEqual(service['CapabilityBoundingSet'], '')
        self.assertEqual(service.get('AmbientCapabilities', ''), '')
        self.assertEqual(service['NoNewPrivileges'], 'true')
        self.assertEqual(service['PrivateDevices'], 'true')
        self.assertEqual(service.get('DeviceAllow', ''), '')
        self.assertEqual(service['StandardOutput'], 'null')
        self.assertEqual(service['StandardError'], 'null')

    def test_subscription_contains_full_routing_and_the_supplied_device_backup(self):
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        device = self.data['devices'][0]
        profiles = json.loads((bundle / 'subscriptions/s' / device['subscription_token'] / 'incy.json').read_text())
        self.assertEqual([p['remarks'] for p in profiles], ['Moscow', 'Frankfurt direct backup'])
        for profile in profiles:
            self.assertEqual([(i['listen'], i['port'], i['protocol']) for i in profile['inbounds']],
                             [('127.0.0.1', 10808, 'socks'), ('127.0.0.1', 10809, 'http')])
            self.assertEqual(profile['dns']['queryStrategy'], 'UseIPv4')
            self.assertEqual(profile['dns']['hosts']['moscow1.nikcode.xyz'], '132.243.191.232')
            rules = profile['routing']['rules']
            self.assertEqual(rules[0], {'type': 'field', 'network': 'udp', 'port': '443', 'outboundTag': 'block'})
            self.assertIn({'type': 'field', 'inboundTag': ['dns-internal'], 'outboundTag': 'proxy'}, rules)
            self.assertTrue(any('geoip:private' in r.get('ip', []) and r['outboundTag'] == 'direct' for r in rules))
            self.assertTrue(any('geoip:ru' in r.get('ip', []) and r['outboundTag'] == 'direct' for r in rules))
            self.assertTrue(any('geosite:category-ru' in r.get('domain', []) for r in rules))
            # Domain requests must reach the DNS/IP pass before using the default proxy.
            self.assertEqual(profile['routing']['domainStrategy'], 'IPIfNonMatch')
            self.assertEqual(profile['outbounds'][0]['tag'], 'proxy')
            self.assertFalse(any(set(r) <= {'type', 'network', 'outboundTag'} for r in rules),
                             'An unconditional network rule suppresses the DNS/IP pass')
            self.assertEqual(profile['dns']['servers'], ['https://1.1.1.1/dns-query'])
            reality = profile['outbounds'][0]['streamSettings']['realitySettings']
            self.assertEqual(reality['fingerprint'], 'firefox')
            user = profile['outbounds'][0]['settings']['vnext'][0]['users'][0]
            self.assertEqual(user['flow'], 'xtls-rprx-vision')
            self.assertEqual(user['encryption'], 'none')
        primary = profiles[0]['outbounds'][0]
        backup = profiles[1]['outbounds'][0]
        self.assertEqual(primary['settings']['vnext'][0]['address'], 'moscow1.nikcode.xyz')
        self.assertEqual(primary['settings']['vnext'][0]['users'][0]['id'], device['uuid'])
        self.assertEqual(backup['settings']['vnext'][0]['users'][0]['id'], device['direct_frankfurt_outbound']['uuid'])
        self.assertNotEqual(backup['settings']['vnext'][0]['users'][0]['id'], self.data['frankfurt_outbound']['uuid'])
        self.assertEqual(backup['streamSettings']['realitySettings']['publicKey'],
                         device['direct_frankfurt_outbound']['tls']['reality']['public_key'])

    def test_caddy_exposes_only_exact_raw_paths_and_keeps_tls_logging(self):
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        site = (bundle / 'Caddyfile').read_text()
        token = self.data['devices'][0]['subscription_token']
        self.assertIn('auto_https disable_redirects', site)
        self.assertIn('admin localhost:2019', site)
        self.assertIn('storage file_system /var/lib/caddy/moscow1', site)
        self.assertIn('exclude http.log.access http.log.error admin.api', site)
        self.assertNotIn('output discard', site)  # TLS operational messages remain.
        self.assertNotIn('debug', site)
        self.assertIn('{http.request.orig_uri} == "/s/' + token + '/incy.json"', site)
        self.assertIn('{http.request.method} in ["GET", "HEAD"]', site)
        self.assertIn('rewrite * /s/' + token + '/incy.json', site)
        self.assertIn('Cache-Control "no-store"', site)
        self.assertIn('handle_errors', site)
        self.assertIn('respond "" 404', site)
        self.assertNotIn('browse', site)
        self.assertNotIn('reverse_proxy', site)
        self.assertNotIn('/etc/letsencrypt', site)
        http = site.split(':80 {', 1)[1]
        self.assertNotIn(token, http)
        self.assertNotIn('redir', http)
        self.assertIn('respond "" 404', http)
        self.assertIn('/healthz', site)
        self.assertFalse((bundle / 'nginx.conf').exists())
        self.assertFalse((bundle / 'renew-nginx.sh').exists())

    def test_caddy_parser_if_already_available(self):
        engine = shutil.which('caddy')
        if not engine:
            self.skipTest('Caddy is not installed; parent must adapt/validate with Ubuntu package')
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        # Run the same adapter as deploy; all token-bearing output stays private.
        destination = self.root / 'native-caddy.json'
        adapted = subprocess.run([sys.executable, str(BUILD.with_name('adapt-caddy.py')),
                                  str(bundle / 'Caddyfile'), str(destination), '--caddy', engine],
                                 capture_output=True, text=True)
        self.assertEqual(adapted.returncode, 0, 'Caddy adaptation failed; inspect private test state')
        self.assertEqual(adapted.stdout + adapted.stderr, '')
        self.assertEqual(destination.stat().st_mode & 0o077, 0)
        config = json.loads(destination.read_text())
        self.assertEqual(config['admin']['listen'], 'localhost:2019')
        self.assertFalse(config['admin']['config']['persist'])
        self.assertEqual(config['storage']['root'], '/var/lib/caddy/moscow1')
        default_log = config['logging']['logs']['default']
        self.assertTrue({'http.log.access', 'http.log.error', 'admin.api'} <= set(default_log['exclude']))
        # Do not validate here: provisioning paths target the real Moscow filesystem.
        # Parent runs validate under the private deployment backup before cutover.

    def test_exact_pinned_engine_checks_all_generated_sing_box_configs(self):
        engine = os.environ.get('MOSCOW1_SING_BOX')
        if not engine:
            self.skipTest('Set MOSCOW1_SING_BOX to the offline pinned 1.13.5 binary')
        self.assertEqual(hashlib.sha256(Path(engine).read_bytes()).hexdigest(), ENGINE_SHA)
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        configs = [bundle / 'server.json', *sorted((bundle / 'client-tests').rglob('*.json'))]
        self.assertEqual(len(configs), 3)
        for path in configs:
            check = subprocess.run([engine, 'check', '-c', str(path)], capture_output=True, text=True,
                                   env={k: v for k, v in os.environ.items() if not k.startswith('ENABLE_DEPRECATED_')})
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_rejects_unsafe_schema_and_leaves_no_output(self):
        mutations = [
            lambda d: d.update(hostname='evil.example; include /tmp/x'),
            lambda d: d.update(ip='127.0.0.1'),
            lambda d: d.update(extra='not allowed'),
            lambda d: d.update(reality_private_key='PLACEHOLDER'),
            lambda d: d.update(short_id='a'),
            lambda d: d['devices'][0].update(name='../escape'),
            lambda d: d['devices'][0].update(uuid='not-a-uuid'),
            lambda d: d['devices'][0].update(subscription_token='a' * 42),
            lambda d: d['devices'][0].update(subscription_token='../' + 'a' * 43),
            lambda d: d['frankfurt_outbound'].update(detour='direct'),
            lambda d: d['frankfurt_outbound'].update(server='169.254.169.254'),
            lambda d: d['frankfurt_outbound'].update(server_port=True),
            lambda d: d['frankfurt_outbound'].update(server_port=443),
            lambda d: d['frankfurt_outbound']['tls'].update(insecure=True),
            lambda d: d['frankfurt_outbound']['tls'].update(enabled=1),
            lambda d: d['frankfurt_outbound']['tls'].update(extra={}),
            lambda d: d['frankfurt_outbound']['tls']['utls'].update(fingerprint='evil;'),
            lambda d: d['devices'][0]['direct_frankfurt_outbound'].update(uuid=d['devices'][0]['uuid']),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                data = copy.deepcopy(self.data)
                mutate(data)
                result, directory = self.generate(data, 'bad-' + str(index))
                self.assertEqual(result.returncode, 1)
                self.assertFalse(directory.exists())
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, 'Bundle rejected: invalid schema or unavailable new output directory.\n')

    def test_duplicate_device_fields_and_fallback_ownership_are_rejected(self):
        for field in ('name', 'uuid', 'subscription_token', 'direct_frankfurt_outbound'):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                other = fixture()['devices'][0]
                other['name'] = 'second'
                other[field] = copy.deepcopy(data['devices'][0][field])
                data['devices'].append(other)
                result, directory = self.generate(data, 'duplicate-' + field)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(directory.exists())

    def test_two_synthetic_devices_are_separate_and_preserve_fallback_fingerprint(self):
        other = fixture()['devices'][0]
        other['name'] = 'second'
        other['direct_frankfurt_outbound']['tls']['utls']['fingerprint'] = 'chrome'
        self.data['devices'].append(other)
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        for device in self.data['devices']:
            path = bundle / 'subscriptions/s' / device['subscription_token'] / 'incy.json'
            profiles = json.loads(path.read_text())
            backup = profiles[1]['outbounds'][0]
            self.assertEqual(backup['streamSettings']['realitySettings']['fingerprint'],
                             device['direct_frankfurt_outbound']['tls']['utls']['fingerprint'])
            self.assertEqual(backup['settings']['vnext'][0]['users'][0]['id'],
                             device['direct_frankfurt_outbound']['uuid'])
            other_device = next(d for d in self.data['devices'] if d is not device)
            self.assertNotIn(other_device['uuid'], path.read_text())
            self.assertNotIn(other_device['subscription_token'], path.read_text())
            for filename in ('moscow.json', 'frankfurt.json'):
                client = json.loads((bundle / 'client-tests' / device['name'] / filename).read_text())
                self.assertEqual([o['type'] for o in client['outbounds']], ['vless'])
                self.assertEqual(client['route']['final'], 'proxy')
                self.assertEqual(client['inbounds'][0]['listen'], '127.0.0.1')
                self.assertNotIn('tun', json.dumps(client))
        # No credentials in routine generator receipts.
        for value in (self.data['reality_private_key'], self.data['frankfurt_outbound']['uuid'],
                      self.data['devices'][0]['uuid'], self.data['devices'][0]['subscription_token']):
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_new_output_is_private_and_never_overwrites_existing_or_symlink(self):
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        before = {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
        for path in [bundle, *bundle.rglob('*')]:
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        result, _ = self.generate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(before, {p.relative_to(bundle): p.read_bytes() for p in bundle.rglob('*') if p.is_file()})
        (self.root / 'link').symlink_to(bundle, target_is_directory=True)
        result, _ = self.generate(destination='link')
        self.assertEqual(result.returncode, 1)

    def test_duplicate_json_keys_are_rejected_without_echoing_values(self):
        source = self.root / 'duplicate.json'
        source.write_text('{"hostname":"fake-secret","hostname":"moscow1.nikcode.xyz"}')
        result = subprocess.run([sys.executable, str(BUILD), str(source), str(self.root / 'out')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('fake-secret', result.stdout + result.stderr)
        self.assertFalse((self.root / 'out').exists())

    def test_xray_parser_if_already_available(self):
        engine = shutil.which('xray')
        if not engine:
            self.skipTest('Xray is not installed; no installation attempted')
        result, bundle = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        path = next((bundle / 'subscriptions').rglob('incy.json'))
        for index, profile in enumerate(json.loads(path.read_text())):
            config = self.root / ('xray-' + str(index) + '.json')
            config.write_text(json.dumps(profile))
            check = subprocess.run([engine, 'run', '-test', '-config', str(config)],
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
