"""Synthetic owner-boundary tests; no Docker or real credentials."""
import importlib.util
import io
import base64
import struct
import tempfile
import json
import stat
import select
import time
import termios
import fcntl
import hashlib
import types
import signal
import threading
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/owner_rutracker_refresh.py'
spec = importlib.util.spec_from_file_location('owner_refresh', SCRIPT)
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)


def valid_inspect():
    return {'Name': '/audiobook-ops-flaresolverr', 'Id': 'a' * 64,
                 'Image': owner.EXPECTED_IMAGE,
                 'HostConfig': {'Privileged': False, 'CapAdd': None, 'CapDrop': None, 'SecurityOpt': None, 'UsernsMode': '', 'NetworkMode': 'audiobook-ops-backend', 'PidMode': ''},
                 'Mounts': [{'Type': 'bind', 'Destination': '/config', 'Source': '/home/nik/services/readmeabook/flaresolverr', 'Mode': 'rw', 'RW': True, 'Propagation': 'rprivate'}],
                 'NetworkSettings': {'Networks': {'audiobook-ops-backend': {'NetworkID': 'b' * 64, 'EndpointID': 'c' * 64, 'Aliases': ['audiobook-ops-flaresolverr', 'flaresolverr'], 'Gateway': '172.19.0.1', 'IPAddress': '172.19.0.2', 'IPPrefixLen': 16, 'GlobalIPv6Address': '', 'GlobalIPv6PrefixLen': 0}}},
                 'Config': dict(owner.EXPECTED_CONFIG),
                 'State': {'Running': True, 'Paused': False, 'Restarting': False,
                           'Dead': False, 'StartedAt': '2026-11-04T00:00:00Z', 'Pid': 123}}


def valid_image_inspect():
    """Synthetic classic-store proof from an exact pinned-reference lookup."""
    return {'Id': owner.EXPECTED_IMAGE, 'RepoDigests': [owner.EXPECTED_REFERENCE],
            'Descriptor': None, 'Os': 'linux', 'Architecture': 'amd64'}


def run_pty(code, answer=None, trigger_signal=None, assert_restore=False):
    master, slave = os.openpty()
    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    process = subprocess.Popen([sys.executable, '-I', '-c', code], stdin=slave,
                               stdout=slave, stderr=slave, close_fds=True,
                               preexec_fn=controlling_terminal,
                               env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TMPDIR': os.environ['TMPDIR']})
    os.close(slave)
    captured = bytearray()
    sent = False
    limit = time.monotonic() + 5
    try:
        while time.monotonic() < limit:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                captured.extend(chunk)
                if not sent and b'Password: ' in captured:
                    if trigger_signal is not None:
                        os.kill(process.pid, trigger_signal)
                        sent = True
                    elif answer is not None:
                        os.write(master, answer)
                        sent = True
            elif process.poll() is not None:
                break
        returncode = process.wait(timeout=1)
        if assert_restore and not termios.tcgetattr(master)[3] & termios.ECHO:
            raise AssertionError('TTY ECHO was not restored')
        return returncode, bytes(captured)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)
        os.close(master)


class OwnerGateTests(unittest.TestCase):
    def test_main_never_exposes_exception_or_hostile_diagnostic_contents(self):
        for exception in ["RuntimeError('SYNTHETIC_SECRET https://fixture.invalid/private')",
                          "m.SafeError(['SYNTHETIC_SECRET https://fixture.invalid/private'])"]:
            with self.subTest(exception=exception):
                code = ("import importlib.util,os,types; "
                        f"s=importlib.util.spec_from_file_location('owner',{str(SCRIPT)!r}); "
                        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                        "m.os.getuid=lambda:0;m.os.geteuid=lambda:0; "
                        "m.pwd.getpwnam=lambda n:types.SimpleNamespace(pw_uid=1000,pw_gid=1000); "
                        "os.environ.update(SUDO_USER='nik',SUDO_UID='1000',SUDO_GID='1000'); "
                        "m.INSTALLED_LAUNCHER=m.__file__;m._installed_helper=lambda:b'reviewed-fixture'; "
                        f"m._owner_run=lambda *args:(_ for _ in ()).throw({exception}); "
                        "raise SystemExit(m.main())")
                rc, output = run_pty(code)
                self.assertEqual(rc, 1, output)
                self.assertEqual(output, b'owner-refresh: privacy\r\n')
                self.assertNotIn(b'SYNTHETIC_SECRET', output)

    def test_whole_cli_deadline_reports_only_fixed_timeout(self):
        code = ("import importlib.util,os,types,time; "
                f"s=importlib.util.spec_from_file_location('owner',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "m.os.getuid=lambda:0;m.os.geteuid=lambda:0; "
                "m.pwd.getpwnam=lambda n:types.SimpleNamespace(pw_uid=1000,pw_gid=1000); "
                "os.environ.update(SUDO_USER='nik',SUDO_UID='1000',SUDO_GID='1000'); "
                "m.INSTALLED_LAUNCHER=m.__file__;m._installed_helper=lambda:b'reviewed-fixture'; "
                "m.MAX_RUNTIME_SECONDS=1;m._owner_run=lambda *args:time.sleep(2); "
                "raise SystemExit(m.main())")
        rc, output = run_pty(code)
        self.assertEqual(rc, 1, output)
        self.assertEqual(output, b'owner-refresh: timeout\r\n')

    def test_signals_abort_private_input_with_fixed_output_and_restore_tty(self):
        code = ("import importlib.util,os,types; "
                f"s=importlib.util.spec_from_file_location('owner',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "m.os.getuid=lambda:0;m.os.geteuid=lambda:0; "
                "m.pwd.getpwnam=lambda n:types.SimpleNamespace(pw_uid=1000,pw_gid=1000); "
                "os.environ.update(SUDO_USER='nik',SUDO_UID='1000',SUDO_GID='1000'); "
                "m.INSTALLED_LAUNCHER=m.__file__;m._installed_helper=lambda:b'reviewed-fixture'; "
                "m._owner_run=lambda terminal,record,source: terminal.read_secret('Password: '); "
                "raise SystemExit(m.main())")
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=signum):
                rc, output = run_pty(code, trigger_signal=signum, assert_restore=True)
                self.assertEqual(rc, 1, output)
                self.assertEqual(output, b'Password: \r\nowner-refresh: privacy\r\n')

    def test_main_positive_under_real_pty_uses_trusted_synthetic_os_and_install_boundaries(self):
        code = ("import importlib.util,os,types; "
                f"s=importlib.util.spec_from_file_location('owner',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "m.os.getuid=lambda:0;m.os.geteuid=lambda:0; "
                "m.pwd.getpwnam=lambda n:types.SimpleNamespace(pw_uid=1000,pw_gid=1000); "
                "os.environ.update(SUDO_USER='nik',SUDO_UID='1000',SUDO_GID='1000',SYNTHETIC_SECRET='discard'); "
                "m.INSTALLED_LAUNCHER=m.__file__;m._installed_helper=lambda:b'reviewed-fixture'; "
                "m._owner_run=lambda terminal,record,source: "
                "os.write(1,b'OPERATION:'+str(source==b'reviewed-fixture' and 'SYNTHETIC_SECRET' not in os.environ).encode()+b'\\n'); "
                "raise SystemExit(m.main())")
        rc, output = run_pty(code)
        self.assertEqual(rc, 0, output)
        self.assertIn(b'OPERATION:True', output)
        self.assertIn(b'owner-refresh: installed; reload pending', output)
        self.assertNotIn(b'discard', output)

    def test_actual_cli_with_controlling_terminal_still_denies_uninstalled_owner(self):
        code = f"import runpy; runpy.run_path({str(SCRIPT)!r},run_name='__main__')"
        rc, output = run_pty(code)
        self.assertEqual(rc, 1)
        self.assertEqual(output, b'owner-refresh: privacy\r\n')

    def test_real_controlling_terminal_reads_password_without_echo(self):
        code = ("import importlib.util; "
                f"s=importlib.util.spec_from_file_location('owner',{str(SCRIPT)!r}); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "t=m.OwnerTerminal(); "
                "a=t.read_secret('Password: '); "
                "t.close(); print('DONE:'+str(a=='synthetic-password'))")
        rc, output = run_pty(code, b'synthetic-password\n')
        self.assertEqual(rc, 0)
        self.assertIn(b'Password: ', output)
        self.assertIn(b'DONE:True', output)
        self.assertNotIn(b'synthetic-password', output)

    def test_only_privileged_fixed_owner_can_authorize(self):
        valid = {'SUDO_USER': 'nik', 'SUDO_UID': '1000', 'SUDO_GID': '1000'}
        owner.authorize(0, 0, 1000, 1000, valid)
        for euid, uid, invoking in [(1000, 1000, valid), (0, 0, {}),
                                    (0, 0, dict(valid, SUDO_UID='1001')),
                                    (0, 0, dict(valid, SUDO_USER='other'))]:
            with self.subTest(euid=euid, uid=uid, invoking=invoking):
                with self.assertRaises(owner.SafeError) as raised:
                    owner.authorize(euid, uid, 1000, 1000, invoking)
                self.assertEqual(raised.exception.code, 'privacy')

    def test_cli_rejects_captured_terminal_before_transport(self):
        result = subprocess.run([sys.executable, '-I', str(SCRIPT)],
                                input=b'', capture_output=True,
                                env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'TMPDIR': os.environ['TMPDIR'],
                                     'SYNTHETIC_SECRET': 'NEVER_INHERIT'}, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'owner-refresh: privacy\n')


