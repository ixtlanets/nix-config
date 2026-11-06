"""Portable contract regressions; mapped OS metadata is not privilege proof."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from test_owner_rutracker_refresh import (
    FixtureTerminal, FixtureTransport, owner,
)

BUNDLE = Path(__file__).resolve().parents[1]


def metadata(path):
    # Reading a cookie can update atime; publication must preserve these fields
    # on a failure before rename. Directory entry changes have separate checks.
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            stat.S_IMODE(info.st_mode), info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def private_preflight_body():
    """Extract one function, never source or execute the preflight entrypoint."""
    text = (BUNDLE / 'scripts/preflight.sh').read_text()
    matches = re.findall(r'^check_root_private_directory\(\) \{\n.*?^\}', text,
                         flags=re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise AssertionError('expected exactly one root-private function')
    return matches[0]


def gateway_cookies(path):
    """Actual gateway constructor/JSON loader; no server or upstream calls."""
    spec = importlib.util.spec_from_file_location(
        'root_private_gateway', BUNDLE / 'scripts/rutracker_gateway.py')
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    return gateway.GatewayConfig(
        flaresolverr_url='http://fixture.invalid/v1', listen_host='127.0.0.1',
        listen_port=0, max_body_bytes=1024, max_upstream_response_bytes=1024,
        max_timeout_ms=1000, timeout_seconds=1,
        session_cookies_file=str(path)).session_cookies


@contextlib.contextmanager
def local_owner_tree():
    """Map only root ownership to this test UID/GID; keep real mode/inode checks."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        base, secret = root / 'runtime', root / 'secrets'
        base.mkdir(mode=0o710)
        secret.mkdir(mode=0o700)
        native_directory = owner.Directory

        class LocalDirectory(native_directory):
            def __init__(self, path, uid, mode, anchor='/', gid=None):
                if uid != 0:
                    raise AssertionError('owner must request root directory ownership')
                super().__init__(path, os.getuid(), mode, anchor=temporary,
                                 gid=os.getgid() if gid == 0 else gid)

        events = []
        record = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        class Terminal(FixtureTerminal):
            closed = False

            def close(self):
                self.closed = True

        terminal = Terminal(events)
        with patch.object(owner, 'Directory', LocalDirectory), \
             patch.object(owner, 'SECRET_DIRECTORY', str(secret)), \
             patch.object(owner, '_runtime_directory',
                          lambda record: LocalDirectory(str(base), 0, 0o710)), \
             patch.object(owner, 'DockerTransport', lambda source: FixtureTransport(events)):
            yield root, secret, terminal, record, events


