#!/usr/bin/python3
"""Isolated HOME + mocked tools only; never starts the real service.
Run: python3 hosts/omarchy-vm/dsh/tests/test_lifecycle.py
"""
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

BUNDLE = Path(__file__).resolve().parents[1]
MOCK = r'''#!/usr/bin/python3
import json, os, pathlib, sys, uuid
p = pathlib.Path(os.environ['HOME'])
args = sys.argv[1:]
tool = pathlib.Path(sys.argv[0]).name
log = p / 'calls.jsonl'
with log.open('a') as out:
    out.write(json.dumps({'tool': tool, 'args': args,
                         'DSH_HOME': os.environ.get('DSH_HOME'),
                         'MISE_AUTO_INSTALL': os.environ.get('MISE_AUTO_INSTALL'),
                         'MISE_NOT_FOUND_AUTO_INSTALL': os.environ.get('MISE_NOT_FOUND_AUTO_INSTALL'),
                         'PATH': os.environ['PATH']}) + '\n')
f = p / 'service.json'
s = json.loads(f.read_text()) if f.exists() else {'active': False, 'invocation': 'a'*32, 'previous': 'b'*32}
def save():
    f.write_text(json.dumps(s))
def version():
    return dict(line.split('=', 1) for line in (p / '.config/dsh-vm/runtime.env').read_text().splitlines())['DSH_VERSION']
if tool == 'mise':
    if (p / 'fail-install').exists():
        sys.exit(17)
    print('0.2.2-rc.1')
elif tool == 'systemctl':
    action = args[1]
    if action == 'show':
        print('ActiveState=' + ('active' if s['active'] else 'inactive'))
        print('MainPID=' + ('4321' if s['active'] else '0'))
        print('InvocationID=' + s['invocation'])
    elif action == 'stop':
        s['active'] = False
        save()
    elif action == 'start':
        if not s['active']:
            s['previous'] = s['invocation']
            s['invocation'] = uuid.uuid4().hex
            s['active'] = True
        save()
        if version() == '9.0.0':
            (p / '.dsh/nested/secret').write_text('failed migration')
            s['active'] = False
            save()
            sys.exit(19)
        if version() == '9.0.1':
            (p / '.dsh/nested/secret').write_text('failed readiness migration')
    elif action not in ['enable', 'daemon-reload', 'reset-failed']:
        sys.exit(21)
elif tool == 'journalctl':
    def row(inv):
        return {'_SYSTEMD_INVOCATION_ID': inv,
                'MESSAGE': 'dsh web: https://personal-openclaw.tailf108.ts.net:8443/?token=' + inv}
    assert '--boot=0' in args and '_SYSTEMD_INVOCATION_ID=' + s['invocation'] in args
    print(json.dumps(row(s['previous'])))
    if not (p / 'stale-journal').exists():
        print(json.dumps(row(s['invocation'])))
elif tool == 'curl':
    from urllib.parse import urlsplit, parse_qs
    url = json.loads(sys.stdin.read().removeprefix('url = ').strip())
    assert not any('token=' in arg for arg in args)
    if '--cookie-jar' in args:
        jar = pathlib.Path(args[args.index('--cookie-jar') + 1])
        ok = parse_qs(urlsplit(url).query).get('token') == [s['invocation']]
        if ok:
            jar.write_text(s['invocation'])
        print('\n' + ('303' if ok else '401'), end='')
    elif '--cookie' not in args:
        print('\n401', end='')
    else:
        cookie = pathlib.Path(args[args.index('--cookie') + 1]).read_text()
        assert cookie == s['invocation'] and s['active']
        payload = json.loads(args[args.index('--data-binary') + 1])
        assert payload['method'] == 'agentPresets/list' and payload['payload'] == {'args': {}}
        if version() == '9.0.1' or (p / 'bad-api').exists():
            print('{"type":"server-response","result":{"ok":false}}\n200', end='')
        else:
            print(json.dumps({'type':'server-response', 'rpcId':payload['rpcId'],
                              'result': {'ok': True, 'value': {'presets': []}}}) + '\n200', end='')
        if (p / 'changing-invocation').exists():
            s['invocation'] = uuid.uuid4().hex
            save()
else:
    sys.exit(23)
'''