class IdentityTests(unittest.TestCase):
    def test_overlay_changes_allow_state_but_refuse_modified_executable_inputs(self):
        owner.validate_overlay_changes(b'C /app\nC /tmp\nA /tmp/browser-state\nC /app/chromedriver\nA /app/__pycache__/utils.cpython-311.pyc\n')
        for data in [b'C /usr/local/bin/python3\n', b'A /usr/local/lib/python3.11/site-packages/evil.pyc\n',
                     b'C /app/utils.py\n', b'A /app/new_module.py\n', b'D /app\n',
                     b'C /etc/ld.so.preload\n', b'C /tmp/../usr/bin/python3\n',
                     b'C /var/unknown\n', b'malformed', b'C /app\x00x\n']:
            with self.subTest(data=data):
                with self.assertRaises(owner.SafeError) as raised:
                    owner.validate_overlay_changes(data)
                self.assertEqual(raised.exception.code, 'identity')

    def test_only_exact_running_image_and_no_proxy_configuration_is_accepted(self):
        valid = valid_inspect()
        self.assertEqual(owner.inspect_identity(valid)[:4],
                         ('a' * 64, owner.EXPECTED_IMAGE, '2026-11-04T00:00:00Z', 123))
        for invalid in [dict(valid, Name='/other'), dict(valid, Id='bad'),
                        dict(valid, Image='sha256:' + 'b' * 64),
                        dict(valid, State=dict(valid['State'], Running=False)),
                        dict(valid, State=dict(valid['State'], Paused=True)),
                        dict(valid, Config=dict(valid['Config'], Image='tag:latest')),
                        dict(valid, Config=dict(valid['Config'], Env=['HTTP_PROXY=synthetic'])),
                        dict(valid, Config=dict(valid['Config'], Env=['chrome_args=synthetic'])),
                        dict(valid, Config=dict(valid['Config'], User='root')),
                        dict(valid, State=dict(valid['State'], Running='yes')),
                        dict(valid, HostConfig=dict(valid['HostConfig'], Privileged=True)),
                        dict(valid, HostConfig=dict(valid['HostConfig'], CapDrop=['KILL'])),
                        dict(valid, HostConfig=dict(valid['HostConfig'], CapAdd=['SYS_ADMIN'])),
                        dict(valid, HostConfig=dict(valid['HostConfig'], UsernsMode='host')),
                        dict(valid, Mounts=[{'Type': 'bind', 'Destination': '/app'}]),
                        dict(valid, Mounts=[{'Type': 'bind', 'Destination': '/usr/local'}]),
                        dict(valid, Config=dict(valid['Config'], Cmd=['/bin/sh'])),
                        dict(valid, Config=dict(valid['Config'], Env=valid['Config']['Env'] + ['LD_PRELOAD=synthetic'])),
                        dict(valid, Config=dict(valid['Config'], Env=valid['Config']['Env'] + ['PYTHONPATH=synthetic']))]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(owner.SafeError) as raised:
                    owner.inspect_identity(invalid)
                self.assertEqual(raised.exception.code, 'identity')

    def test_namespace_and_retained_mount_drift_refused(self):
        valid = valid_inspect()
        self.assertEqual(owner.inspect_identity(valid)[:4],
                         ('a' * 64, owner.EXPECTED_IMAGE, '2026-11-04T00:00:00Z', 123))
        import copy
        for key, values in [('NetworkMode', ['host', 'bridge', 'container:' + 'd' * 64, 'none']),
                            ('PidMode', ['host', 'container:' + 'd' * 64])]:
            for value in values:
                bad = copy.deepcopy(valid); bad['HostConfig'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(owner.SafeError):
                    owner.inspect_identity(bad)
        for key, value in [('Source', '/arbitrary'), ('Propagation', 'rshared'), ('RW', False)]:
            bad = copy.deepcopy(valid); bad['Mounts'][0][key] = value
            with self.subTest(key=key), self.assertRaises(owner.SafeError): owner.inspect_identity(bad)
        bad = copy.deepcopy(valid)
        bad['NetworkSettings']['Networks']['other'] = bad['NetworkSettings']['Networks'].pop('audiobook-ops-backend')
        with self.assertRaises(owner.SafeError): owner.inspect_identity(bad)

    def test_actual_host_namespace_sharing_is_refused_before_bootstrap(self):
        def namespace_stat(path):
            kind = str(path).rsplit('/', 1)[-1]
            # Candidate shares the host net namespace despite claimed inspect config.
            return types.SimpleNamespace(st_dev=4, st_ino=10 if kind == 'net' else (20 if '/123/' in str(path) else 21))
        with patch.object(owner.os, 'stat', side_effect=namespace_stat):
            transport = owner.DockerTransport(b'fixture', runner=lambda argv, **k: types.SimpleNamespace(returncode=0, stdout=json.dumps(valid_image_inspect() if 'image' in argv else valid_inspect()).encode()))
            with patch.object(owner, 'validate_overlay_changes'), self.assertRaises(owner.SafeError):
                transport._inspect()
        def private_stat(path):
            return types.SimpleNamespace(st_dev=4, st_ino=(10 if '/self/' in str(path) else 11) + (100 if str(path).endswith('/pid') else 0))
        with patch.object(owner.os, 'stat', side_effect=private_stat):
            self.assertEqual(owner.namespace_identity(123), ((4, 11), (4, 111)))
        with self.assertRaises(owner.SafeError): owner.namespace_identity(os.getpid())

    def test_named_network_must_actually_be_local_bridge(self):
        def runner(argv, **kwargs):
            value = (valid_image_inspect() if 'image' in argv else
                     {'Name':'audiobook-ops-backend','Id':'b'*64,'Driver':'macvlan','Scope':'local','Internal':False,'Ingress':False,'ConfigOnly':False}
                     if 'network' in argv else valid_inspect())
            return types.SimpleNamespace(returncode=0,stdout=json.dumps(value).encode())
        transport=owner.DockerTransport(b'fixture',runner=runner)
        with patch.object(owner,'namespace_identity',return_value=((4,11),(4,12))),patch.object(owner,'validate_overlay_changes'),self.assertRaises(owner.SafeError):
            transport._inspect()


class DockerTransportTests(unittest.TestCase):
    def test_shipped_companion_source_matches_exact_bootstrap_pin(self):
        helper = SCRIPT.with_name('owner_rutracker_helper.py').read_bytes()
        self.assertRegex(owner.HELPER_SHA256, r'^[0-9a-f]{64}$')
        self.assertEqual(hashlib.sha256(helper).hexdigest(), owner.HELPER_SHA256)
        self.assertEqual(len(helper), owner.HELPER_LENGTH)

    def test_private_pipe_write_deadline_does_not_block_on_a_stalled_reader(self):
        read_fd, write_fd = os.pipe()
        fcntl.fcntl(write_fd, fcntl.F_SETPIPE_SZ, 4096)
        def drain_later():
            time.sleep(0.5)
            while os.read(read_fd, 65536):
                pass
        reader = threading.Thread(target=drain_later)
        reader.start()
        started = time.monotonic()
        try:
            stream = owner._TimedPipe(write_fd, started + 0.05)
            with self.assertRaises(owner.SafeError) as raised:
                stream.write(b'x' * 1048576)
            elapsed = time.monotonic() - started
            self.assertEqual(raised.exception.code, 'timeout')
            self.assertLess(elapsed, 0.25)
        finally:
            os.close(write_fd)
            reader.join(timeout=2)
            os.close(read_fd)
        self.assertFalse(reader.is_alive())

    def test_fixed_transport_clears_environment_and_uses_only_inspected_container_id(self):
        fixture_source = b'# fixture-source-only\n'
        fixture_identity = valid_inspect()
        commands = []
        def runner(argv, **kwargs):
            commands.append(tuple(argv))
            output = ('C /app\nA /tmp/fixture-state\n' if 'diff' in argv else json.dumps(valid_image_inspect()) if 'image' in argv else json.dumps({'Name':'audiobook-ops-backend','Id':'b'*64,'Driver':'bridge','Scope':'local','Internal':False,'Ingress':False,'ConfigOnly':False}) if 'network' in argv else json.dumps(fixture_identity))
            code = ("import os,sys; assert 'SYNTHETIC_SECRET' not in os.environ; "
                    f"sys.stdout.write({output!r})")
            kwargs['env'] = dict(kwargs['env'], TMPDIR=os.environ['TMPDIR'])
            return subprocess.run([sys.executable, '-I', '-c', code], **kwargs)
        child = ("import sys,os,struct,json; assert 'SYNTHETIC_SECRET' not in os.environ; "
                 f"assert sys.stdin.buffer.read({len(fixture_source)}) == {fixture_source!r}; "
                 "v=json.dumps({'kind':'captcha','png':'fixture','cap_required':True}).encode(); "
                 "sys.stdout.buffer.write(struct.pack('!I',len(v))+v); sys.stdout.buffer.flush(); "
                 "n=struct.unpack('!I',sys.stdin.buffer.read(4))[0]; "
                 "v=json.loads(sys.stdin.buffer.read(n)); assert v['password']=='synthetic-password'; "
                 "v=b'{\"kind\":\"verified\",\"cookies\":{\"bb_session\":\"fixture\"}}'; "
                 "sys.stdout.buffer.write(struct.pack('!I',len(v))+v); sys.stdout.buffer.flush()")
        def factory(argv, **kwargs):
            commands.append(tuple(argv))
            kwargs['env'] = dict(kwargs['env'], TMPDIR=os.environ['TMPDIR'])
            return subprocess.Popen([sys.executable, '-I', '-c', child], **kwargs)
        with patch.dict(os.environ, {'SYNTHETIC_SECRET': 'never-inherit'}), \
             patch.object(owner, 'HELPER_SHA256', hashlib.sha256(fixture_source).hexdigest()), \
             patch.object(owner, 'HELPER_LENGTH', len(fixture_source)), \
             patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
            transport = owner.DockerTransport(fixture_source, runner=runner, process_factory=factory)
            try:
                transport.start()
                self.assertEqual(transport.identity[:4],
                                 ('a' * 64, owner.EXPECTED_IMAGE, '2026-11-04T00:00:00Z', 123))
                self.assertEqual(transport.receive()['kind'], 'captcha')
                transport.send({'kind': 'login', 'password': 'synthetic-password'})
                self.assertEqual(transport.receive()['kind'], 'verified')
                transport.finish()
                transport.recheck()
                self.assertEqual(commands[0][:3], owner.DOCKER)
                execution = next(command for command in commands if 'exec' in command)
                self.assertEqual(execution[:3], owner.DOCKER)
                self.assertIn('a' * 64, execution)
                self.assertNotIn(owner.CONTAINER, execution)
                self.assertIn('/usr/bin/env', execution)
                self.assertIn('-i', execution)
                self.assertIn('0:0', execution)
                self.assertNotIn('synthetic-password', repr(commands))
                self.assertEqual(sum('diff' in command for command in commands), 2)
                self.assertEqual(sum('image' in command for command in commands), 2)
            finally:
                transport.abort()


class ProtocolTests(unittest.TestCase):
    def test_private_frames_preserve_boundaries_and_reject_malformed_data(self):
        pipe = io.BytesIO()
        owner.write_frame(pipe, {'kind': 'login', 'password': 'synthetic'})
        owner.write_frame(pipe, {'kind': 'verified', 'cookies': {'bb_session': 's'}})
        self.assertEqual(pipe.getvalue()[:1], b'\x00')
        pipe.seek(0)
        self.assertEqual(owner.read_frame(pipe), {'kind': 'login', 'password': 'synthetic'})
        self.assertEqual(owner.read_frame(pipe),
                         {'kind': 'verified', 'cookies': {'bb_session': 's'}})
        invalid = [b'', b'\x00', struct.pack('!I', owner.MAX_FRAME + 1),
                   struct.pack('!I', 4) + b'{}',
                   struct.pack('!I', 2) + b'[]',
                   struct.pack('!I', 13) + b'{"a":1,"a":2}',
                   struct.pack('!I', 3) + b'NaN']
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(owner.SafeError) as raised:
                    owner.read_frame(io.BytesIO(raw))
                self.assertEqual(raised.exception.code, 'protocol')
        with self.assertRaises(owner.SafeError):
            owner.write_frame(io.BytesIO(), {'a': 'x' * owner.MAX_FRAME})


class DirectoryTests(unittest.TestCase):
    def test_installed_helper_is_read_from_reviewed_same_directory_with_pinned_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / 'install'
            private.mkdir(mode=0o700)
            host_script = private / 'owner_rutracker_refresh.py'
            helper_script = private / 'owner_rutracker_helper.py'
            host_script.write_bytes(b'# synthetic host source')
            helper_script.write_bytes(b'# reviewed synthetic helper')
            host_script.chmod(0o700)
            helper_script.chmod(0o700)
            native_directory = owner.Directory
            def directory(path, uid, mode):
                return native_directory(path, os.getuid(), mode, anchor=temporary)
            with patch.object(owner, 'INSTALLED_DIRECTORY', str(private)), \
                 patch.object(owner, 'INSTALLED_LAUNCHER', str(host_script)), \
                 patch.object(owner, '__file__', str(host_script)), \
                 patch.object(owner, 'Directory', side_effect=directory), \
                 patch.object(owner, 'HELPER_SHA256', hashlib.sha256(helper_script.read_bytes()).hexdigest()), \
                 patch.object(owner, 'HELPER_LENGTH', len(helper_script.read_bytes())):
                self.assertEqual(owner._installed_helper(), b'# reviewed synthetic helper')
                helper_script.write_bytes(b'# tampered synthetic helper')
                with self.assertRaises(owner.SafeError) as raised:
                    owner._installed_helper()
                self.assertEqual(raised.exception.code, 'identity')

    def test_installed_code_requires_single_link_owner_only_regular_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / 'install'
            private.mkdir(mode=0o700)
            script = private / 'helper.py'
            script.write_bytes(b'# synthetic reviewed source')
            script.chmod(0o700)
            directory = owner.Directory(str(private), os.getuid(), 0o700, anchor=temporary)
            try:
                self.assertEqual(owner.read_private_script(directory, 'helper.py', os.getuid()),
                                 b'# synthetic reviewed source')
                script.chmod(0o720)
                with self.assertRaises(owner.SafeError):
                    owner.read_private_script(directory, 'helper.py', os.getuid())
                script.chmod(0o700)
                os.link(script, private / 'hardlink.py')
                with self.assertRaises(owner.SafeError):
                    owner.read_private_script(directory, 'helper.py', os.getuid())
                (private / 'hardlink.py').unlink()
                (private / 'link.py').symlink_to(script)
                with self.assertRaises(owner.SafeError):
                    owner.read_private_script(directory, 'link.py', os.getuid())
            finally:
                directory.close()

    def test_private_directory_refuses_symlink_and_writable_ancestors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            safe = root / 'safe'
            safe.mkdir(mode=0o700)
            target = safe / 'secrets'
            target.mkdir(mode=0o750)
            opened = owner.Directory(str(target), os.getuid(), 0o750, anchor=temporary)
            opened.recheck()
            opened.close()
            link = root / 'link'
            link.symlink_to(safe, target_is_directory=True)
            for path in [link / 'secrets', safe / '..' / 'safe' / 'secrets']:
                with self.subTest(path=str(path)):
                    with self.assertRaises(owner.SafeError):
                        owner.Directory(str(path), os.getuid(), 0o750, anchor=temporary)
            safe.chmod(0o770)
            with self.assertRaises(owner.SafeError):
                owner.Directory(str(target), os.getuid(), 0o750, anchor=temporary)


class DocumentedInstallTests(unittest.TestCase):
    def test_literal_install_modes_pass_actual_file_and_directory_validators(self):
        import shlex
        doc = SCRIPT.parents[1] / 'OWNER-RUTRACKER-SESSION.md'
        commands = [shlex.split(line) for line in doc.read_text().splitlines()
                    if line.startswith('/usr/bin/sudo /usr/bin/install')]
        self.assertEqual(len(commands), 3)
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / 'install'
            install.mkdir(mode=int(commands[0][commands[0].index('-m') + 1], 8))
            for command in commands[1:]:
                target = install / Path(command[-1]).name
                target.write_bytes(Path(command[-2]).read_bytes())
                target.chmod(int(command[command.index('-m') + 1], 8))
            directory = owner.Directory(str(install), os.getuid(), 0o700, anchor=temporary)
            try:
                for name in ('owner_rutracker_helper.py', 'owner_rutracker_refresh.py'):
                    self.assertEqual(owner.read_private_script(directory, name, os.getuid()), (install / name).read_bytes())
            finally: directory.close()


class PublicationTests(unittest.TestCase):
    def test_unpublished_cookie_is_inside_root_private_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'secrets'
            target.mkdir(mode=0o750)
            directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
            native_fsync = os.fsync
            observed = []
            def inspect(fd):
                stages = list(target.glob('.gateway-session-cookie.stage-*'))
                if stages:
                    observed.append((stages[0].is_dir(), stat.S_IMODE(stages[0].stat().st_mode)))
                native_fsync(fd)
            try:
                with patch.object(owner.os, 'fsync', side_effect=inspect):
                    owner.Publisher(directory, os.getgid()).publish({'bb_session': 'synthetic'})
                self.assertTrue(observed)
                self.assertTrue(all(entry == (True, 0o700) for entry in observed), observed)
                self.assertEqual(list(target.glob('.gateway-session-cookie.stage-*')), [])
            finally:
                os.close(directory)

    def test_replace_failure_distinguishes_visibility_from_pre_write_failure(self):
        for after in (False, True):
            with self.subTest(after=after), tempfile.TemporaryDirectory() as temporary:
                directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
                final = Path(temporary) / owner.COOKIE_NAME
                final.write_bytes(b'{"bb_session":"old"}')
                final.chmod(0o640)
                native_replace = os.replace
                def fail(*args, **kwargs):
                    if after:
                        native_replace(*args, **kwargs)
                    raise OSError('SYNTHETIC_SECRET https://fixture.invalid/?secret=x')
                try:
                    with patch.object(owner.os, 'replace', side_effect=fail):
                        with self.assertRaises(owner.SafeError) as raised:
                            owner.Publisher(directory, os.getgid()).publish({'bb_session': 'new'})
                    self.assertEqual(raised.exception.code,
                                     'publication_unknown' if after else 'publication')
                    self.assertEqual(json.loads(final.read_bytes()),
                                     {'bb_session': 'new' if after else 'old'})
                    self.assertNotIn('SYNTHETIC', str(raised.exception))
                    self.assertEqual(len(list(Path(temporary).glob('*.stage-*'))), 0)
                finally:
                    os.close(directory)

    def test_directory_swap_before_publication_preserves_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'secrets'
            target.mkdir(mode=0o750)
            opened = owner.Directory(str(target), os.getuid(), 0o750, anchor=temporary)
            native_fsync = os.fsync
            swapped = False
            def swap(fd):
                nonlocal swapped
                native_fsync(fd)
                if not swapped:
                    swapped = True
                    target.rename(Path(temporary) / 'moved')
                    target.mkdir(mode=0o750)
            try:
                with patch.object(owner.os, 'fsync', side_effect=swap):
                    with self.assertRaises(owner.SafeError) as raised:
                        owner.Publisher(opened, os.getgid()).publish({'bb_session': 'synthetic'})
                self.assertEqual(raised.exception.code, 'publication')
                self.assertFalse((target / owner.COOKIE_NAME).exists())
                self.assertFalse((Path(temporary) / 'moved' / owner.COOKIE_NAME).exists())
            finally:
                opened.close()

    def test_invalid_cookie_set_never_touches_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                final = Path(temporary) / owner.COOKIE_NAME
                for cookies in [{}, {'bb_session': ''}, {'bb_session': True},
                                {'bb_session': 'x', 'other': 'x'},
                                {'bb_session': 'x\n'}, {'bb_session': 'x;y'},
                                {'bb_session': 'x,y'}, {'bb_session': 'x"y'},
                                {'bb_session': 'x\\y'}, {'bb_session': 'x' * 4097}]:
                    final.write_bytes(b'old-synthetic')
                    final.chmod(0o640)
                    with self.subTest(cookies=cookies):
                        with self.assertRaises(owner.SafeError) as raised:
                            owner.Publisher(directory, os.getgid()).publish(cookies)
                        self.assertEqual(raised.exception.code, 'cookies')
                        self.assertEqual(final.read_bytes(), b'old-synthetic')
                        self.assertEqual(list(Path(temporary).iterdir()), [final])
            finally:
                os.close(directory)

    def test_cookie_publication_is_private_and_keeps_prior_manual_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                final = Path(temporary) / owner.COOKIE_NAME
                final.write_bytes(b'{"bb_session":"old-synthetic"}')
                final.chmod(0o640)
                publisher = owner.Publisher(directory, os.getgid())
                publisher.publish({'bb_session': 'new-synthetic'})
                self.assertEqual(json.loads(final.read_bytes()), {'bb_session': 'new-synthetic'})
                backups = list(Path(temporary).glob('.gateway-session-cookie.rollback-*'))
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups[0].read_bytes(), b'{"bb_session":"old-synthetic"}')
                self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o640)
                self.assertEqual(final.stat().st_nlink, 1)
                self.assertEqual(list(Path(temporary).glob('.gateway-session-cookie.stage-*')), [])
            finally:
                os.close(directory)


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=')


