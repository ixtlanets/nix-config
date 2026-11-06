import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    't14s_public_ipv4', Path(__file__).parents[1] / 'scripts/t14s-public-ipv4.py'
)
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)


class RollbackTests(unittest.TestCase):
    def test_interface_snapshot_includes_individual_and_dotted_interfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in {'all': '1', 'default': '0', 'eth0': '1', 'veth.1': '0'}.items():
                (root / name).mkdir()
                (root / name / 'disable_ipv6').write_text(value + '\n')
            with patch.object(apply, 'Path', return_value=root):
                self.assertEqual(apply.interface_ipv6_state(), {'eth0': '1', 'veth.1': '0'})

    def test_rollback_enables_ipv6_for_restart_then_restores_each_setting(self):
        self.check_rollback_restart(fails=False)

    def test_failed_rollback_restart_restores_settings_and_records_failure(self):
        self.check_rollback_restart(fails=True)

    def check_rollback_restart(self, fails):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / 'backup'
            base.mkdir()
            ipv6 = root / 'ipv6'
            originals = {'all': '1', 'default': '0', 'eth0': '1', 'veth.1': '0'}
            for name in originals:
                (ipv6 / name).mkdir(parents=True)
                (ipv6 / name / 'disable_ipv6').write_text('0\n')
            (base / 'before.json').write_text(json.dumps({
                'sysctl': {'net.ipv6.conf.all.disable_ipv6': '1',
                           'net.ipv6.conf.default.disable_ipv6': '0'},
                'interface_ipv6': {'eth0': '1', 'veth.1': '0', 'removed-tun': '1'},
                'refresh_timer_active': False,
            }))
            restarted = False

            def run(command, **kwargs):
                nonlocal restarted
                if command[0] == 'sysctl':
                    for setting in command[2:]:
                        key, value = setting.split('=')
                        name = key.split('.')[3]
                        (ipv6 / name / 'disable_ipv6').write_text(value + '\n')
                if command == ['systemctl', 'restart', 'vless-sing-box.service']:
                    restarted = True
                    for name in originals:
                        self.assertEqual((ipv6 / name / 'disable_ipv6').read_text().strip(), '0')
                    if fails:
                        if kwargs.get('check', True):
                            raise RuntimeError('restart failed')
                        return SimpleNamespace(returncode=1)
                return SimpleNamespace(returncode=0)

            with patch.object(apply, 'BASE', base), \
                    patch.object(apply, 'DROP', root / 'drop'), \
                    patch.object(apply, 'HELPER', root / 'helper'), \
                    patch.object(apply, 'Path', return_value=ipv6), \
                    patch.object(apply, 'run', side_effect=run):
                if fails:
                    with self.assertRaisesRegex(RuntimeError, 'restart failed'):
                        apply.rollback()
                else:
                    apply.rollback()

            self.assertTrue(restarted)
            for name, value in originals.items():
                self.assertEqual((ipv6 / name / 'disable_ipv6').read_text().strip(), value)
            receipt = json.loads((base / 'result.json').read_text())
            self.assertEqual(receipt['status'], 'rollback-failed' if fails else 'rolled-back')
            if fails:
                self.assertEqual(receipt['error'], 'RuntimeError')

    def test_watchdog_releases_apply_lock_without_waiting_for_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock'
            process = subprocess.Popen(
                [sys.executable, '-c',
                 'import fcntl,sys,time; f=open(sys.argv[1], "w"); '
                 'fcntl.flock(f, fcntl.LOCK_EX); print("locked", flush=True); time.sleep(30)',
                 str(lock)], stdout=subprocess.PIPE, text=True, start_new_session=True,
            )
            try:
                self.assertEqual(process.stdout.readline().strip(), 'locked')
                started = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
                before = time.monotonic()
                real_open = open
                def open_lock(value, *args, **kwargs):
                    if value == '/var/lib/nikcode-network/t14s/lock':
                        value = lock
                    return real_open(value, *args, **kwargs)
                with patch.object(apply, 'BASE', Path(directory)), \
                        patch.object(apply, 'rollback') as rollback, \
                        patch.object(apply.os, 'geteuid', return_value=0), \
                        patch.object(apply.os, 'umask'), \
                        patch.object(apply.socket, 'gethostname', return_value='t14s'), \
                        patch('builtins.open', side_effect=open_lock), \
                        patch.object(sys, 'argv', ['apply', '--rollback', '--apply-pid', str(process.pid),
                                                   '--apply-start-time', started]):
                    apply.main()
                rollback.assert_called_once()
                self.assertLess(time.monotonic() - before, 2)
                self.assertEqual(process.wait(timeout=2), -signal.SIGKILL)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()

    def test_watchdog_does_not_signal_reused_pid(self):
        with patch.object(apply.os, 'killpg') as kill:
            apply.stop_expired_apply(apply.os.getpid(), 'not-the-current-start-time')
        kill.assert_not_called()

    def test_timer_cleanup_failure_does_not_fail_an_accepted_apply(self):
        with patch.object(apply, 'run', side_effect=subprocess.TimeoutExpired('systemctl', 40)), \
                patch.object(sys, 'stderr') as stderr:
            apply.cancel_watchdog()
        self.assertTrue(stderr.write.called)

    def test_refresh_restart_failure_rolls_back_instead_of_accepting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {name: root / name for name in ['LIVE', 'CANDIDATE', 'DROP', 'HELPER', 'BASE']}
            for name in ['LIVE', 'CANDIDATE', 'DROP', 'HELPER']:
                paths[name].write_text('original-' + name)
            profile = root / 'profile.json'
            profile.write_text(json.dumps({
                'route': {'rules': [
                    {'ip_is_private': True, 'outbound': 'direct'},
                    {'ip_version': 6, 'action': 'reject'},
                ]},
                'dns': {'rules': [{'query_type': ['AAAA']}]},
                'inbounds': [{'type': 'tun', 'address': ['198.19.0.1/30', 'fdfe:dcba:9876::1/126'],
                              'route_exclude_address': ['fc00::/7']}],
            }))
            helper = root / 'new-helper'
            helper.write_text('replacement')
            failed_refresh = False

            def run(command, **kwargs):
                nonlocal failed_refresh
                if command == ['systemctl', 'start', 'nikcode-t14s-refresh.timer'] and not failed_refresh:
                    failed_refresh = True
                    raise RuntimeError('refresh failed')
                return SimpleNamespace(stdout='0', returncode=1 if command[0] == 'curl' else 0)

            def path(value):
                if str(value) == '/proc/sys/net/ipv6/conf':
                    return root / 'empty-proc'
                return Path(value)

            # Keep the real file lock, redirected to this test's private directory.
            real_open = open

            def open_lock(value, *args, **kwargs):
                if value == '/var/lib/nikcode-network/t14s/lock':
                    value = root / 'lock'
                return real_open(value, *args, **kwargs)

            with patch.multiple(apply, **paths), patch.object(apply, 'run', side_effect=run), \
                    patch.object(apply, 'Path', side_effect=path), \
                    patch.object(apply, 'dns_checks'), patch.object(apply, 'restore_tailnet_ipv6'), \
                    patch.object(apply.os, 'geteuid', return_value=0), \
                    patch.object(apply.os, 'setpgrp'), patch.object(apply.os, 'umask'), \
                    patch.object(apply.socket, 'gethostname', return_value='t14s'), \
                    patch('builtins.open', side_effect=open_lock), \
                    patch.object(sys, 'argv', ['apply', '--profile', str(profile), '--dns-helper', str(helper)]):
                with self.assertRaisesRegex(RuntimeError, 'refresh failed'):
                    apply.main()

            self.assertEqual(json.loads((paths['BASE'] / 'result.json').read_text())['status'], 'rolled-back')
            for name in ['LIVE', 'CANDIDATE', 'DROP', 'HELPER']:
                self.assertEqual(paths[name].read_text(), 'original-' + name)


if __name__ == '__main__':
    unittest.main()
