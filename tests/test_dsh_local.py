#!/usr/bin/python3
"""Reuse the VM transaction contract in isolated HOME with mocked tools only."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'dotfiles/dsh/local'
VM = ROOT / 'hosts/omarchy-vm/dsh'
spec = importlib.util.spec_from_file_location('vm_lifecycle_tests', VM / 'tests/test_lifecycle.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class LocalLifecycle(vm.Lifecycle):
    app = 'dsh-local'
    endpoint = 'http://127.0.0.1:3080/'
    extra_assets = ('dsh-local-snapshot.py',)
    # Local reuses the existing web profile, without seeding the VM's profile
    # or VM-specific OAuth helper. Other transaction tests are shared.
    test_login_uses_pinned_runtime_and_vm_store_without_restart = None

    def setUp(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        super().setUp()

    def asset(self, name):
        if name == self.app:
            return (VM / 'dsh-vm').read_text().replace(
                '("127.0.0.1", 3080)', '("127.0.0.1", ' + str(self.port) + ')')
        return (LOCAL / name).read_text()

    def test_install_start_status_url_and_exact_launcher(self):
        self.assertEqual(self.versions(), 'DSH_VERSION=0.2.2-rc.1\nNODE_VERSION=26.13.0\n')
        self.assertNotIn('?token=', self.call('status').stdout)
        self.assertNotIn('?token=', self.call('check').stdout)
        current = json.loads((self.home / 'service.json').read_text())['invocation']
        self.assertEqual(self.call('url').stdout.strip(), self.endpoint + '?token=' + current)
        self.call('install')
        result = subprocess.run([str(self.home / '.local/bin/dsh-local-runtime')], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = self.calls()[-1]
        self.assertEqual(launch['args'], ['exec', 'node@26.13.0', 'npm:@deepseek-ai/dsh@0.2.2-rc.1',
                                         '--', 'dsh', 'web', '--no-open', '--host', '127.0.0.1', '--port', '3080'])
        self.assertEqual(launch['DSH_HOME'], str(self.state))
        self.assertEqual(launch['MISE_AUTO_INSTALL'], 'false')
        self.assertEqual(launch['MISE_NOT_FOUND_AUTO_INSTALL'], 'false')
        for path in ['.local/share/mise/shims', '.local/bin']:
            self.assertIn(str(self.home / path), launch['PATH'].split(':'))
        self.assertIn('/usr/share/omarchy/bin', launch['PATH'].split(':'))
        self.assertNotIn('danger-full-access', json.dumps(launch))

    def test_update_rollback_preserves_complete_legacy_npx_graph(self):
        cache = self.home / '.npm/_npx/abc123/node_modules'
        (cache / 'pkg/node_modules/dep').mkdir(parents=True)
        (cache / 'pkg/node_modules/dep/version').write_text('nested-v1')
        (cache / 'native-optional').mkdir()
        (cache / 'native-optional/binary').write_bytes(b'native-payload')
        shared = self.state / 'profiles/node_modules'
        shared.mkdir(parents=True)
        (shared / 'pkg').symlink_to(cache / 'pkg', target_is_directory=True)
        (shared / 'dep').symlink_to(cache / 'pkg/node_modules/dep', target_is_directory=True)
        before = os.readlink(shared / 'pkg')
        self.call('update', '0.2.3')
        original_snapshot = self.snaps()[0]
        self.assertEqual(os.readlink(shared / 'pkg'), before)
        (self.state / 'nested/secret').write_text('after update')
        self.call('rollback', str(original_snapshot), '--yes')
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        restored = shared / 'pkg'
        self.assertFalse(Path(os.readlink(restored)).is_absolute())
        self.assertTrue(restored.resolve().is_relative_to(self.state))
        self.assertEqual((restored / 'node_modules/dep/version').read_text(), 'nested-v1')
        self.assertEqual((shared / 'dep/version').read_text(), 'nested-v1')
        embedded = self.state / '.dsh-local-package-cache/npx-abc123/node_modules'
        self.assertEqual((embedded / 'native-optional/binary').read_bytes(), b'native-payload')
        # Subsequent transactions must snapshot the now-internal graph too.
        self.call('update', '0.2.4')
        self.call('check')

    def test_reinstall_does_not_start_stop_or_touch_existing_state(self):
        self.state.chmod(0o751)
        before = {str(path.relative_to(self.state)): (path.lstat().st_mode, path.lstat().st_mtime_ns,
                  path.read_bytes() if path.is_file() and not path.is_symlink() else None)
                  for path in [self.state, *self.state.rglob('*')]}
        service = (self.home / 'service.json').read_bytes()
        count = len(self.calls())
        self.call('install')
        after = {str(path.relative_to(self.state)): (path.lstat().st_mode, path.lstat().st_mtime_ns,
                 path.read_bytes() if path.is_file() and not path.is_symlink() else None)
                 for path in [self.state, *self.state.rglob('*')]}
        self.assertEqual(after, before)
        self.assertEqual((self.home / 'service.json').read_bytes(), service)
        actions = [c['args'][1] for c in self.calls()[count:] if c['tool'] == 'systemctl']
        self.assertEqual(actions, ['daemon-reload', 'enable'])
        version_calls = [c for c in self.calls()[count:] if c['tool'] == 'mise' and '--version' in c['args']]
        self.assertNotEqual(version_calls[0]['DSH_HOME'], str(self.state))

    def test_first_install_is_nonstarting_and_preserves_existing_state(self):
        # Repeat the source-bundle install with a new HOME containing credentials.
        home = self.root / 'fresh-home'
        state = home / '.dsh'
        state.mkdir(parents=True, mode=0o751)
        (state / 'credentials').write_text('keep credentials')
        before = state.stat()
        env = dict(self.env, HOME=str(home))
        bundle = self.root / 'repository/dotfiles/dsh/local'
        bundle.mkdir(parents=True)
        for name in ['dsh-local', 'dsh-local-runtime', 'dsh-local.service', 'dsh-local-snapshot.py']:
            destination = bundle / name
            destination.write_text((LOCAL / name).read_text().replace('/usr/bin/mise', str(self.tools / 'mise')))
            destination.chmod(0o700)
        engine = self.root / 'repository/hosts/omarchy-vm/dsh/dsh-vm'
        engine.parent.mkdir(parents=True)
        engine.write_text(self.asset('dsh-local').replace('/usr/bin/mise', str(self.tools / 'mise')))
        result = subprocess.run([str(bundle / 'dsh-local'), 'install'], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((state / 'credentials').read_text(), 'keep credentials')
        self.assertEqual(state.stat().st_mode, before.st_mode)
        self.assertEqual(state.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse((home / 'service.json').exists())
        calls = [json.loads(line) for line in (home / 'calls.jsonl').read_text().splitlines()]
        self.assertEqual([c['args'][1] for c in calls if c['tool'] == 'systemctl'], ['daemon-reload', 'enable'])
        self.assertEqual((home / '.config/dsh-local/runtime.env').read_text(), self.versions())
        # Installed CLI embeds the engine rather than the repository bootstrap.
        self.assertEqual((home / '.local/bin/dsh-local').read_text(), engine.read_text())
        result = subprocess.run([str(home / '.local/bin/dsh-local'), 'status'], env=env,
                                cwd=home, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Local URL (no credential): ' + self.endpoint, result.stdout)

    def assert_rejected_without_cutover(self, *args):
        pins = self.versions()
        state = (self.state / 'nested/secret').read_bytes()
        snapshots = self.snaps()
        count = len(self.calls())
        result = self.call(*args, ok=False)
        self.assertEqual(self.versions(), pins)
        self.assertEqual((self.state / 'nested/secret').read_bytes(), state)
        self.assertEqual(self.snaps(), snapshots)
        self.assertFalse(any(c['tool'] == 'systemctl' and c['args'][1] in ['start', 'stop', 'restart']
                             for c in self.calls()[count:]))
        return result

    def test_competing_listener_blocks_start_update_and_rollback(self):
        self.call('update', '0.2.3')
        target = self.snaps()[0]
        service = self.home / 'service.json'
        data = json.loads(service.read_text())
        data['active'] = False
        service.write_text(json.dumps(data))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', self.port))
            listener.listen()
            for args in [('start',), ('update', '0.2.4'), ('rollback', target.name, '--yes')]:
                with self.subTest(args=args):
                    result = self.assert_rejected_without_cutover(*args)
                    self.assertIn('Competing listener', result.stderr)

    def test_listener_detected_after_stop_never_recovers_second_server(self):
        pins = self.versions()
        count = len(self.calls())
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', self.port))
            listener.listen()
            result = self.call('update', '0.2.3', ok=False)
        self.assertIn('Competing listener', result.stderr)
        self.assertEqual(self.versions(), pins)
        self.assertEqual(self.snaps(), [])
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        actions = [c['args'][1] for c in self.calls()[count:] if c['tool'] == 'systemctl']
        self.assertIn('stop', actions)
        self.assertNotIn('start', actions)
        self.assertNotIn('restart', actions)

    def test_manual_dsh_process_blocks_update_even_without_listener(self):
        # Bash exec -a provides a real DSH-shaped process before it opens state.
        process = subprocess.Popen(['/usr/bin/bash', '-c', 'exec -a dsh /usr/bin/sleep 60'], env=self.env)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        try:
            result = self.assert_rejected_without_cutover('update', '0.2.3')
            self.assertIn('Competing DSH process', result.stderr)
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_external_open_writer_blocks_update(self):
        # Our test process is external to the lifecycle and keeps a writable FD.
        with (self.state / 'nested/secret').open('a'):
            result = self.assert_rejected_without_cutover('update', '0.2.3')
        self.assertIn('External writer', result.stderr)

    def test_runtime_rejects_malformed_pins_before_mise(self):
        config = self.home / '.config/dsh-local/runtime.env'
        original = config.read_text()
        cases = ['DSH_VERSION=latest\nNODE_VERSION=26.13.0\n',
                 original + 'NODE_VERSION=26.13.0\n',
                 original + 'EXTRA=x\n',
                 'DSH_VERSION=0.2.3\n',
                 'DSH_VERSION=$(touch bad)\nNODE_VERSION=26.13.0\n',
                 original + 'EXTRA=bad']
        for value in cases:
            with self.subTest(value=value):
                config.write_text(value)
                count = len(self.calls())
                self.call('status', ok=False)
                result = subprocess.run([str(self.home / '.local/bin/dsh-local-runtime')], env=self.env,
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(self.calls()), count)
                self.assertFalse((self.home / 'bad').exists())


class Syntax(unittest.TestCase):
    def test_local_assets_and_standalone_bootstrap(self):
        ast.parse((LOCAL / 'dsh-local').read_text())
        ast.parse(Path(__file__).read_text())
        result = subprocess.run(['/usr/bin/bash', '-n', str(LOCAL / 'dsh-local-runtime')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = (LOCAL / 'dsh-local.service').read_text()
        self.assertIn('ExecStart=%h/.local/bin/dsh-local-runtime', unit)
        self.assertIn('KillMode=control-group', unit)
        self.assertNotIn('User=', unit)
        self.assertNotIn('danger-full-access', unit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