class Lifecycle(unittest.TestCase):
    app = 'dsh-vm'
    endpoint = 'https://personal-openclaw.tailf108.ts.net:8443/'

    def asset(self, name):
        return (BUNDLE / name).read_text()

    def setUp(self):
        # All test writes are inside the exclusive bundle scope, auto-cleaned.
        self.tmp = tempfile.TemporaryDirectory(prefix='.test-', dir=BUNDLE / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        for name in ['mise', 'systemctl', 'journalctl', 'curl']:
            path = self.tools / name
            path.write_text(MOCK.replace('dsh-vm', self.app).replace(
                'https://personal-openclaw.tailf108.ts.net:8443/', self.endpoint))
            path.chmod(0o700)
        self.source = self.root / 'bundle'
        self.source.mkdir()
        names = [self.app, self.app + '-runtime', self.app + '.service']
        names.extend(getattr(self, 'extra_assets', ()))
        if self.app == 'dsh-vm':
            names.append(self.app + '-login.mjs')
        for name in names:
            text = self.asset(name)
            text = text.replace('/usr/bin/mise', str(self.tools / 'mise'))
            text = text.replace('ready(wait=60)', 'ready(wait=0)')
            target = self.source / name
            target.write_text(text)
            target.chmod(0o700)
        self.env = {'HOME': str(self.home), 'PATH': str(self.tools) + ':/usr/bin:/bin', 'LC_ALL': 'C'}
        self.cli = self.source / self.app
        self.call('install')
        self.cli = self.home / '.local/bin' / self.app
        self.state = self.home / '.dsh'
        (self.state / 'nested').mkdir()
        (self.state / 'nested/secret').write_text('original secret')
        (self.state / 'empty').mkdir()
        (self.state / '.hidden').write_text('hidden data')
        (self.state / 'relative-link').symlink_to('nested/secret')
        executable = self.state / 'executable'
        executable.write_text('#!/bin/sh\n')
        executable.chmod(0o700)
        self.call('start')

    def call(self, *args, ok=True):
        result = subprocess.run([str(self.cli), *args], env=self.env, cwd=self.home,
                                capture_output=True, text=True, timeout=15)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def snaps(self):
        return sorted((self.home / '.local/state' / self.app / 'snapshots').iterdir())

    def versions(self):
        return (self.home / '.config' / self.app / 'runtime.env').read_text()

    def calls(self):
        return [json.loads(line) for line in (self.home / 'calls.jsonl').read_text().splitlines()]

    def test_login_uses_pinned_runtime_and_vm_store_without_restart(self):
        before = json.loads((self.home / 'service.json').read_text())
        for command, mode in [('login', 'login'), ('login-status', 'status')]:
            self.call(command)
            call = self.calls()[-1]
            self.assertEqual(call['tool'], 'mise')
            self.assertEqual(call['args'], ['exec', 'node@26.13.0',
                'npm:@deepseek-ai/dsh@0.2.2-rc.1', '--', 'node',
                str(self.home / '.local/bin/dsh-vm-login.mjs'), mode])
            self.assertEqual(call['DSH_HOME'], str(self.state))
        self.assertEqual(json.loads((self.home / 'service.json').read_text()), before)
        self.assertEqual((self.home / '.local/bin/dsh-vm-login.mjs').stat().st_mode & 0o777, 0o700)

    def test_install_start_status_url_and_exact_launcher(self):
        self.assertEqual(self.versions(), 'DSH_VERSION=0.2.2-rc.1\nNODE_VERSION=26.13.0\n')
        status = self.call('status').stdout
        self.assertNotIn('?token=', status)
        self.assertNotIn('?token=', self.call('check').stdout)
        current = json.loads((self.home / 'service.json').read_text())['invocation']
        self.assertEqual(self.call('url').stdout.strip(),
                         'https://personal-openclaw.tailf108.ts.net:8443/?token=' + current)
        result = subprocess.run([str(self.home / '.local/bin' / (self.app + '-runtime'))], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        launch = self.calls()[-1]
        self.assertEqual(launch['args'], ['exec', 'node@26.13.0', 'npm:@deepseek-ai/dsh@0.2.2-rc.1', '--',
                                         'dsh', '--profile', 'web', '--no-open', '--host', '127.0.0.1',
                                         '--port', '3080', '--public-url',
                                         'https://personal-openclaw.tailf108.ts.net:8443/',
                                         '--trusted-host', 'personal-openclaw.tailf108.ts.net:8443'])
        self.assertEqual(launch['DSH_HOME'], str(self.state))
        self.assertIn('/usr/bin', launch['PATH'])

    def test_update_snapshot_complete_private_and_rollback(self):
        self.call('update', '0.2.3', '26.14.0')
        self.assertIn('DSH_VERSION=0.2.3', self.versions())
        self.assertIn('NODE_VERSION=26.14.0', self.versions())
        snapshot = self.snaps()[0]
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o700)
        for path in snapshot.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with tarfile.open(snapshot / 'state.tar') as archive:
            self.assertEqual(archive.extractfile('state/nested/secret').read(), b'original secret')
            self.assertIn('state/.hidden', archive.getnames())
            self.assertIn('state/empty', archive.getnames())
        (self.state / 'nested/secret').write_text('new changes')
        result = self.call('rollback', str(snapshot), '--yes')
        self.assertIn('WARNING', result.stderr)
        self.assertEqual(len(self.snaps()), 2)
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        self.assertTrue((self.state / 'relative-link').is_symlink())
        self.assertEqual((self.state / 'executable').stat().st_mode & 0o777, 0o700)
        self.assertIn('0.2.2-rc.1', self.versions())
        preserved = list(self.home.glob('.' + self.app + '-preserved-*'))
        self.assertEqual((preserved[0] / 'state/nested/secret').read_text(), 'new changes')
        installs = [c['args'] for c in self.calls() if c['tool'] == 'mise']
        self.assertIn(['exec', 'node@26.14.0', '--', str(self.tools / 'mise'), 'install',
                       'npm:@deepseek-ai/dsh@0.2.3'], installs)

    def test_update_without_node_keeps_exact_node(self):
        self.call('update', '0.2.4')
        self.assertIn('NODE_VERSION=26.13.0', self.versions())
        self.call('install')
        self.assertIn('DSH_VERSION=0.2.4', self.versions())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')

    def test_preinstall_failure_leaves_service_state_and_config_untouched(self):
        before = (self.home / 'service.json').read_text()
        (self.home / 'fail-install').touch()
        self.call('update', '0.2.5', ok=False)
        self.assertEqual(self.snaps(), [])
        self.assertEqual((self.home / 'service.json').read_text(), before)
        self.assertIn('0.2.2-rc.1', self.versions())

    def test_snapshot_rejects_unrestorable_state_before_cutover(self):
        link = self.state / 'unsafe-link'
        for destination in [str(self.state / 'nested/secret'), '../outside']:
            with self.subTest(destination=destination):
                link.symlink_to(destination)
                result = self.call('update', '0.2.3', ok=False)
                self.assertIn('cannot create a restorable snapshot', result.stderr)
                self.assertIn('0.2.2-rc.1', self.versions())
                self.assertEqual(self.snaps(), [])
                self.assertTrue(link.is_symlink())
                self.call('check')
                link.unlink()
        special = self.state / 'named-pipe'
        os.mkfifo(special)
        self.call('update', '0.2.3', ok=False)
        self.assertEqual(self.snaps(), [])
        self.assertIn('0.2.2-rc.1', self.versions())
        self.call('check')

    def test_startup_failure_restores_and_preserves_failed_state(self):
        result = self.call('update', '9.0.0', ok=False)
        self.assertIn('Previous pinned runtime and complete state restored', result.stderr)
        self.assertIn('0.2.2-rc.1', self.versions())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        preserved = list(self.home.glob('.' + self.app + '-preserved-*'))
        self.assertEqual((preserved[0] / 'state/nested/secret').read_text(), 'failed migration')
        self.call('check')

    def test_authenticated_failure_also_recovers(self):
        self.call('update', '9.0.1', ok=False)
        self.assertIn('0.2.2-rc.1', self.versions())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        self.call('check')

    def test_rollback_failure_recovers_safety_snapshot(self):
        self.call('update', '0.2.5')
        target = self.snaps()[0]
        self.call('update', '0.2.6')
        original = (target / 'runtime.env').read_text()
        (target / 'runtime.env').write_text(original.replace('0.2.2-rc.1', '9.0.0'))
        metadata = json.loads((target / 'metadata.json').read_text())
        metadata['versions']['DSH_VERSION'] = '9.0.0'
        (target / 'metadata.json').write_text(json.dumps(metadata))
        (self.state / 'nested/secret').write_text('before rollback')
        self.call('rollback', target.name, '--yes', ok=False)
        self.assertIn('0.2.6', self.versions())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'before rollback')
        self.call('check')

    def test_reject_stale_journal_changing_invocation_and_bad_api(self):
        for marker in ['stale-journal', 'changing-invocation', 'bad-api']:
            with self.subTest(marker=marker):
                path = self.home / marker
                path.touch()
                self.call('check', ok=False)
                if marker == 'stale-journal':
                    self.call('url', ok=False)
                path.unlink()

    def test_rollback_requires_yes_valid_name_checksum_and_no_symlinks(self):
        self.call('update', '0.2.3')
        target = self.snaps()[0]
        for args in [('rollback', target.name),
                     ('rollback', '../' + target.name, '--yes'),
                     ('rollback', '/tmp/' + target.name, '--yes'),
                     ('rollback', str(target.parent) + '/../snapshots/' + target.name, '--yes')]:
            with self.subTest(args=args):
                self.call(*args, ok=False)
        (target / 'state.tar').write_bytes(b'broken')
        self.call('rollback', target.name, '--yes', ok=False)
        self.assertIn('0.2.3', self.versions())
        (target / 'state.tar').unlink()
        (target / 'state.tar').symlink_to(self.state / 'nested/secret')
        self.call('rollback', target.name, '--yes', ok=False)

    def test_reject_malicious_archive_without_deleting_current_state(self):
        import hashlib
        self.call('update', '0.2.3')
        target = self.snaps()[0]
        with tarfile.open(target / 'state.tar', 'w') as archive:
            member = tarfile.TarInfo('state/../../escape')
            member.size = 4
            archive.addfile(member, io.BytesIO(b'evil'))
        metadata = json.loads((target / 'metadata.json').read_text())
        metadata['sha256'] = hashlib.sha256((target / 'state.tar').read_bytes()).hexdigest()
        (target / 'metadata.json').write_text(json.dumps(metadata))
        self.call('rollback', target.name, '--yes', ok=False)
        self.assertFalse((self.home / 'escape').exists())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        self.assertIn('0.2.3', self.versions())

    def test_reject_archive_link_escaping_state_subtree(self):
        import hashlib
        self.call('update', '0.2.3')
        target = self.snaps()[0]
        with tarfile.open(target / 'state.tar', 'w') as archive:
            member = tarfile.TarInfo('state/link')
            member.type = tarfile.SYMTYPE
            member.linkname = '../escape'
            archive.addfile(member)
        metadata = json.loads((target / 'metadata.json').read_text())
        metadata['sha256'] = hashlib.sha256((target / 'state.tar').read_bytes()).hexdigest()
        (target / 'metadata.json').write_text(json.dumps(metadata))
        self.call('rollback', target.name, '--yes', ok=False)
        self.assertFalse((self.state / 'link').exists())
        self.assertEqual((self.state / 'nested/secret').read_text(), 'original secret')
        self.assertIn('0.2.3', self.versions())

    def test_lock_excludes_concurrent_updates(self):
        import fcntl
        with (self.home / '.local/state' / self.app / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.call('update', '0.2.3', ok=False)
        self.assertEqual(self.snaps(), [])

    def test_reject_version_aliases_and_environment_execution(self):
        for version in ['latest', '0.2', '1.0.0;touch bad', '../../1.0.0']:
            self.call('update', version, ok=False)
        self.call('update', '0.2.3', 'latest', ok=False)
        config = self.home / '.config' / self.app / 'runtime.env'
        config.write_text('DSH_VERSION=$(touch bad)\nNODE_VERSION=26.13.0\n')
        result = subprocess.run([str(self.home / '.local/bin' / (self.app + '-runtime'))], env=self.env,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / 'bad').exists())


class Syntax(unittest.TestCase):
    def test_syntax_and_unit_contract(self):
        ast.parse((BUNDLE / 'dsh-vm').read_text())
        ast.parse(Path(__file__).read_text())
        result = subprocess.run(['/usr/bin/bash', '-n', str(BUNDLE / 'dsh-vm-runtime')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        unit = (BUNDLE / 'dsh-vm.service').read_text()
        self.assertIn('ExecStart=%h/.local/bin/dsh-vm-runtime', unit)
        self.assertIn('KillMode=control-group', unit)
        self.assertNotIn('User=', unit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
