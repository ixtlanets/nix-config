"""Offline only: fixed NON-KEY fixtures, tmpdir files, strict fake command runner."""
import base64
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

BUNDLE = Path(__file__).resolve().parent
sys.path.insert(0, str(BUNDLE))
import control
import issuer


def stub(number):
    # Deliberately predictable test bytes, NOT cryptographic key generation.
    return base64.b64encode(bytes([number]) * 32).decode()


def settings():
    return {'site': {'external_ipv4': '91.108.225.14', 'external_prefix': 32,
                     'external_interface': 'ens3', 'external_gateway': '10.0.0.1'},
            'profile': {**{key: str(i + 1) for i, key in enumerate(control.PROFILE_KEYS[:-2])},
                        'ContentPaddingAddition': '4-28', 'RandomTrailers': 'on'},
            'client_dns': ['1.1.1.1', '9.9.9.9']}


class FakeKeys:
    def __init__(self):
        self.calls = []

    def run(self, action, value=None):
        self.calls.append((action, value))
        return stub(len(self.calls))


class FakeRunner:
    def __init__(self):
        self.calls, self.rules = [], {}
        self.links = [{'ifname': 'ens3', 'ifindex': 2, 'flags': ['UP']}]
        self.addresses = [{'ifname': 'ens3', 'addr_info': [{'local': '91.108.225.14', 'prefixlen': 32}]}]
        self.routes = [{'dst': 'default', 'gateway': '10.0.0.1', 'dev': 'ens3'}]
        self.dev, self.gateway, self.return_dev = 'ens3', '10.0.0.1', control.IFACE
        self.busy, self.fail, self.listing = False, None, ''
        self.foreign = ('-i', 'production0', '-j', 'ACCEPT')
        self.rules[('iptables', 'filter', 'FORWARD')] = [self.foreign]

    def run(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if self.fail and self.fail(argv):
            return 2, 'SECRET_SENTINEL_MUST_NOT_ESCAPE'
        if argv[0] in ('iptables', 'ip6tables'):
            assert argv[1:4] == ['-w', '5', '-t']
            if argv[5:] == ['-S']:
                return 0, self.listing
            tool, table, action, chain = argv[0], argv[4], argv[5], argv[6]
            args = tuple(argv[8:] if action == '-I' else argv[7:])
            bucket = self.rules.setdefault((tool, table, chain), [])
            if action == '-C':
                return (0 if args in bucket else 1), ''
            if action == '-I':
                assert argv[7] in ('1', '2', '3')
                bucket.insert(int(argv[7]) - 1, args)
            elif action == '-D':
                bucket.remove(args)
            else:
                raise AssertionError('unexpected firewall operation')
            return 0, ''
        if argv == ['ip', '-j', 'link', 'show']:
            return 0, json.dumps(self.links)
        if argv == ['ip', '-j', '-4', 'address', 'show']:
            return 0, json.dumps(self.addresses)
        if argv == ['ip', '-j', '-4', 'route', 'show', 'table', 'all']:
            return 0, json.dumps(self.routes)
        if argv[:5] == ['ip', '-j', '-4', 'route', 'get']:
            route = {'dev': self.return_dev} if len(argv) == 6 else {'dev': self.dev, 'gateway': self.gateway}
            return 0, json.dumps([route])
        if argv == ['ss', '-H', '-lun', f'sport = :{control.PORT}']:
            return 0, 'bound' if self.busy else ''
        if argv == ['ip', 'link', 'delete', 'dev', control.IFACE]:
            self.links = [item for item in self.links if item['ifname'] != control.IFACE]
            return 0, ''
        allowed = [
            ['ip', 'address', 'add', control.SERVER, 'dev', control.IFACE],
            ['ip', 'link', 'set', 'dev', control.IFACE, 'mtu', '1280'],
            ['ip', 'link', 'set', 'dev', control.IFACE, 'up'],
            ['ip', 'link', 'set', 'dev', control.IFACE, 'down'],
        ]
        if argv in allowed or (len(argv) == 4 and argv[1:3] == ['setconf', control.IFACE]):
            return 0, ''
        raise AssertionError(f'unexpected command {argv!r}')


class OfflineTests(unittest.TestCase):
    def setUp(self):
        # Hard stop if any test accidentally reaches a real subprocess.
        self.addCleanup(patch.stopall)
        patch('subprocess.run', side_effect=AssertionError('real subprocess forbidden')).start()
        self.temp = tempfile.TemporaryDirectory(prefix='awg-uk-offline-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / 'state'
        self.keys = FakeKeys()
        issuer.init(self.state, settings(), self.keys)
        issuer.add(self.state, 'alice', self.keys)
        issuer.add(self.state, 'bob', self.keys)
        self.root, self.runtime = self.base / 'installed', self.base / 'runtime'
        self.root.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        self.forwarding = self.base / 'forwarding'
        self.forwarding.write_text('1\n')
        for dev in ('default', 'ens3', control.IFACE):
            directory = self.base / 'conf' / dev
            directory.mkdir(parents=True)
            (directory / 'forwarding').write_text('1\n')
        self.socket, self.interface = self.base / 'uapi', self.base / 'interface'
        self.runner = FakeRunner()
        self.clock = [0.0]
        self.lifecycle = control.Lifecycle(
            runner=self.runner, root=self.root, runtime=self.runtime, socket=self.socket,
            interface_path=self.interface, forwarding=self.forwarding, invocation='test-invocation',
            platform_check=lambda: None, clock=lambda: self.clock[0],
            sleep=lambda seconds: self.clock.__setitem__(0, self.clock[0] + seconds))
        # Exercise full parsing/security/hash checks against NON-executable fixture files.
        pins = {}
        for name in control.PINS:
            data = b'NOT_AN_EXECUTABLE_' + name.encode()
            control.write_new(self.root / name, data.decode())
            (self.root / name).chmod(0o700)
            pins[name] = hashlib.sha256(data).hexdigest()
        patch.object(control, 'PINS', pins).start()
        save_secure = control.secure
        patch.object(control, 'secure', side_effect=lambda path, mode, directory=False, uid=None:
                     save_secure(path, mode, directory, os.geteuid() if uid is None else uid)).start()
        control.write_new(self.root / 'site.json', json.dumps(settings()['site']))
        issuer.render(self.state, self.root / 'server.conf', [])
        # No sockets are opened, including Unix sockets: readiness is purely fake.
        patch.object(Path, 'is_socket', lambda path: path == self.socket and path.exists()).start()

    def preflight(self):
        self.lifecycle.preflight()

    def ready(self):
        if self.socket.exists():
            self.socket.unlink()
        self.preflight()
        self.interface.mkdir(exist_ok=True)
        (self.interface / 'ifindex').write_text('41\n')
        self.socket.touch()
        self.runner.links.append({'ifname': control.IFACE, 'ifindex': 41, 'flags': []})

    def no_permits(self):
        self.assertFalse(any('MASQUERADE' in rule or ('ACCEPT' in rule and rule != self.runner.foreign)
                             for rules in self.runner.rules.values() for rule in rules))

    def test_multiple_peers_and_native_structure(self):
        self.lifecycle.config_check()
        self.assertEqual(self.lifecycle.peers, ['10.214.91.2/32', '10.214.91.3/32'])
        self.assertEqual(control.NETWORK.prefixlen, 24)
        self.assertEqual(len(self.keys.calls), 9)

    def test_lifecycle_preserves_foreign_rules_and_second_cleanup_is_noop(self):
        self.ready()
        self.lifecycle.up()
        before = copy.deepcopy(self.runner.rules)
        for spec in self.lifecycle.guards() + self.lifecycle.permits():
            self.lifecycle.rule(spec, True)
        self.assertEqual(before, self.runner.rules)
        self.lifecycle.down()
        count = len(self.runner.calls)
        self.lifecycle.down()
        self.assertEqual(count, len(self.runner.calls))
        self.assertFalse(self.lifecycle.marker.exists())
        self.assertEqual([r for rules in self.runner.rules.values() for r in rules], [self.runner.foreign])

    def test_guards_before_setconf_and_up_and_policy_checks_before_permits(self):
        self.ready()
        self.lifecycle.up()
        calls = self.runner.calls
        index = next(i for i, argv in enumerate(calls) if 'setconf' in argv)
        self.assertEqual(sum('-I' in argv for argv in calls[:index]), len(self.lifecycle.guards()))
        up = calls.index(['ip', 'link', 'set', 'dev', control.IFACE, 'up'])
        self.assertLess(index, up)
        first_permit = next(i for i, argv in enumerate(calls) if '-I' in argv and 'ACCEPT' in argv)
        self.assertGreater(first_permit, max(i for i, argv in enumerate(calls) if 'get' in argv))

    def test_rule_order_public_only_per_peer_and_ipv6_only_owned_interface(self):
        self.ready()
        self.lifecycle.up()
        rules = self.runner.rules[('iptables', 'filter', 'FORWARD')]
        for peer in self.lifecycle.peers:
            accept = next(i for i, rule in enumerate(rules) if '-s' in rule and peer in rule and 'ACCEPT' in rule)
            for destination in control.NON_PUBLIC:
                self.assertLess(next(i for i, rule in enumerate(rules) if destination in rule), accept)
        for key, bucket in self.runner.rules.items():
            if key[0] == 'ip6tables':
                self.assertTrue(all(control.IFACE in rule and 'DROP' in rule for rule in bucket))
        nat = self.runner.rules[('iptables', 'nat', 'POSTROUTING')]
        self.assertEqual(len(nat), 2)
        self.assertTrue(all('/32' in rule[1] and 'ens3' in rule for rule in nat))

    def test_every_firewall_mutation_is_exact_checked_and_comment_scoped(self):
        self.ready()
        self.lifecycle.up()
        self.lifecycle.down()
        for i, command in enumerate(self.runner.calls):
            if command[0] not in ('iptables', 'ip6tables') or command[5] not in ('-I', '-D'):
                continue
            previous = self.runner.calls[i - 1]
            self.assertEqual(previous[:5], command[:5])
            self.assertEqual(previous[5], '-C')
            self.assertEqual(previous[7:], command[8:] if command[5] == '-I' else command[7:])
            self.assertIn(command[-1], ('awg-uk', 'awg-uk-startup'))
            self.assertEqual(command[-4:-1], control.COMMENT[:-1])
        self.assertFalse(any(token in ('flush', '-F', '-P', 'sysctl', 'systemctl', 'route-add')
                             for argv in self.runner.calls for token in argv))

    def test_duplicate_exact_cleanup_uses_snapshot_not_changed_configs(self):
        self.ready()
        self.lifecycle.up()
        for key in self.runner.rules:
            if key[0] == 'iptables' and key[1] == 'nat':
                self.runner.rules[key] *= 3
        (self.root / 'server.conf').unlink()
        (self.root / 'site.json').unlink()
        self.lifecycle.down()
        self.assertEqual([r for rules in self.runner.rules.values() for r in rules], [self.runner.foreign])

    def test_foreign_invocation_and_missing_identity_never_clean_up(self):
        self.ready()
        self.lifecycle.invocation = 'foreign'
        before = len(self.runner.calls)
        self.lifecycle.down()
        self.assertEqual(before, len(self.runner.calls))
        self.assertTrue(self.lifecycle.marker.exists())
        self.lifecycle.invocation = None
        with self.assertRaises(control.Failure):
            self.lifecycle.preflight()

    def test_recreated_interface_and_unknown_index_are_not_deleted(self):
        self.ready()
        self.lifecycle.up()
        self.runner.links[-1]['ifindex'] = 99
        before = len(self.runner.calls)
        with self.assertRaises(control.Failure):
            self.lifecycle.down()
        self.assertFalse(any('delete' in argv for argv in self.runner.calls[before:]))
        self.assertTrue(self.lifecycle.marker.exists())

    def test_start_failure_before_capture_preserves_unknown_interface_metadata(self):
        self.ready()
        with self.assertRaises(control.Failure):
            self.lifecycle.down()
        self.assertTrue(self.lifecycle.marker.exists())

    def test_start_failure_before_daemon_creation_cleanup_is_safe(self):
        self.preflight()
        self.lifecycle.down()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_all_mutation_failure_points_preserve_ownership_and_redact(self):
        # One isolated tmpdir fixture per subtest; no actual commands executed.
        self.ready()
        self.lifecycle.up()
        dangerous = [argv for argv in self.runner.calls if ('-I' in argv or '-D' in argv or 'setconf' in argv
                     or argv[:2] in (['ip', 'address'], ['ip', 'link']))]
        self.lifecycle.down()
        for fail_command in dangerous:
            with self.subTest(command=fail_command[:7]):
                # Reuse only disposable fixture paths; reset in-memory network state.
                self.runner = FakeRunner()
                self.lifecycle.runner = self.runner
                self.ready()
                self.runner.fail = lambda argv, target=fail_command: argv == target
                with self.assertRaises(control.Failure) as error:
                    self.lifecycle.up()
                self.assertNotIn('SECRET', str(error.exception))
                self.assertTrue(self.lifecycle.marker.exists())
                self.runner.fail = None
                self.lifecycle.down()

    def test_partial_permit_install_stays_behind_startup_drops(self):
        self.ready()
        self.runner.fail = lambda argv: '-I' in argv and '10.0.0.0/8' in argv
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        rules = self.runner.rules[('iptables', 'filter', 'FORWARD')]
        self.assertTrue(all('awg-uk-startup' in rule and 'DROP' in rule for rule in rules[:2]))
        self.assertTrue(any('ACCEPT' in rule and rule != self.runner.foreign for rule in rules[2:]))
        self.assertTrue(self.lifecycle.marker.exists())

    def test_configuration_drift_is_rejected_before_commands(self):
        self.ready()
        text = (self.root / 'server.conf').read_text()
        (self.root / 'server.conf').write_text(text.replace(stub(1), stub(42)))
        count = len(self.runner.calls)
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertEqual(count, len(self.runner.calls))

    def test_unconfirmed_delete_preserves_guards_and_metadata(self):
        self.ready()
        self.lifecycle.up()
        actual = self.runner.run
        def pretend_delete(argv):
            if argv == ['ip', 'link', 'delete', 'dev', control.IFACE]:
                self.runner.calls.append(argv)
                return 0, ''
            return actual(argv)
        self.runner.run = pretend_delete
        before = copy.deepcopy(self.runner.rules)
        with self.assertRaises(control.Failure):
            self.lifecycle.down()
        self.assertEqual(before, self.runner.rules)
        self.assertTrue(self.lifecycle.marker.exists())

    def test_cleanup_failures_keep_metadata_and_guards_until_retry(self):
        for action in ('down', 'delete', '-D'):
            with self.subTest(action=action):
                self.ready()
                self.lifecycle.up()
                before = copy.deepcopy(self.runner.rules)
                self.runner.fail = lambda argv: action in argv
                with self.assertRaises(control.Failure):
                    self.lifecycle.down()
                self.assertTrue(self.lifecycle.marker.exists())
                if action != '-D':
                    self.assertEqual(before, self.runner.rules)
                self.runner.fail = None
                self.lifecycle.down()

    def test_setconf_error_and_bad_forward_or_return_route_fail_closed(self):
        self.ready()
        for field, value in (('dev', 'tailscale0'), ('gateway', '10.99.0.1'), ('return_dev', 'foreign')):
            original = getattr(self.runner, field)
            setattr(self.runner, field, value)
            with self.assertRaises(control.Failure):
                self.lifecycle.up()
            self.no_permits()
            setattr(self.runner, field, original)
        self.runner.fail = lambda argv: 'setconf' in argv
        with self.assertRaises(control.Failure) as error:
            self.lifecycle.up()
        self.assertNotIn('SECRET', str(error.exception))
        self.no_permits()

    def test_readiness_timeout_no_sleep_no_real_socket_no_commands(self):
        self.preflight()
        count = len(self.runner.calls)
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertAlmostEqual(self.clock[0], 10.0)
        self.assertEqual(count, len(self.runner.calls))
        self.assertTrue(self.lifecycle.marker.exists())

    def test_already_up_interface_is_rejected_before_setconf(self):
        self.ready()
        self.runner.links[-1]['flags'] = ['UP']
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertFalse(any('setconf' in argv for argv in self.runner.calls))

    def test_preflight_resource_collisions_never_claim_or_mutate(self):
        variations = [
            lambda: self.runner.links.append({'ifname': control.IFACE, 'ifindex': 99}),
            lambda: self.socket.touch(),
            lambda: setattr(self.runner, 'busy', True),
            lambda: setattr(self.runner, 'listing', '-A FORWARD -i awguk -j DROP'),
            lambda: setattr(self.runner, 'listing', '-A INPUT -m comment --comment awg-uk -j DROP'),
            lambda: self.runner.addresses.append({'ifname': 'docker0', 'addr_info': [{'local': '10.214.0.1', 'prefixlen': 16}]}),
            lambda: self.runner.routes.append({'dst': '10.214.91.0/25', 'table': 52}),
        ]
        for mutate in variations:
            self.runner = FakeRunner()
            self.lifecycle.runner = self.runner
            if self.socket.exists():
                self.socket.unlink()
            mutate()
            with self.assertRaises(control.Failure):
                self.preflight()
            self.assertFalse(self.lifecycle.marker.exists())
            self.assertFalse(any('-I' in argv or '-D' in argv for argv in self.runner.calls))

    def test_external_facts_and_forwarding_must_match_without_writes(self):
        for field in ('dev', 'gateway'):
            value = getattr(self.runner, field)
            setattr(self.runner, field, 'wrong')
            with self.assertRaises(control.Failure):
                self.preflight()
            setattr(self.runner, field, value)
        for field, value in (('local', '194.87.166.59'), ('prefixlen', 24)):
            addr = self.runner.addresses[0]['addr_info'][0]
            old = addr[field]
            addr[field] = value
            with self.assertRaises(control.Failure):
                self.preflight()
            addr[field] = old
        self.forwarding.write_text('0\n')
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertEqual(self.forwarding.read_text(), '0\n')
        self.assertFalse(self.lifecycle.marker.exists())

    def test_stale_marker_never_adopted_and_firewall_check_error_not_absence(self):
        self.preflight()
        with self.assertRaises(control.Failure):
            self.preflight()
        self.lifecycle.down()
        self.runner.fail = lambda argv: argv[0] == 'ip6tables'
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_config_forbids_hooks_advancedsecurity_duplicates_and_non32(self):
        text = (self.root / 'server.conf').read_text()
        variants = [text + '\nPostUp = SECRET\n', text + '\nAdvancedSecurity = on\n',
                    text.replace('10.214.91.2/32', '10.214.91.2/24'),
                    text.replace('10.214.91.3/32', '10.214.91.2/32'),
                    text.replace('10.214.91.3/32', '10.214.91.1/32'),
                    text.replace('10.214.91.3/32', '10.214.91.255/32'),
                    text.replace('ContentPaddingAddition = 4-28', 'ContentPaddingAddition = 1-2'),
                    text + '\n[Interface]\n', text + '\n[Peer]\n']
        for variant in variants:
            with self.assertRaises(control.Failure) as error:
                control.native_peers(variant)
            self.assertNotIn('SECRET', str(error.exception))

    def test_hash_mode_and_symlink_checks_do_not_execute(self):
        (self.root / 'awg').write_text('TAMPERED_NOT_EXECUTABLE')
        with self.assertRaisesRegex(control.Failure, 'hash mismatch'):
            self.preflight()
        self.assertEqual(self.runner.calls, [])
        target = self.base / 'wrong-mode'
        target.write_text('NON_SECRET')
        target.chmod(0o644)
        with self.assertRaises(control.Failure):
            control.secure(target, 0o600)
        link = self.base / 'link'
        link.symlink_to(target)
        with self.assertRaises(control.Failure):
            control.secure(link, 0o600)
        with self.assertRaises(FileExistsError):
            control.write_new(link, 'NO_OVERWRITE')
        self.assertEqual(target.read_text(), 'NON_SECRET')

    def test_runtime_keygen_uses_only_pinned_binary_and_private_stdin(self):
        from types import SimpleNamespace
        keygen = issuer.Keygen(self.root / 'awg')
        output = io.StringIO()
        with patch('issuer.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=stub(99) + '\n')) as run:
            with redirect_stdout(output):
                self.assertEqual(keygen.run('pubkey', stub(98) + '\n'), stub(99))
            self.assertEqual(run.call_args.args[0], [str(self.root / 'awg'), 'pubkey'])
            self.assertEqual(run.call_args.kwargs['input'], stub(98) + '\n')
            self.assertTrue(run.call_args.kwargs['capture_output'])
        self.assertEqual(output.getvalue(), '')
        with patch('issuer.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='SECRET')):
            with self.assertRaises(control.Failure) as error:
                keygen.run('genkey')
            self.assertNotIn('SECRET', str(error.exception))

    def test_interface_forwarding_is_read_only_and_must_already_be_one(self):
        path = self.base / 'conf' / 'ens3' / 'forwarding'
        path.write_text('0\n')
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertEqual(path.read_text(), '0\n')
        path.write_text('1\n')
        self.ready()
        path = self.base / 'conf' / control.IFACE / 'forwarding'
        path.write_text('0\n')
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertEqual(path.read_text(), '0\n')
        self.no_permits()

    def test_metadata_replace_failure_keeps_original_evidence(self):
        self.ready()
        before = self.lifecycle.marker.read_bytes()
        with patch.object(control.os, 'replace', side_effect=OSError('FAKE_FAILURE')):
            with self.assertRaises(OSError):
                self.lifecycle.up()
        self.assertEqual(before, self.lifecycle.marker.read_bytes())
        self.assertTrue((self.runtime / 'owned.pending').exists())
        self.assertFalse(any('setconf' in argv for argv in self.runner.calls))

    def test_site_and_public_example_reject_guesses_and_placeholders(self):
        for field in settings()['site']:
            site = dict(settings()['site'])
            del site[field]
            with self.assertRaises(control.Failure):
                control.site_check(site)
        site = dict(settings()['site'], external_ipv4='81.29.155.74')
        with self.assertRaises(control.Failure):
            control.site_check(site)
        example = json.loads((BUNDLE / 'settings.example.json').read_text())
        with self.assertRaises(control.Failure):
            issuer.init(self.base / 'invalid', example, self.keys)
        self.assertFalse((self.base / 'invalid').exists())

    def test_issuer_unique_users_keys_psks_hpk_and_private_permissions(self):
        alice, bob = issuer.users(self.state).values()
        identity = issuer.load(self.state / 'identity.json')
        self.assertNotEqual(alice['private'], bob['private'])
        self.assertNotEqual(alice['psk'], bob['psk'])
        self.assertNotIn(identity['header'], (alice['psk'], bob['psk']))
        for directory in (self.state, self.state / 'users', self.state / 'clients'):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            for path in directory.iterdir():
                if path.is_file():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for path in (self.state / 'clients').iterdir():
            text = path.read_text()
            for required in ('MTU = 1280', 'AllowedIPs = 0.0.0.0/0, ::/0',
                             'Endpoint = 91.108.225.14:49381', 'ContentPaddingAddition = 4-28',
                             'RandomTrailers = on', 'HeaderProtectionKey = '):
                self.assertIn(required, text)
            self.assertNotIn('AdvancedSecurity', text)

    def test_issuer_no_overwrite_no_stdout_and_exclusive_revocation_render(self):
        output = io.StringIO()
        before = len(self.keys.calls)
        with redirect_stdout(output), self.assertRaises(control.Failure):
            issuer.add(self.state, 'alice', self.keys)
        self.assertEqual(len(self.keys.calls), before)
        self.assertEqual(output.getvalue(), '')
        path = self.base / 'reviewed-server.conf'
        issuer.render(self.state, path, ['alice'])
        self.assertEqual(control.native_peers(path.read_text()), ['10.214.91.3/32'])
        issuer.render(self.state, self.base / 'no-peers.conf', ['alice', 'bob'])
        self.assertEqual(control.native_peers((self.base / 'no-peers.conf').read_text()), [])
        with self.assertRaises(FileExistsError):
            issuer.render(self.state, path, [])
        with self.assertRaises(control.Failure):
            issuer.render(self.state, self.base / 'unknown.conf', ['missing'])
        self.assertEqual(len(self.keys.calls), before)

    def test_issuer_rejects_private_dns_bad_names_and_existing_init(self):
        for dns in (['100.100.100.100'], ['192.168.1.1'], ['::1'], []):
            with self.assertRaises(control.Failure):
                issuer.check_dns(dns)
        for name in ('../escape', 'UPPER', 'a.conf', '', '-a'):
            with self.assertRaises(control.Failure):
                issuer.add(self.state, name, self.keys)
        with self.assertRaises(FileExistsError):
            issuer.init(self.state, settings(), self.keys)

    def test_render_rejects_duplicate_peer_state_and_reused_keys(self):
        users = issuer.users(self.state)
        users['bob']['address'] = users['alice']['address']
        identity, _, profile, _ = issuer.state(self.state)
        with self.assertRaises(control.Failure):
            issuer.server_text(identity, profile, users)
        users['bob']['address'] = '10.214.91.3/32'
        users['bob']['psk'] = users['alice']['psk']
        with self.assertRaises(control.Failure):
            issuer.server_text(identity, profile, users)

    def test_cli_keygen_requires_explicit_flag_and_no_runtime_in_repo(self):
        for args in (
                ['issuer.py', '--directory', str(self.base / 'new'), 'init', '--settings', 'public.json', '--awg', 'awg'],
                ['issuer.py', '--directory', str(self.state), 'add', 'charlie', '--awg', 'awg']):
            with patch.object(sys, 'argv', args), patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit):
                issuer.main()
        with patch.object(sys, 'argv', ['issuer.py', '--directory', str(BUNDLE), 'render',
                                      '--output', str(self.base / 'out')]), self.assertRaises(control.Failure):
            issuer.main()
        self.assertEqual(len(self.keys.calls), 9)

    def test_unit_is_named_foreground_private_and_no_shared_runtime_management(self):
        unit = (BUNDLE / 'awg-uk.service').read_text()
        for text in ('ExecStart=/etc/awg-uk/amneziawg-go -f awguk', 'ExecStopPost=',
                     'RuntimeDirectoryPreserve=yes', 'StandardOutput=null', 'StandardError=null',
                     'DeviceAllow=/dev/net/tun rw', 'ProtectKernelTunables=yes', 'Restart=no'):
            self.assertIn(text, unit)
        self.assertNotIn('RuntimeDirectory=amneziawg', unit)
        self.assertNotIn('awg-s22-test', unit)


if __name__ == '__main__':
    unittest.main()