class FixtureTerminal:
    def close(self): pass
    def __init__(self, events, ready=True):
        self.events, self.ready = events, ready
        self.answers = iter(('answer', 'fixture', 'synthetic-password'))

    def confirm_private_image(self, path):
        self.events.append(('image', str(path)))
        return self.ready

    def read_secret(self, prompt):
        self.events.append(('input', prompt))
        return next(self.answers)


class FixtureTransport:
    def __init__(self, events, frames=None):
        self.events = events
        self.frames = iter(frames or [
            {'kind': 'captcha', 'png': base64.b64encode(PNG).decode(), 'cap_required': True},
            {'kind': 'verified', 'cookies': {'bb_session': 'fixture-rotated'}}])

    def start(self): self.events.append('start')
    def receive(self): self.events.append('receive'); return next(self.frames)
    def send(self, value): self.events.append(('send', value))
    def recheck(self): self.events.append('identity')
    def finish(self): self.events.append('exit0')
    def abort(self): self.events.append('abort')


class FixtureStage:
    def __init__(self, path, events): self.path, self.events = path, events
    def write_png(self, png):
        self.events.append('png')
        self.path.write_bytes(png)
        self.path.chmod(0o600)
        return self.path
    def cleanup(self):
        self.events.append('cleanup')
        self.path.unlink(missing_ok=True)

