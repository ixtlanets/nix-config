import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'm1max_split_dns', Path(__file__).parents[1] / 'scripts/m1max-split-dns.py'
)
dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dns)


class SplitDnsSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.base = root / 'state'
        self.base.mkdir()
        self.resolver = root / 'resolver' / 'tailf108.ts.net'
        self.resolver.parent.mkdir()
        self.plist = root / 'helper.plist'
        patches = ExitStack()
        self.addCleanup(patches.close)
        for name, value in [('BASE', self.base), ('RESOLVER', self.resolver),
                            ('PLIST', self.plist)]:
            patches.enter_context(patch.object(dns, name, value))

    def save_before(self, resolver_existed):
        before = {
            'corp_dns': True,
            'resolver_existed': resolver_existed,
            'resolver_mode': 0o640,
            'exit_node': '',
            'route_all': True,
            'exit_ip': '203.0.113.7',
        }
        (self.base / 'before.json').write_text(json.dumps(before))

    def test_rollback_restores_files_even_when_tailscale_cli_fails(self):
        self.save_before(resolver_existed=True)
        original = b'nameserver 192.0.2.53\n'
        (self.base / 'resolver-before').write_bytes(original)
        self.resolver.write_text('nameserver 100.100.100.100\n')
        self.plist.write_text('temporary helper')

        def run(command, **kwargs):
            if command == dns.CLI + ['set', '--accept-dns=true']:
                self.assertEqual(self.resolver.read_bytes(), original)
                self.assertEqual(self.resolver.stat().st_mode & 0o777, 0o640)
                self.assertFalse(self.plist.exists())
                raise RuntimeError('Tailscale unavailable')
            return SimpleNamespace(returncode=0, stdout='')

        with patch.object(dns, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'Tailscale unavailable'):
                dns.rollback()

        receipt = json.loads((self.base / 'result.json').read_text())
        self.assertEqual(receipt['status'], 'rollback-failed')
        self.assertEqual(receipt['error'], 'RuntimeError')
        self.assertFalse((self.base / 'accepted').exists())

    def test_rollback_restores_absent_resolver_when_cli_times_out(self):
        self.save_before(resolver_existed=False)
        self.resolver.write_text('nameserver 100.100.100.100\n')
        self.plist.write_text('temporary helper')

        def run(command, **kwargs):
            if command == dns.CLI + ['set', '--accept-dns=true']:
                self.assertFalse(self.resolver.exists())
                self.assertFalse(self.plist.exists())
                raise subprocess.TimeoutExpired(command, 20)
            return SimpleNamespace(returncode=0, stdout='')

        with patch.object(dns, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                dns.rollback()

        receipt = json.loads((self.base / 'result.json').read_text())
        self.assertEqual(receipt['status'], 'rollback-failed')
        self.assertEqual(receipt['error'], 'TimeoutExpired')

    def test_watchdog_retries_failed_rollback(self):
        (self.base / 'armed.json').write_text(json.dumps({'deadline': 99}))
        with patch.object(dns.time, 'time', return_value=100), \
                patch.object(dns.time, 'sleep') as sleep, \
                patch.object(dns, 'rollback', side_effect=[
                    subprocess.TimeoutExpired('tailscale', 20), None,
                ]) as rollback:
            dns.watchdog()

        self.assertEqual(rollback.call_count, 2)
        sleep.assert_called_once_with(15)

    def check_accept_rejected(self, deadline, rollback_started=False):
        self.save_before(resolver_existed=False)
        (self.base / 'armed.json').write_text(json.dumps({'deadline': deadline}))
        if rollback_started:
            (self.base / 'result.json').write_text(json.dumps({'status': 'rolling-back'}))

        def run(command, **kwargs):
            if command[:2] == ['/usr/sbin/scutil', '--nc']:
                return SimpleNamespace(stdout='Connected\n')
            if command == dns.CLI + ['debug', 'prefs']:
                return SimpleNamespace(stdout=json.dumps({
                    'CorpDNS': False, 'ExitNodeID': '', 'RouteAll': True,
                }))
            if command[0] == '/usr/bin/python3':
                self.assertEqual(kwargs['timeout'], 12)
                return SimpleNamespace(stdout='')
            if command[0] == '/usr/bin/curl':
                return SimpleNamespace(stdout='ip=203.0.113.7\n')
            self.fail('Unexpected external command: ' + repr(command))

        with patch.object(dns, 'reconcile'), \
                patch.object(dns, 'run', side_effect=run), \
                patch.object(dns.time, 'time', return_value=100):
            with self.assertRaisesRegex(RuntimeError, 'deadline elapsed or rollback started'):
                dns.accept()

        self.assertFalse((self.base / 'accepted').exists())
        if rollback_started:
            self.assertEqual(json.loads((self.base / 'result.json').read_text()),
                             {'status': 'rolling-back'})
        else:
            self.assertFalse((self.base / 'result.json').exists())

    def test_accept_rejects_expired_deadline_without_success_marker(self):
        self.check_accept_rejected(deadline=100)

    def test_accept_rejects_started_rollback_without_success_marker(self):
        self.check_accept_rejected(deadline=200, rollback_started=True)


if __name__ == '__main__':
    unittest.main()
