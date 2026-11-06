"""Separate, mandatory parent gate: real mapped root and service DAC, offline.

Not collected by unittest discovery. Requires a fresh user/PID namespace with
both 0 and 1000 mapped; never run as host root. No Docker or provider commands.
Only the runtime path and browser/TTY boundaries are synthetic. Directory,
Stage, lock, refresh, Publisher, preflight body and gateway loader are real.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_owner_root_private import metadata, private_preflight_body
from test_owner_rutracker_refresh import FixtureTerminal, FixtureTransport, owner

SCRATCH = Path('/home/nik/.hermes/cache/scratch')
BUNDLE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('privilege_gateway', BUNDLE / 'scripts/rutracker_gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


def require_namespace():
    for name in ('uid_map', 'gid_map'):
        rows = [tuple(map(int, row.split()))
                for row in Path('/proc/self/' + name).read_text().splitlines()]
        if (not rows or any(count > 65536 for _, _, count in rows)
                or not all(any(start <= identity < start + count for start, _, count in rows)
                           for identity in (0, 1000))):
            raise RuntimeError('SETUP: requires isolated two-identity user namespace')
    if os.geteuid() != 0 or os.getegid() != 0 or os.getpid() != 1:
        raise RuntimeError('SETUP: requires mapped root as private PID namespace init')
    if not Path(os.environ.get('TMPDIR', '')).is_relative_to(SCRATCH):
        raise RuntimeError('SETUP: TMPDIR must be under the owned scratch parent')
    if Path('/proc/self/setgroups').read_text().strip() != 'allow':
        raise RuntimeError('SETUP: mapping must allow clearing supplementary groups')
    try:
        os.setgroups([])
    except OSError:
        raise RuntimeError('SETUP: cannot clear supplementary groups') from None


def load_gateway(path):
    return gateway.GatewayConfig(
        flaresolverr_url='http://fixture.invalid/v1', listen_host='127.0.0.1',
        listen_port=0, max_body_bytes=1024, max_upstream_response_bytes=1024,
        max_timeout_ms=1000, timeout_seconds=1,
        session_cookies_file=str(path)).session_cookies


def service_read(secret, directory_fd, service_fd, expected, backup_fd=None):
    """An already-open file is the mount-equivalent, not a host directory grant."""
    pid = os.fork()
    if pid == 0:
        try:
            os.setgroups([])
            os.setgid(1000)
            os.setuid(1000)
            assert os.getresuid() == (1000,) * 3
            assert os.getresgid() == (1000,) * 3
            assert os.getgroups() == []
            assert 'CapEff:\t0000000000000000' in Path('/proc/self/status').read_text()
            for attempt in (lambda: os.open(secret, os.O_RDONLY),
                            lambda: os.open(owner.COOKIE_NAME, os.O_RDONLY, dir_fd=directory_fd)):
                try:
                    fd = attempt()
                except PermissionError:
                    pass
                else:
                    os.close(fd)
                    raise AssertionError('service traversed host private directory')
            info = os.fstat(service_fd)
            assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 1000, 0o640)
            assert load_gateway('/proc/self/fd/' + str(service_fd)) == expected
            # The fd-visible path still checks file permissions: root-only rollback
            # cannot be reopened by service UID/GID, even with an inherited fd.
            if backup_fd is not None:
                try:
                    fd = os.open('/proc/self/fd/' + str(backup_fd), os.O_RDONLY)
                except PermissionError:
                    pass
                else:
                    os.close(fd)
                    raise AssertionError('service reopened root-only rollback')
            os._exit(0)
        except BaseException:
            os._exit(1)
    assert os.waitpid(pid, 0)[1] == 0, 'unprivileged service proof failed'


def check_preflight(secret, temporary):
    link = Path(temporary) / 'secret-link'
    link.symlink_to(secret, target_is_directory=True)
    for path, mode, expected in ((secret, 0o700, 'PASS'), (secret, 0o750, 'FAIL'),
                                 (link, 0o700, 'FAIL')):
        secret.chmod(mode)
        result = subprocess.run(
            ['/bin/bash', '-c', 'pass() { echo PASS; }; fail() { echo FAIL; };\n'
             + private_preflight_body() + '\ncheck_root_private_directory "$1"',
             'synthetic-preflight', str(path)], capture_output=True, text=True,
            timeout=5, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                            'HOME': temporary, 'TMPDIR': str(SCRATCH)})
        assert (result.returncode, result.stdout, result.stderr) == (0, expected + '\n', '')
    link.unlink()


def scenario(failure):
    with tempfile.TemporaryDirectory(prefix='root-private-proof-', dir=SCRATCH) as temporary:
        root = Path(temporary)
        secret, runtime = root / 'secrets', root / 'runtime'
        secret.mkdir(mode=0o700)
        runtime.mkdir(mode=0o710)
        os.chown(runtime, 0, 1000)
        assert metadata(secret)[2:5] == (0, 0, 0o700)
        check_preflight(secret, temporary)
        final = secret / owner.COOKIE_NAME
        previous = b'{"bb_session":"synthetic-previous"}'
        final.write_bytes(previous)
        os.chown(final, 0, 1000)
        final.chmod(0o640)
        before, directory_before = metadata(final), metadata(secret)
        old_fd = os.open(final, os.O_RDONLY)
        directory_fd = os.open(secret, os.O_RDONLY | os.O_DIRECTORY)
        opened = []
        events = []

        class AnchoredDirectory(owner.Directory):
            def __init__(self, path, uid, mode, anchor='/', gid=None):
                super().__init__(path, uid, mode, anchor=temporary, gid=gid)

        class Terminal(FixtureTerminal):
            closed = False

            def close(self):
                self.closed = True

        terminal = Terminal(events)
        native_replace, native_fsync = os.replace, os.fsync
        observed_stage = []

        def replace(*args, **kwargs):
            if failure == 'before':
                raise OSError('synthetic before rename')
            result = native_replace(*args, **kwargs)
            if failure == 'after':
                raise OSError('synthetic after rename')
            return result

        def fsync(fd):
            for path in secret.glob('.gateway-session-cookie.stage-*'):
                assert metadata(path)[2:5] == (0, 0, 0o700)
                observed_stage.append(True)
            return native_fsync(fd)

        try:
            service_read(final, directory_fd, old_fd, {'bb_session': 'synthetic-previous'})
            owner.authorize(0, 0, 1000, 1000,
                            {'SUDO_USER': 'nik', 'SUDO_UID': '1000', 'SUDO_GID': '1000'})
            with patch.object(owner, 'Directory', AnchoredDirectory), \
                 patch.object(owner, 'SECRET_DIRECTORY', str(secret)), \
                 patch.object(owner, '_runtime_directory',
                              lambda record: AnchoredDirectory(str(runtime), 0, 0o710, gid=1000)), \
                 patch.object(owner, 'DockerTransport', lambda source: FixtureTransport(events)), \
                 patch.object(owner.os, 'replace', side_effect=replace), \
                 patch.object(owner.os, 'fsync', side_effect=fsync):
                code = 'success'
                try:
                    owner._owner_run(terminal, types.SimpleNamespace(pw_uid=1000, pw_gid=1000), b'synthetic')
                except owner.SafeError as error:
                    code = error.code
            assert code == {'none': 'success', 'before': 'publication', 'after': 'publication_unknown'}[failure]
            assert terminal.closed and observed_stage
            assert metadata(secret)[:5] == directory_before[:5]
            assert metadata(final)[2:6] == (0, 1000, 0o640, 1)
            assert list(secret.glob('.gateway-session-cookie.stage-*')) == []
            assert [p.name for p in runtime.iterdir()] == ['refresh.lock']
            backups = list(secret.glob('.gateway-session-cookie.rollback-*'))
            assert len(backups) == 1 and backups[0].read_bytes() == previous
            assert metadata(backups[0])[2:6] == (0, 0, 0o600, 1)
            backup_fd = os.open(backups[0], os.O_RDONLY)
            opened.append(backup_fd)
            # Old file mount / open-fd view remains on old inode after replacement.
            service_read(final, directory_fd, old_fd, {'bb_session': 'synthetic-previous'}, backup_fd)
            if failure == 'before':
                assert metadata(final) == before and final.read_bytes() == previous
            else:
                assert metadata(final)[:2] != before[:2]
                assert load_gateway(final) == {'bb_session': 'fixture-rotated'}
                service_fd = os.open(final, os.O_RDONLY)
                opened.append(service_fd)
                service_read(final, directory_fd, service_fd, {'bb_session': 'fixture-rotated'}, backup_fd)
            # Verify operation released lock, using the real validator and flock.
            base = AnchoredDirectory(str(runtime), 0, 0o710, gid=1000)
            try:
                lock = owner._RefreshLock(base)
                lock.close()
            finally:
                base.close()
        finally:
            for fd in (*opened, old_fd, directory_fd):
                os.close(fd)
    print('PASS real namespace DAC/publication/preflight/gateway: ' + failure, flush=True)


if __name__ == '__main__':
    require_namespace()
    for failure in ('none', 'before', 'after'):
        scenario(failure)
    print(json.dumps({'privilege_gate': 'PASS', 'scenarios': 3}), flush=True)