class RefreshLockTests(unittest.TestCase):
    def test_concurrent_refresh_loser_has_no_transport_input_or_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private, secret = root / 'private', root / 'secrets'
            private.mkdir(mode=0o710); secret.mkdir(mode=0o700)
            ready_r, ready_w = os.pipe(); go_r, go_w = os.pipe(); result_r, result_w = os.pipe()
            def operation(block):
                events = []
                native_directory = owner.Directory
                class LocalDirectory(native_directory):
                    def __init__(self, path, uid, mode, anchor='/', gid=None):
                        super().__init__(path, os.getuid(), mode, anchor=temporary,
                                         gid=os.getgid() if gid == 0 else gid)
                class Transport(FixtureTransport):
                    def start(self):
                        events.append('transport')
                        if block:
                            os.write(ready_w, b'R')
                            assert os.read(go_r, 1) == b'G'
                        super().start()
                with patch.object(owner, 'Directory', LocalDirectory), patch.object(owner, 'SECRET_DIRECTORY', str(secret)), patch.object(owner, '_runtime_directory', lambda record: LocalDirectory(str(private), os.getuid(), 0o710)), patch.object(owner, 'DockerTransport', lambda source: Transport(events)):
                    code = 'success'
                    try: owner._owner_run(FixtureTerminal(events), types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()), b'fixture')
                    except owner.SafeError as exc: code = exc.code
                    return code, events
            pid = os.fork()
            if pid == 0:
                try:
                    code, events = operation(True)
                    os.write(result_w, json.dumps([code, events]).encode())
                    os._exit(0)
                except BaseException: os._exit(2)
            try:
                self.assertTrue(select.select([ready_r], [], [], 5)[0])
                self.assertEqual(os.read(ready_r, 1), b'R')
                code, events = operation(False)
                self.assertEqual(code, 'busy')
                self.assertEqual(events, [])
                self.assertFalse((secret / owner.COOKIE_NAME).exists())
            finally:
                os.write(go_w, b'G')
                _, status = os.waitpid(pid, 0)
                for fd in (ready_r, ready_w, go_r, go_w, result_w): os.close(fd)
            report = json.loads(os.read(result_r, 65536)); os.close(result_r)
            self.assertEqual(status, 0)
            self.assertEqual(report[0], 'success')
            self.assertIn('transport', report[1])
            self.assertEqual(json.loads((secret / owner.COOKIE_NAME).read_bytes()), {'bb_session': 'fixture-rotated'})
            # The same public operation succeeds after the winner has fully closed.
            self.assertEqual(operation(False)[0], 'success')


    def test_owner_failure_and_interruption_release_after_terminal_close(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); private=root/'private'; secret=root/'secret'
                private.mkdir(mode=0o710); secret.mkdir(mode=0o700)
                ready_r,ready_w=os.pipe()
                pid=os.fork()
                if pid==0:
                    native_directory=owner.Directory
                    class LocalDirectory(native_directory):
                        def __init__(self,path,uid,mode,anchor='/',gid=None):
                            super().__init__(path,os.getuid(),mode,anchor=temporary,
                                             gid=os.getgid() if gid == 0 else gid)
                    class Terminal(FixtureTerminal):
                        def close(self):
                            # The lock must still be held during terminal closure.
                            directory=LocalDirectory(str(private),os.getuid(),0o710)
                            try:
                                try: probe=owner._RefreshLock(directory)
                                except owner.SafeError as exc:
                                    assert exc.code=='busy'
                                    (root/'closed-under-lock').write_text('yes')
                                else:
                                    probe.close()
                                    raise AssertionError('lock released before terminal closure')
                            finally: directory.close()
                    class Transport(FixtureTransport):
                        def start(self):
                            os.write(ready_w,b'R')
                            if interrupted:
                                while True: signal.pause()
                            raise owner.SafeError('protocol')
                    try:
                        signal.signal(signal.SIGTERM,owner._abort_signal)
                        with patch.object(owner,'Directory',LocalDirectory),patch.object(owner,'SECRET_DIRECTORY',str(secret)),patch.object(owner,'_runtime_directory',lambda record:LocalDirectory(str(private),os.getuid(),0o710)),patch.object(owner,'DockerTransport',lambda source:Transport([])):
                            try: owner._owner_run(Terminal([]),types.SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid()),b'fixture')
                            except owner.SafeError as exc: assert exc.code==('privacy' if interrupted else 'protocol')
                            else: raise AssertionError('operation succeeded')
                        os._exit(0)
                    except BaseException: os._exit(2)
                try:
                    self.assertTrue(select.select([ready_r],[],[],5)[0])
                    self.assertEqual(os.read(ready_r,1),b'R')
                    if interrupted: os.kill(pid,signal.SIGTERM)
                    self.assertEqual(os.waitpid(pid,0)[1],0)
                    self.assertEqual((root/'closed-under-lock').read_text(),'yes')
                    directory=owner.Directory(str(private),os.getuid(),0o710,anchor=temporary)
                    try:
                        lock=owner._RefreshLock(directory); lock.close()
                    finally: directory.close()
                    self.assertEqual([p.name for p in private.iterdir()],['refresh.lock'])
                    self.assertEqual(list(secret.iterdir()),[])
                finally:
                    os.close(ready_r);os.close(ready_w)
    def test_unsafe_lock_inodes_are_refused_and_failure_releases_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / 'private'; private.mkdir(mode=0o710)
            directory = owner.Directory(str(private), os.getuid(), 0o710, anchor=temporary)
            path = private / 'refresh.lock'
            try:
                for kind in ('symlink', 'hardlink', 'mode', 'owner', 'swap'):
                    with self.subTest(kind=kind):
                        other = private / 'other'; other.write_bytes(b''); other.chmod(0o600)
                        if kind == 'symlink': path.symlink_to(other)
                        elif kind == 'hardlink': os.link(other, path)
                        else: path.write_bytes(b''); path.chmod(0o644 if kind == 'mode' else 0o600)
                        native_fstat, native_stat = os.fstat, os.stat
                        def fstat(fd):
                            info = native_fstat(fd)
                            if kind == 'owner' and stat.S_ISREG(info.st_mode):
                                fields = list(info); fields[4] = os.getuid() + 1
                                return os.stat_result(fields)
                            return info
                        def stat_path(name, **kwargs):
                            if kind == 'swap' and name == 'refresh.lock': os.replace(other, path)
                            return native_stat(name, **kwargs)
                        try:
                            with patch.object(owner.os, 'fstat', side_effect=fstat), patch.object(owner.os, 'stat', side_effect=stat_path), self.assertRaises(owner.SafeError): owner._RefreshLock(directory)
                        finally:
                            path.unlink()
                            if other.exists(): other.unlink()
                # Interrupted owner operation closes its descriptor; kernel release
                # is observed in a different process, never by the same open handle.
                for interrupted in (False, True):
                    pid = os.fork()
                    if pid == 0:
                        try:
                            signal.signal(signal.SIGTERM, owner._abort_signal)
                            lock = owner._RefreshLock(directory)
                            try:
                                if interrupted: os.kill(os.getpid(), signal.SIGTERM)
                                raise owner.SafeError('protocol')
                            finally: lock.close()
                        except owner.SafeError: os._exit(0)
                        except BaseException: os._exit(2)
                    self.assertEqual(os.waitpid(pid, 0)[1], 0)
                    lock = owner._RefreshLock(directory); lock.close()
            finally: directory.close()