class RootPrivateOwnerTests(unittest.TestCase):
    def test_owner_gid_drift_is_refused_even_when_sudo_identity_matches(self):
        with self.assertRaises(owner.SafeError) as raised:
            owner.authorize(0, 0, 1000, 1001,
                            {'SUDO_USER': 'nik', 'SUDO_UID': '1000', 'SUDO_GID': '1001'})
        self.assertEqual(raised.exception.code, 'privacy')

    def test_owner_run_accepts_root_private_secrets_and_replaces_existing_cookie(self):
        with local_owner_tree() as (root, secret, terminal, record, events):
            final = secret / owner.COOKIE_NAME
            previous = b'{"bb_session":"synthetic-previous"}'
            final.write_bytes(previous)
            final.chmod(0o640)
            before = final.stat()
            owner._owner_run(terminal, record, b'synthetic-helper-boundary')
            self.assertEqual(json.loads(final.read_bytes()), {'bb_session': 'fixture-rotated'})
            self.assertNotEqual(owner._inode(before), owner._inode(final.stat()))
            self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o700)
            backups = list(secret.glob('.gateway-session-cookie.rollback-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), previous)
            self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
            self.assertEqual([p.name for p in (root / 'runtime').iterdir()], ['refresh.lock'])
            self.assertEqual(list(secret.glob('.gateway-session-cookie.stage-*')), [])
            self.assertTrue(terminal.closed)
            self.assertEqual(gateway_cookies(final), {'bb_session': 'fixture-rotated'})

    def test_secrets_directory_refuses_group_and_world_access_before_transport(self):
        for mode in (0o750, 0o710, 0o701, 0o770, 0o777, 0o740):
            with self.subTest(mode=oct(mode)), local_owner_tree() as (_, secret, terminal, record, events):
                secret.chmod(mode)
                with self.assertRaises(owner.SafeError) as raised:
                    owner._owner_run(terminal, record, b'synthetic')
                self.assertEqual(raised.exception.code, 'privacy')
                self.assertEqual(events, [])
                self.assertTrue(terminal.closed)
                self.assertEqual(list(secret.iterdir()), [])

    def test_secrets_directory_refuses_wrong_owner_or_group_before_transport(self):
        for field in (4, 5):
            with self.subTest(field=field), local_owner_tree() as (_, secret, terminal, record, events):
                identity = owner._inode(secret.stat())
                native_fstat = os.fstat

                def wrong_metadata(fd):
                    info = native_fstat(fd)
                    if owner._inode(info) == identity:
                        values = list(info)
                        values[field] += 1
                        return os.stat_result(values)
                    return info

                with patch.object(owner.os, 'fstat', side_effect=wrong_metadata), \
                     self.assertRaises(owner.SafeError) as raised:
                    owner._owner_run(terminal, record, b'synthetic')
                self.assertEqual(raised.exception.code, 'privacy')
                self.assertEqual(events, [])
                self.assertTrue(terminal.closed)

    def test_secrets_directory_symlink_is_refused_before_transport(self):
        with local_owner_tree() as (root, secret, terminal, record, events):
            secret.rename(root / 'actual')
            secret.symlink_to(root / 'actual', target_is_directory=True)
            with self.assertRaises(owner.SafeError) as raised:
                owner._owner_run(terminal, record, b'synthetic')
            self.assertEqual(raised.exception.code, 'privacy')
            self.assertEqual(events, [])
            self.assertTrue(terminal.closed)

    def test_replaced_secrets_inode_prevents_publication_and_cleans_stage(self):
        with local_owner_tree() as (root, secret, terminal, record, events):
            class ReplacingTransport(FixtureTransport):
                checks = 0

                def recheck(self):
                    super().recheck()
                    self.checks += 1
                    if self.checks == 3:
                        secret.rename(root / 'original')
                        secret.mkdir(mode=0o700)

            with patch.object(owner, 'DockerTransport', lambda source: ReplacingTransport(events)), \
                 self.assertRaises(owner.SafeError) as raised:
                owner._owner_run(terminal, record, b'synthetic')
            self.assertEqual(raised.exception.code, 'publication')
            self.assertEqual(list(secret.iterdir()), [])
            self.assertEqual(list((root / 'original').iterdir()), [])
            self.assertEqual([p.name for p in (root / 'runtime').iterdir()], ['refresh.lock'])
            self.assertTrue(terminal.closed)

    def test_replace_failures_preserve_cleanup_and_publication_unknown(self):
        for after in (False, True):
            with self.subTest(after=after), local_owner_tree() as (root, secret, terminal, record, events):
                final = secret / owner.COOKIE_NAME
                previous = b'{"bb_session":"synthetic-previous"}'
                final.write_bytes(previous)
                final.chmod(0o640)
                before = metadata(final)
                native_replace = os.replace

                def fail(*args, **kwargs):
                    if after:
                        native_replace(*args, **kwargs)
                    raise OSError('synthetic replacement failure')

                with patch.object(owner.os, 'replace', side_effect=fail), \
                     self.assertRaises(owner.SafeError) as raised:
                    owner._owner_run(terminal, record, b'synthetic')
                self.assertEqual(raised.exception.code, 'publication_unknown' if after else 'publication')
                self.assertEqual(json.loads(final.read_bytes()),
                                 {'bb_session': 'fixture-rotated' if after else 'synthetic-previous'})
                if not after:
                    self.assertEqual(metadata(final), before)
                self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o640)
                backups = list(secret.glob('.gateway-session-cookie.rollback-*'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), previous)
                self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
                self.assertEqual(list(secret.glob('.gateway-session-cookie.stage-*')), [])
                self.assertEqual([p.name for p in (root / 'runtime').iterdir()], ['refresh.lock'])
                self.assertTrue(terminal.closed)


class ProductionRootPrivateContractTests(unittest.TestCase):
    def test_exact_preflight_function_accepts_0700_and_refuses_0750_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            secret = Path(temporary) / 'secrets'
            secret.mkdir(mode=0o700)
            link = Path(temporary) / 'link'
            link.symlink_to(secret, target_is_directory=True)
            # Portable UID mapping only; real stat still supplies mode and type.
            # The separate privilege harness executes this body with no mapping.
            uid_mapping = ('stat() { if [[ $1 == -c && $2 == %u ]]; then '
                           'printf "0\\n"; else command stat "$@"; fi; }\n')
            for path, mode, expected in ((secret, 0o700, 'PASS'), (secret, 0o750, 'FAIL'),
                                         (link, 0o700, 'FAIL')):
                secret.chmod(mode)
                code = ('pass() { printf "PASS\\n"; }; fail() { printf "FAIL\\n"; };\n'
                        + uid_mapping + private_preflight_body()
                        + '\ncheck_root_private_directory ' + shlex.quote(str(path)))
                result = subprocess.run(['/bin/bash', '-c', code], capture_output=True,
                                        text=True, timeout=5,
                                        env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                                             'HOME': temporary, 'TMPDIR': temporary})
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, expected + '\n', ''))

    def test_um790pro_preflight_and_runbook_keep_root_private_install_contract(self):
        text = (BUNDLE / 'scripts/preflight.sh').read_text()
        branch = text.split('if [[ $host == um790pro ]]; then\n', 1)[1].split('\nelse\n', 1)[0]
        self.assertIn('secrets_root=${AUDIOBOOK_OPS_SECRETS_ROOT:-/etc/audiobook-ops/secrets}', branch)
        self.assertIn('  check_root_private_directory "$secrets_root"\n', branch)
        runbook = (BUNDLE / 'PRODUCTION-RUNBOOK.md').read_text()
        self.assertIn('sudo install -d -o root -g root -m 0700 /etc/audiobook-ops/secrets\n', runbook)
        self.assertIn('installed `root:nik` mode `0640`', runbook)

    def test_compose_gateway_keeps_service_identity_and_file_secret_mount(self):
        # Literal static contract; no YAML dependency or Compose execution.
        text = (BUNDLE / 'docker-compose.yml').read_text()
        service = text.split('\n  rutracker-gateway:\n', 1)[1].split('\n  prowlarr:\n', 1)[0]
        self.assertIn('    user: "1000:1000"\n', service)
        self.assertIn('RUTRACKER_GATEWAY_SESSION_COOKIES: /run/secrets/gateway_session_cookie\n', service)
        self.assertIn('    secrets:\n      - gateway_session_cookie\n', service)
        self.assertIn('root:1000, mode 0640', service)
        self.assertIn('\n  gateway_session_cookie:\n    file: ${AUDIOBOOK_OPS_SECRETS_ROOT:-/etc/audiobook-ops/secrets}/gateway-session-cookie\n', text)


if __name__ == '__main__':
    unittest.main()
