"""Offline-only tests: commands are recorded, never executed."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('awg_s22_control', BUNDLE / 'control.py')
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.rules = {}
        self.links = [{'ifname': 'eth0'}]
        self.addresses = [{'ifname': 'eth0', 'addr_info': [
            {'local': '31.58.85.163', 'prefixlen': 32}]}]
        self.routes = [{'dst': 'default', 'gateway': '10.0.0.1', 'dev': 'eth0'}]
        self.forward_dev = 'eth0'
        self.gateway = '10.0.0.1'
        self.return_dev = 'awgs22'
        self.port_busy = False
        self.fail = None
        self.foreign = ('UNRELATED_PRODUCTION_RULE',)
        self.rules[('iptables', 'filter', 'FORWARD')] = [self.foreign]

    def run(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if self.fail and self.fail(argv):
            return 2, 'SECRET_ERROR_MUST_NEVER_ESCAPE'
        if argv[0] in ('iptables', 'ip6tables'):
            assert argv[1:3] == ['-w', '5']
            assert argv[3] == '-t'
            tool, table, action, chain = argv[0], argv[4], argv[5], argv[6]
            args = tuple(argv[8:] if action == '-I' else argv[7:])
            bucket = self.rules.setdefault((tool, table, chain), [])
            if action == '-C':
                return (0 if args in bucket else 1), ''
            if action == '-I':
                assert argv[7] == '1'
                bucket.insert(0, args)
            elif action == '-D':
                bucket.remove(args)
            else:
                raise AssertionError('unexpected firewall mutation')
            return 0, ''
        if argv == ['ip', '-j', 'link', 'show']:
            return 0, json.dumps(self.links)
        if argv == ['ip', '-j', '-4', 'address', 'show']:
            return 0, json.dumps(self.addresses)
        if argv == ['ip', '-j', '-4', 'route', 'show', 'table', 'all']:
            return 0, json.dumps(self.routes)
        if argv[:6] == ['ip', '-j', '-4', 'route', 'get', '10.213.211.2']:
            return 0, json.dumps([{'dev': self.return_dev}])
        if argv[:5] == ['ip', '-j', '-4', 'route', 'get']:
            return 0, json.dumps([{'dev': self.forward_dev, 'gateway': self.gateway}])
        if argv[0] == 'ss':
            return 0, 'bound' if self.port_busy else ''
        if argv == ['ip', 'link', 'delete', 'dev', 'awgs22']:
            self.links = [item for item in self.links if item['ifname'] != 'awgs22']
            return 0, ''
        if argv[:2] in (['ip', 'address'], ['ip', 'link']) or argv[1:2] == ['setconf']:
            return 0, ''
        raise AssertionError(f'unexpected command: {argv!r}')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        # Even disposable test writes stay inside the assigned exclusive prefix.
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=BUNDLE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'private'
        self.runtime = self.base / 'runtime'
        self.root.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        self.forwarding = self.base / 'forwarding'
        self.forwarding.write_text('1\n')
        self.interface = self.base / 'interface'
        self.socket = self.base / 'uapi.sock'
        self.runner = FakeRunner()
        self.lifecycle = control.Lifecycle(
            runner=self.runner, root=self.root, runtime=self.runtime,
            socket=self.socket, forwarding=self.forwarding,
            interface_path=self.interface, invocation='current-invocation')

    def own(self):
        self.lifecycle.marker.write_text('current-invocation')

    def ready(self):
        self.own()
        self.interface.touch()
        self.runner.links.append({'ifname': 'awgs22'})
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(self.socket))
        self.addCleanup(sock.close)

    def preflight(self):
        with patch.object(self.lifecycle, 'config_check'), patch.object(
                control.Path, 'exists', autospec=True, side_effect=lambda p:
                True if str(p) == '/dev/net/tun' else p.is_file() or p.is_dir()), patch.object(
                control.os, 'uname') as uname:
            uname.return_value.machine = 'x86_64'
            self.lifecycle.preflight()

    def test_up_and_down_preserve_foreign_rules_and_are_idempotent(self):
        self.ready()
        self.lifecycle.up()
        rules = {key: list(value) for key, value in self.runner.rules.items()}
        for spec in self.lifecycle.guards() + self.lifecycle.permits():
            self.lifecycle.rule(spec, True)
        self.assertEqual(rules, self.runner.rules)
        self.lifecycle.down()
        calls = len(self.runner.calls)
        self.lifecycle.down()
        self.assertEqual(calls, len(self.runner.calls))
        self.assertFalse(self.lifecycle.marker.exists())
        self.assertEqual(self.runner.rules[('iptables', 'filter', 'FORWARD')],
                         [self.runner.foreign])
        self.assertFalse(any(rule for key, rules in self.runner.rules.items()
                             for rule in rules if rule != self.runner.foreign))
        self.assertFalse(any(link['ifname'] == 'awgs22' for link in self.runner.links))

    def test_guards_precede_setconf_and_link_up(self):
        self.ready()
        self.lifecycle.up()
        calls = self.runner.calls
        configured = next(i for i, c in enumerate(calls) if 'setconf' in c)
        guards = [c for c in calls[:configured] if '-I' in c]
        self.assertEqual(len(guards), len(self.lifecycle.guards()))
        self.assertFalse(any('-j' in c and 'ACCEPT' in c for c in calls[:configured]))
        self.assertLess(configured, calls.index(['ip', 'link', 'set', 'dev', 'awgs22', 'up']))

    def test_destination_drops_precede_client_accept_and_guards(self):
        self.ready()
        self.lifecycle.up()
        rules = self.runner.rules[('iptables', 'filter', 'FORWARD')]
        accept = next(i for i, r in enumerate(rules) if '-s' in r and 'ACCEPT' in r)
        guard = next(i for i, r in enumerate(rules) if r[:2] == ('-i', 'awgs22')
                     and '-d' not in r and 'DROP' in r)
        self.assertLess(accept, guard)
        for network in control.NON_PUBLIC:
            index = next(i for i, r in enumerate(rules) if network in r)
            self.assertLess(index, accept)
        for key, rules in self.runner.rules.items():
            if key[0] == 'ip6tables':
                self.assertTrue(all('DROP' in r for r in rules))

    def test_each_mutation_has_exact_check_and_comment(self):
        self.ready()
        self.lifecycle.up()
        self.lifecycle.down()
        for index, command in enumerate(self.runner.calls):
            if command[0] not in ('iptables', 'ip6tables') or command[5] == '-C':
                continue
            self.assertIn('awg-s22-test', command)
            previous = self.runner.calls[index - 1]
            self.assertEqual(previous[:5], command[:5])
            self.assertEqual(previous[5], '-C')
            expected = command[8:] if command[5] == '-I' else command[7:]
            self.assertEqual(previous[7:], expected)

    def test_delete_duplicate_exact_rules_only(self):
        self.own()
        spec = self.lifecycle.permits()[0]
        self.lifecycle.rule(spec, True)
        key = tuple(spec[:3])
        self.runner.rules[key] *= 3
        self.lifecycle.down()
        self.assertEqual(self.runner.rules[key], [])

    def test_cleanup_before_interface_creation(self):
        self.own()
        self.lifecycle.down()
        self.assertFalse(self.lifecycle.marker.exists())
        self.assertFalse(any(c[:2] == ['ip', 'link'] for c in self.runner.calls))

    def test_foreign_invocation_is_not_touched(self):
        self.ready()
        self.lifecycle.marker.write_text('older-invocation')
        self.lifecycle.down()
        self.assertEqual(self.runner.calls, [])
        self.assertTrue(self.lifecycle.marker.exists())
        with self.assertRaises(control.Failure):
            self.lifecycle.up()

    def test_missing_invocation_cannot_own_or_cleanup(self):
        self.ready()
        self.lifecycle.invocation = None
        self.lifecycle.down()
        self.assertEqual(self.runner.calls, [])
        with self.assertRaises(control.Failure):
            self.lifecycle.preflight()

    def test_interface_delete_failure_preserves_guards_and_marker(self):
        self.ready()
        self.lifecycle.up()
        before = {key: list(value) for key, value in self.runner.rules.items()}
        self.runner.fail = lambda c: c[:3] == ['ip', 'link', 'delete']
        with self.assertRaises(control.Failure):
            self.lifecycle.down()
        self.assertTrue(self.lifecycle.marker.exists())
        self.assertEqual(before, self.runner.rules)
        self.runner.fail = None
        self.lifecycle.down()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_failed_rule_cleanup_can_be_retried(self):
        self.ready()
        self.lifecycle.up()
        self.runner.fail = lambda c: '-D' in c
        with self.assertRaises(control.Failure):
            self.lifecycle.down()
        self.assertTrue(self.lifecycle.marker.exists())
        self.runner.fail = None
        self.lifecycle.down()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_config_failure_remains_closed_and_redacted(self):
        self.ready()
        self.runner.fail = lambda c: 'setconf' in c
        with self.assertRaises(control.Failure) as error:
            self.lifecycle.up()
        self.assertNotIn('SECRET', str(error.exception))
        self.assertFalse(any('ACCEPT' in r for rules in self.runner.rules.values() for r in rules))
        self.lifecycle.down()

    def test_wrong_policy_route_keeps_all_permits_absent(self):
        self.ready()
        self.runner.forward_dev = 'tailscale0'
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertFalse(any('ACCEPT' in r for rules in self.runner.rules.values() for r in rules))
        self.lifecycle.down()

    def test_wrong_gateway_and_return_route_fail_closed(self):
        for field in ('gateway', 'return_dev'):
            with self.subTest(field=field):
                self.ready()
                original = getattr(self.runner, field)
                setattr(self.runner, field, 'unexpected')
                with self.assertRaises(control.Failure):
                    self.lifecycle.up()
                self.assertFalse(any('ACCEPT' in r for rules in self.runner.rules.values() for r in rules))
                self.lifecycle.down()
                self.socket.unlink()
                setattr(self.runner, field, original)

    def test_readiness_has_ten_second_deadline_without_commands(self):
        self.own()
        clock = [0.0]
        self.lifecycle.clock = lambda: clock[0]
        self.lifecycle.sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        with self.assertRaises(control.Failure):
            self.lifecycle.up()
        self.assertAlmostEqual(clock[0], 10)
        self.assertEqual(self.runner.calls, [])

    def test_firewall_check_errors_are_not_treated_as_rule_absence(self):
        self.runner.fail = lambda c: c[0] == 'iptables'
        with self.assertRaises(control.Failure):
            self.lifecycle.rule(self.lifecycle.permits()[0], True)
        self.assertEqual(len(self.runner.calls), 1)
        self.assertIn('-C', self.runner.calls[0])

    def test_preflight_creates_current_invocation_marker(self):
        self.preflight()
        self.assertTrue(self.lifecycle.owned())
        self.lifecycle.down()

    def test_preflight_rejects_conflicting_address(self):
        self.runner.addresses.append({'ifname': 'docker0', 'addr_info': [
            {'local': '10.213.0.1', 'prefixlen': 16}]})
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_preflight_rejects_conflicting_route_in_any_table(self):
        self.runner.routes.append({'dst': '10.213.211.0/24', 'table': 52})
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_preflight_rejects_missing_forwarding_without_writing_it(self):
        self.forwarding.write_text('0\n')
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertEqual(self.forwarding.read_text(), '0\n')

    def test_preflight_rejects_existing_interface_without_adoption(self):
        self.runner.links.append({'ifname': 'awgs22'})
        with self.assertRaises(control.Failure):
            self.preflight()
        self.lifecycle.down()
        self.assertFalse(any('delete' in c for c in self.runner.calls))

    def test_preflight_rejects_port_collision(self):
        self.runner.port_busy = True
        with self.assertRaises(control.Failure):
            self.preflight()
        self.assertFalse(self.lifecycle.marker.exists())

    def test_preflight_rejects_stale_exact_rule_without_adoption(self):
        self.lifecycle.rule(self.lifecycle.permits()[0], True)
        before = {key: list(value) for key, value in self.runner.rules.items()}
        with self.assertRaises(control.Failure):
            self.preflight()
        self.lifecycle.down()
        self.assertFalse(self.lifecycle.marker.exists())
        self.assertEqual({key: rules for key, rules in before.items() if rules},
                         {key: rules for key, rules in self.runner.rules.items() if rules})

    def test_preflight_rejects_stale_marker_without_cleanup(self):
        self.lifecycle.marker.write_text('older-invocation')
        with self.assertRaises(control.Failure):
            self.preflight()
        before = len(self.runner.calls)
        self.lifecycle.down()
        self.assertEqual(before, len(self.runner.calls))
        self.assertEqual(self.lifecycle.marker.read_text(), 'older-invocation')

    def test_config_native_constraints_and_no_secret_error(self):
        config = ('[Interface]\nPrivateKey = NOT_A_REAL_KEY\nListenPort = 49380\n'
                  'Jc = 4\n[Peer]\nPublicKey = NOT_A_REAL_KEY\n'
                  'AllowedIPs = 10.213.211.2/32\n')
        for name in control.PINS:
            (self.root / name).write_bytes(b'NOT_AN_EXECUTABLE')
        with patch.object(self.lifecycle, 'secure'), patch.object(control.hashlib, 'sha256') as digest:
            # One digest per executable, independent of parser-focused variations.
            digest.return_value.hexdigest.side_effect = list(control.PINS.values()) * 8
            (self.root / 'server.conf').write_text(config)
            self.lifecycle.config_check()
            for extra in ('Address = 10.213.211.1/30', 'MTU = 1280',
                          'FwMark = 1', 'PostUp = SECRET_ERROR',
                          'AllowedIPs = 0.0.0.0/0', '[Peer]'):
                (self.root / 'server.conf').write_text(config + extra + '\n')
                with self.assertRaises(control.Failure) as error:
                    self.lifecycle.config_check()
                self.assertNotIn('SECRET_ERROR', str(error.exception))

    def test_hash_mismatch_fails_without_executing_binary(self):
        for name in control.PINS:
            (self.root / name).write_bytes(b'NOT_AN_EXECUTABLE')
        with patch.object(self.lifecycle, 'secure'):
            with self.assertRaisesRegex(control.Failure, 'hash mismatch'):
                self.lifecycle.config_check()
        self.assertEqual(self.runner.calls, [])

    def test_unit_is_foreground_scoped_and_does_not_manage_shared_runtime(self):
        unit = (BUNDLE / 'awg-s22-test.service').read_text()
        self.assertIn('ExecStart=/etc/awg-s22-test/amneziawg-go -f awgs22', unit)
        self.assertIn('ExecStopPost=/usr/bin/python3 /etc/awg-s22-test/control.py down', unit)
        self.assertNotIn('RuntimeDirectory=amneziawg', unit)
        self.assertIn('RuntimeDirectoryPreserve=yes', unit)
        self.assertIn('DeviceAllow=/dev/net/tun rw', unit)
        self.assertIn('AF_NETLINK', unit)
        self.assertIn('StandardError=null', unit)
        self.assertIn('Restart=no', unit)


if __name__ == '__main__':
    unittest.main()