class StageTests(unittest.TestCase):
    def test_runtime_stage_requires_tmpfs_and_creates_fixed_protected_base(self):
        mounts = ('1 0 0:1 / / rw - ext4 /dev/root rw\n'
                  '2 1 0:2 / /run rw - tmpfs tmpfs rw\n'
                  '3 2 0:3 / /run/disk rw - ext4 /dev/disk rw\n')
        owner.require_tmpfs('/run/audiobook-ops-owner-session', mounts)
        for path in ['/tmp', '/run/disk/private']:
            with self.subTest(path=path):
                with self.assertRaises(owner.SafeError) as raised:
                    owner.require_tmpfs(path, mounts)
                self.assertEqual(raised.exception.code, 'privacy')
        with tempfile.TemporaryDirectory() as temporary:
            run_path = Path(temporary) / 'run'
            run_path.mkdir(mode=0o755)
            parent = owner.Directory(str(run_path), os.getuid(), 0o755, anchor=temporary)
            try:
                base = owner._make_runtime_base(parent, os.getgid())
                self.assertIsNotNone(base)
                self.assertEqual(Path(base.path).name, 'audiobook-ops-owner-session')
                self.assertEqual(stat.S_IMODE(os.fstat(base.fd).st_mode), 0o710)
                self.assertEqual(os.fstat(base.fd).st_gid, os.getgid())
                base.close()
                again = owner._make_runtime_base(parent, os.getgid())
                again.close()
                (run_path / 'audiobook-ops-owner-session').chmod(0o777)
                with self.assertRaises(owner.SafeError):
                    owner._make_runtime_base(parent, os.getgid())
            finally:
                parent.close()

    def test_captcha_stage_is_owner_private_and_cleanup_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / 'private'
            private.mkdir(mode=0o710)
            base = owner.Directory(str(private), os.getuid(), 0o710, anchor=temporary)
            try:
                stage = owner.Stage(base, os.getuid(), os.getgid())
                image = Path(stage.write_png(PNG))
                self.assertTrue(image.exists())
                self.assertEqual(image.read_bytes(), PNG)
                self.assertEqual(stat.S_IMODE(image.stat().st_mode), 0o600)
                self.assertEqual(image.stat().st_nlink, 1)
                self.assertEqual(image.stat().st_uid, os.getuid())
                self.assertEqual(stat.S_IMODE(image.parent.stat().st_mode), 0o700)
                stage.cleanup()
                stage.cleanup()
                self.assertEqual(list(private.iterdir()), [])
            finally:
                base.close()


class RefreshTests(unittest.TestCase):
    def test_identity_drift_while_owner_types_denies_credential_transmission(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            class DriftTransport(FixtureTransport):
                checks = 0
                def recheck(self):
                    self.checks += 1
                    if self.checks == 2:
                        raise owner.SafeError('identity')
                    super().recheck()
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(owner.SafeError) as raised:
                    owner.refresh(FixtureTerminal(events), DriftTransport(events),
                                  FixtureStage(Path(temporary) / 'captcha.png', events),
                                  owner.Publisher(directory, os.getgid()))
                self.assertEqual(raised.exception.code, 'identity')
                self.assertEqual([event for event in events if isinstance(event, tuple) and event[0] == 'send'], [])
                self.assertIn('abort', events)
                self.assertEqual(list(Path(temporary).iterdir()), [])
            finally:
                os.close(directory)

    def test_failures_at_private_boundaries_leave_old_cookie_and_clean_stage(self):
        cases = ('image-refused', 'first-frame', 'input', 'send', 'verify-frame',
                 'identity-before-input', 'identity-before-publish', 'finish', 'write-image')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                events = []
                class Terminal(FixtureTerminal):
                    def read_secret(self, prompt):
                        if case == 'input':
                            raise RuntimeError('SYNTHETIC_SECRET https://fixture.invalid/private')
                        return super().read_secret(prompt)
                class Transport(FixtureTransport):
                    checks = 0
                    received = 0
                    def receive(self):
                        self.received += 1
                        if (case == 'first-frame' and self.received == 1) or (case == 'verify-frame' and self.received == 2):
                            raise RuntimeError('SYNTHETIC_SECRET')
                        return super().receive()
                    def send(self, value):
                        if case == 'send':
                            raise RuntimeError('SYNTHETIC_SECRET')
                        super().send(value)
                    def recheck(self):
                        self.checks += 1
                        if (case == 'identity-before-input' and self.checks == 1) or (case == 'identity-before-publish' and self.checks == 2):
                            raise owner.SafeError('identity')
                        super().recheck()
                    def finish(self):
                        if case == 'finish':
                            raise RuntimeError('SYNTHETIC_SECRET')
                        super().finish()
                class ImageStage(FixtureStage):
                    def write_png(self, png):
                        result = super().write_png(png)
                        if case == 'write-image':
                            raise RuntimeError('SYNTHETIC_SECRET')
                        return result
                directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
                final = Path(temporary) / owner.COOKIE_NAME
                final.write_bytes(b'{"bb_session":"old-synthetic"}')
                final.chmod(0o640)
                try:
                    with self.assertRaises(owner.SafeError) as raised:
                        owner.refresh(Terminal(events, ready=case != 'image-refused'), Transport(events),
                                      ImageStage(Path(temporary) / 'captcha.png', events),
                                      owner.Publisher(directory, os.getgid()))
                    self.assertNotIn('SYNTHETIC_SECRET', str(raised.exception))
                    self.assertEqual(final.read_bytes(), b'{"bb_session":"old-synthetic"}')
                    self.assertEqual(list(Path(temporary).iterdir()), [final])
                    if case != 'identity-before-publish':
                        self.assertIn('abort', events)
                    if case in ('image-refused', 'first-frame', 'identity-before-input', 'write-image'):
                        self.assertFalse(any(isinstance(event, tuple) and event[0] == 'input' for event in events))
                finally:
                    os.close(directory)

    def test_close_failure_after_publish_closes_remaining_resources_and_reports_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private, secret = root / 'private', root / 'secrets'
            private.mkdir(mode=0o710)
            secret.mkdir(mode=0o700)
            events, closed = [], []
            native_directory = owner.Directory
            class FixtureDirectory(native_directory):
                def __init__(self, path, uid, mode, anchor='/', gid=None):
                    super().__init__(path, os.getuid(), mode, anchor=temporary,
                                     gid=os.getgid() if gid == 0 else gid)
                def close(self):
                    super().close()
                    closed.append(Path(self.path).name)
                    if Path(self.path).name == 'secrets':
                        raise OSError('SYNTHETIC_SECRET https://fixture.invalid/private')
            record = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            caught = None
            with patch.object(owner, 'Directory', FixtureDirectory), \
                 patch.object(owner, 'SECRET_DIRECTORY', str(secret)), \
                 patch.object(owner, '_runtime_directory',
                              lambda record: FixtureDirectory(str(private), os.getuid(), 0o710)), \
                 patch.object(owner, 'DockerTransport', lambda source: FixtureTransport(events)):
                try:
                    owner._owner_run(FixtureTerminal(events), record, b'reviewed-synthetic')
                except BaseException as error:
                    caught = error
            self.assertIsInstance(caught, owner.SafeError)
            self.assertEqual(caught.code, 'publication_unknown')
            self.assertEqual(closed, ['secrets', 'private'])
            self.assertEqual(json.loads((secret / owner.COOKIE_NAME).read_bytes()),
                             {'bb_session': 'fixture-rotated'})
            self.assertEqual([p.name for p in private.iterdir()], ['refresh.lock'])

    def test_owner_operation_wires_real_private_stage_and_publisher(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private, secret = root / 'private', root / 'secrets'
            private.mkdir(mode=0o710)
            secret.mkdir(mode=0o700)
            events = []
            native_directory = owner.Directory
            class FixtureDirectory(native_directory):
                def __init__(self, path, uid, mode, anchor='/', gid=None):
                    super().__init__(path, os.getuid(), mode, anchor=temporary,
                                     gid=os.getgid() if gid == 0 else gid)
            record = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(owner, 'Directory', FixtureDirectory), \
                 patch.object(owner, 'SECRET_DIRECTORY', str(secret)), \
                 patch.object(owner, '_runtime_directory',
                              lambda record: FixtureDirectory(str(private), os.getuid(), 0o710)), \
                 patch.object(owner, 'DockerTransport', lambda source: FixtureTransport(events)):
                owner._owner_run(FixtureTerminal(events), record, b'reviewed-synthetic')
            final = secret / owner.COOKIE_NAME
            self.assertTrue(final.exists())
            self.assertEqual(json.loads(final.read_bytes()), {'bb_session': 'fixture-rotated'})
            self.assertEqual([p.name for p in private.iterdir()], ['refresh.lock'])

    def test_malformed_png_is_rejected_before_owner_inputs(self):
        for png in [b'\x89PNG\r\n\x1a\n' + b'\x00' * 24, PNG[:-3], PNG + b'extra', PNG[:52] + bytes([PNG[52] ^ 1]) + PNG[53:]]:
            with self.subTest(png=png), tempfile.TemporaryDirectory() as temporary:
                events = []
                frames = [{'kind': 'captcha', 'cap_required': True,
                           'png': base64.b64encode(png).decode()},
                          {'kind': 'verified', 'cookies': {'bb_session': 'fixture'}}]
                directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    with self.assertRaises(owner.SafeError) as raised:
                        owner.refresh(FixtureTerminal(events), FixtureTransport(events, frames),
                                      FixtureStage(Path(temporary) / 'captcha.png', events),
                                      owner.Publisher(directory, os.getgid()))
                    self.assertEqual(raised.exception.code, 'challenge')
                    self.assertFalse(any(isinstance(event, tuple) and event[0] == 'input' for event in events))
                    self.assertFalse((Path(temporary) / owner.COOKIE_NAME).exists())
                    self.assertIn('abort', events)
                finally:
                    os.close(directory)


    def test_action_keycodes_never_reach_helper_or_publication(self):
        for index in range(3):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                events=[]
                terminal=FixtureTerminal(events)
                answers=['answer','fixture','synthetic-password']; answers[index] += chr(0xE007)
                terminal.answers=iter(answers)
                directory=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY)
                try:
                    code='accepted'
                    try: owner.refresh(terminal,FixtureTransport(events),FixtureStage(Path(temporary)/'captcha.png',events),owner.Publisher(directory,os.getgid()))
                    except owner.SafeError as exc: code=exc.code
                    self.assertEqual(code,'privacy')
                    self.assertFalse(any(isinstance(event,tuple) and event[0]=='send' for event in events))
                    self.assertFalse((Path(temporary)/owner.COOKIE_NAME).exists())
                finally: os.close(directory)
    def test_verified_exited_helper_publishes_only_after_private_image_and_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            try:
                owner.refresh(FixtureTerminal(events), FixtureTransport(events),
                              FixtureStage(Path(temporary) / 'captcha.png', events),
                              owner.Publisher(directory, os.getgid()))
                final = Path(temporary) / owner.COOKIE_NAME
                self.assertTrue(final.exists())
                self.assertEqual(json.loads(final.read_bytes()), {'bb_session': 'fixture-rotated'})
                self.assertEqual([entry[1] for entry in events if isinstance(entry, tuple) and entry[0] == 'input'],
                                 ['Captcha: ', 'Username: ', 'Password: '])
                self.assertEqual([entry[1] for entry in events if isinstance(entry, tuple) and entry[0] == 'send'],
                                 [{'kind': 'login', 'captcha': 'answer', 'username': 'fixture',
                                   'password': 'synthetic-password'}])
                self.assertEqual(events[-4:], ['exit0', 'identity', 'cleanup', 'cleanup'])
                self.assertNotIn('abort', events)
                self.assertFalse((Path(temporary) / 'captcha.png').exists())
            finally:
                os.close(directory)


if __name__ == '__main__':
    unittest.main()
