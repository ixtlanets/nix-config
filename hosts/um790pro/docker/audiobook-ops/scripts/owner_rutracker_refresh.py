#!/usr/bin/python3
"""Owner terminal launcher; never invoke from an agent or recorded terminal."""


import json
import fcntl
import struct
import stat
import secrets
import re
import base64
import binascii
import termios
import select
import time
import subprocess
import hashlib
import pwd
import resource
import signal
import zlib
import os
import sys


class SafeError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def authorize(euid, uid, owner_uid, owner_gid, invoking):
    # Compose's gateway runs as 1000:1000 and reads a file-mounted 0640 secret.
    if (euid != 0 or uid != 0 or owner_uid <= 0 or owner_gid != 1000
            or invoking.get('SUDO_USER') != 'nik'
            or invoking.get('SUDO_UID') != str(owner_uid)
            or invoking.get('SUDO_GID') != str(owner_gid)):
        raise SafeError('privacy')


MAX_FRAME = 2097152


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafeError('protocol')
        result[key] = value
    return result


def _exact_read(stream, size):
    parts = []
    while size:
        part = stream.read(size)
        if not part:
            raise SafeError('protocol')
        parts.append(part)
        size -= len(part)
    return b''.join(parts)


def write_frame(stream, value):
    try:
        if type(value) is not dict:
            raise SafeError('protocol')
        data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if not 0 < len(data) <= MAX_FRAME:
            raise SafeError('protocol')
        stream.write(struct.pack('!I', len(data)) + data)
        stream.flush()
    except (OSError, ValueError, TypeError):
        raise SafeError('protocol') from None


def read_frame(stream):
    try:
        size = struct.unpack('!I', _exact_read(stream, 4))[0]
        if not 0 < size <= MAX_FRAME:
            raise SafeError('protocol')
        value = json.loads(_exact_read(stream, size), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(SafeError('protocol')))
        if type(value) is not dict:
            raise SafeError('protocol')
        return value
    except (OSError, ValueError, UnicodeError):
        raise SafeError('protocol') from None


COOKIE_NAME = 'gateway-session-cookie'
COOKIE_NAMES = frozenset({'bb_session', 'bb_data', 'bb_t', 'bb_ssl'})


def validate_cookies(cookies):
    if (type(cookies) is not dict or not cookies or not cookies.get('bb_session')
            or not cookies.keys() <= COOKIE_NAMES):
        raise SafeError('cookies')
    total = 0
    for value in cookies.values():
        if (type(value) is not str or not value or len(value) > 4096
                or any(ord(char) < 33 or ord(char) > 126 or char in ';,"\\' for char in value)):
            raise SafeError('cookies')
        total += len(value)
    if total > 16384:
        raise SafeError('cookies')
    return dict(cookies)


class Directory:
    """Directory capability opened without symlinks and revalidated by pathname."""
    def __init__(self, path, uid, mode, anchor='/', gid=None):
        self.path, self.uid, self.mode, self.anchor, self.gid = path, uid, mode, anchor, gid
        self.fd = self._open()
        self.identity = _inode(os.fstat(self.fd))

    def _open(self):
        prefix = self.anchor.rstrip('/') + '/'
        if (not self.path.startswith(prefix) or any(part in ('.', '..') for part in self.path.split('/'))):
            raise SafeError('privacy')
        parts = self.path[len(prefix):].split('/')
        fd = None
        try:
            fd = os.open(self.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            for index, part in enumerate(parts):
                info = os.fstat(fd)
                if info.st_uid != self.uid or stat.S_IMODE(info.st_mode) & 0o022:
                    raise SafeError('privacy')
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if (info.st_uid != self.uid or stat.S_IMODE(info.st_mode) != self.mode
                    or (self.gid is not None and info.st_gid != self.gid)):
                raise SafeError('privacy')
            result, fd = fd, None
            return result
        except OSError:
            raise SafeError('privacy') from None
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        os.close(self.fd)

    def recheck(self):
        other = self._open()
        try:
            if _inode(os.fstat(other)) != self.identity:
                raise SafeError('privacy')
        finally:
            os.close(other)


def _inode(info):
    return info.st_dev, info.st_ino


class Stage:
    """One PNG in a private owner directory; never follows user-replaced entries."""
    def __init__(self, base, owner_uid, owner_gid):
        self.base, self.owner_uid, self.owner_gid = base, owner_uid, owner_gid
        self.name = secrets.token_hex(16)
        self.path = base.path + '/' + self.name
        self.closed = False
        self.png_inode = None
        self.fd = None
        try:
            base.recheck()
            os.mkdir(self.name, 0o700, dir_fd=base.fd)
            self.fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=base.fd)
            os.fchown(self.fd, owner_uid, owner_gid)
            os.fchmod(self.fd, 0o700)
            self.identity = _inode(os.fstat(self.fd))
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
            try:
                os.rmdir(self.name, dir_fd=base.fd)
            except OSError:
                pass
            raise SafeError('privacy') from None

    def _recheck(self):
        self.base.recheck()
        info = os.stat(self.name, dir_fd=self.base.fd, follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or _inode(info) != self.identity
                or info.st_uid != self.owner_uid or info.st_gid != self.owner_gid
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise SafeError('privacy')

    def write_png(self, png):
        if self.closed or self.png_inode is not None:
            raise SafeError('privacy')
        self._recheck()
        fd = None
        try:
            fd = os.open('captcha.png', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=self.fd)
            self.png_inode = _inode(os.fstat(fd))
            _write_all(fd, png)
            os.fchown(fd, self.owner_uid, self.owner_gid)
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        except OSError:
            raise SafeError('privacy') from None
        finally:
            if fd is not None:
                os.close(fd)
        self._recheck()
        return self.path + '/captcha.png'

    def cleanup(self):
        if self.closed:
            if _exists(self.base.fd, self.name):
                raise SafeError('cleanup')
            return
        error = False
        try:
            self._recheck()
            if self.png_inode is not None:
                info = os.stat('captcha.png', dir_fd=self.fd, follow_symlinks=False)
                _regular_private(info, self.owner_uid, 0o600, self.owner_gid)
                if _inode(info) != self.png_inode:
                    raise SafeError('cleanup')
                os.unlink('captcha.png', dir_fd=self.fd)
                self.png_inode = None
            os.rmdir(self.name, dir_fd=self.base.fd)
        except BaseException:
            error = True
        finally:
            try:
                os.close(self.fd)
            except OSError:
                error = True
            self.closed = True
        if error:
            raise SafeError('cleanup') from None


class Publisher:
    def __init__(self, directory, owner_gid):
        self.directory = directory.fd if isinstance(directory, Directory) else directory
        self.guard = directory.recheck if isinstance(directory, Directory) else lambda: None
        self.owner_gid = owner_gid
        self.published = False

    def publish(self, cookies):
        self.published = False
        validate_cookies(cookies)
        stage = '.gateway-session-cookie.stage-' + secrets.token_hex(16)
        backup = '.gateway-session-cookie.rollback-' + secrets.token_hex(16)
        renamed = False
        error_code = None
        cleanup_failed = False
        stage_dir = stage_fd = backup_fd = old_fd = None
        try:
            self.guard()
            os.mkdir(stage, 0o700, dir_fd=self.directory)
            stage_dir = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=self.directory)
            os.fchmod(stage_dir, 0o700)
            stage_fd = os.open('cookie', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=stage_dir)
            data = json.dumps(cookies, separators=(',', ':'), sort_keys=True).encode('ascii')
            _write_all(stage_fd, data)
            os.fchown(stage_fd, os.geteuid(), self.owner_gid)
            os.fchmod(stage_fd, 0o640)
            os.fsync(stage_fd)
            try:
                old_fd = os.open(COOKIE_NAME, os.O_RDONLY | os.O_NOFOLLOW,
                                 dir_fd=self.directory)
            except FileNotFoundError:
                pass
            if old_fd is not None:
                old_stat = os.fstat(old_fd)
                _regular_private(old_stat, os.geteuid(), 0o640, self.owner_gid)
                backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                    0o600, dir_fd=self.directory)
                previous = os.read(old_fd, MAX_FRAME + 1)
                if len(previous) > MAX_FRAME:
                    raise SafeError('privacy')
                _write_all(backup_fd, previous)
                os.fchmod(backup_fd, 0o600)
                os.fsync(backup_fd)
                current = os.stat(COOKIE_NAME, dir_fd=self.directory, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (old_stat.st_dev, old_stat.st_ino):
                    raise SafeError('privacy')
            elif _exists(self.directory, COOKIE_NAME):
                raise SafeError('privacy')
            os.fsync(self.directory)
            self.guard()
            os.replace('cookie', COOKIE_NAME, src_dir_fd=stage_dir, dst_dir_fd=self.directory)
            renamed = True
            self.published = True
            self.guard()
            os.fsync(self.directory)
        except BaseException:
            # A wrapper can fail after rename made the new inode visible.
            if not renamed and stage_fd is not None:
                try:
                    final = os.stat(COOKIE_NAME, dir_fd=self.directory, follow_symlinks=False)
                    renamed = _inode(final) == _inode(os.fstat(stage_fd))
                except OSError:
                    pass
            self.published = renamed
            error_code = 'publication_unknown' if renamed else 'publication'
        finally:
            for fd in (stage_fd, backup_fd, old_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        cleanup_failed = True
            if stage_dir is not None:
                try:
                    os.unlink('cookie', dir_fd=stage_dir)
                except FileNotFoundError:
                    pass
                except OSError:
                    cleanup_failed = True
                try:
                    os.close(stage_dir)
                except OSError:
                    cleanup_failed = True
            try:
                os.rmdir(stage, dir_fd=self.directory)
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if error_code or cleanup_failed:
            raise SafeError(error_code or ('publication_unknown' if renamed else 'cleanup')) from None


def _exists(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _regular_private(info, uid, mode, gid=None):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != mode or (gid is not None and info.st_gid != gid)):
        raise SafeError('privacy')


def _write_all(fd, data):
    while data:
        size = os.write(fd, data)
        if size <= 0:
            raise SafeError('privacy')
        data = data[size:]


EXPECTED_MANIFEST = 'sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa'
EXPECTED_CONFIG_DIGEST = 'sha256:894893ed4d4557764df3e74d27c5bc1b3944e5a33ed410e62ab7c744b348f415'
EXPECTED_IMAGE = EXPECTED_CONFIG_DIGEST  # Classic image-store ID; fixture compatibility.
EXPECTED_REFERENCE = 'ghcr.io/flaresolverr/flaresolverr@' + EXPECTED_MANIFEST
# The raw pinned public OCI manifest is 2572 bytes and names EXPECTED_CONFIG_DIGEST.
# Its hash/config relationship is checked by portable tests, not supplied by
# Docker's Descriptor (which describes the manifest, not its config).
EXPECTED_DESCRIPTOR = {
    'digest': EXPECTED_MANIFEST,
    'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'size': 2572,
}
IMAGE_PROJECTION = ('{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},'
                    '"Descriptor":{{json (index . "Descriptor")}},"Os":{{json .Os}},'
                    '"Architecture":{{json .Architecture}}}')
EXPECTED_CONFIG = {
    'Image': EXPECTED_REFERENCE, 'User': 'flaresolverr', 'WorkingDir': '/app',
    'Entrypoint': ['/usr/bin/dumb-init', '--'],
    'Cmd': ['/usr/local/bin/python', '-u', '/app/flaresolverr.py'],
    'Env': [
        'PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LANG=C.UTF-8', 'GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D',
        'PYTHON_VERSION=3.11.15',
        'PYTHON_SHA256=272179ddd9a2e41a0fc8e42e33dfbdca0b3711aa5abf372d3f2d51543d09b625',
        'LOG_LEVEL=warning', 'LOG_HTML=false', 'CAPTCHA_SOLVER=none', 'TZ=Europe/Moscow'],
}
CONTAINER = 'audiobook-ops-flaresolverr'
DOCKER = ('/usr/bin/docker', '--host', 'unix:///var/run/docker.sock')


def image_identity(value, actual_id):
    """Bind actual container image to the daemon's exact pinned-reference lookup."""
    if (type(value) is not dict or actual_id not in (EXPECTED_MANIFEST, EXPECTED_CONFIG_DIGEST)
            or value.get('Id') != actual_id or value.get('Os') != 'linux'
            or value.get('Architecture') != 'amd64'):
        raise SafeError('identity')
    digests = value.get('RepoDigests')
    if (type(digests) is not list or not all(type(item) is str for item in digests)
            or EXPECTED_REFERENCE not in digests):
        raise SafeError('identity')
    descriptor = value.get('Descriptor')
    # containerd must report the pinned image manifest, never an OCI index.
    # Classic stores may omit Descriptor: the exact RepoDigest lookup plus
    # config ID independently binds the pinned reference to the config digest.
    if actual_id == EXPECTED_MANIFEST or descriptor is not None:
        if (type(descriptor) is not dict or descriptor != EXPECTED_DESCRIPTOR
                or type(descriptor.get('size')) is not int):
            raise SafeError('identity')
    return json.dumps({'Id': actual_id, 'RepoDigests': sorted(digests),
                       'Descriptor': descriptor, 'Os': value['Os'],
                       'Architecture': value['Architecture']}, sort_keys=True)


def inspect_identity(value, image_evidence=None):
    try:
        state, config = value['State'], value['Config']
        environment = config.get('Env', [])
        if (value['Name'] != '/' + CONTAINER or not re.fullmatch('[0-9a-f]{64}', value['Id'])
                or value['Image'] not in (EXPECTED_CONFIG_DIGEST, EXPECTED_MANIFEST)
                or (image_evidence is None and value['Image'] != EXPECTED_CONFIG_DIGEST)
                or config['Image'] != EXPECTED_REFERENCE
                or state['Running'] is not True or state.get('Paused') or state.get('Restarting')
                or state.get('Dead') or type(state['Pid']) is not int or state['Pid'] <= 0
                or type(state['StartedAt']) is not str or not state['StartedAt']
                or type(environment) is not list):
            raise SafeError('identity')
        host = value['HostConfig']
        if (host.get('Privileged') is not False or host.get('CapAdd') not in (None, [])
                or host.get('CapDrop') not in (None, []) or host.get('SecurityOpt') not in (None, [])
                or host.get('UsernsMode') not in (None, '')
                or host.get('NetworkMode') != 'audiobook-ops-backend'
                or host.get('PidMode') != ''):
            raise SafeError('identity')
        mounts = value['Mounts']
        if (type(mounts) is not list or len(mounts) != 1 or type(mounts[0]) is not dict
                or mounts[0] != {'Type': 'bind', 'Source': '/home/nik/services/readmeabook/flaresolverr',
                                 'Destination': '/config', 'Mode': 'rw', 'RW': True,
                                 'Propagation': 'rprivate'}):
            raise SafeError('identity')
        networks = value['NetworkSettings']['Networks']
        if type(networks) is not dict or set(networks) != {'audiobook-ops-backend'}:
            raise SafeError('identity')
        network = networks['audiobook-ops-backend']
        if (type(network) is not dict
                or not all(type(network.get(key)) is str and re.fullmatch('[0-9a-f]{64}', network[key])
                           for key in ('NetworkID', 'EndpointID'))
                or type(network.get('Aliases')) is not list
                or sorted(network['Aliases']) != ['audiobook-ops-flaresolverr', 'flaresolverr']):
            raise SafeError('identity')
        for key in ('User', 'WorkingDir', 'Entrypoint', 'Cmd'):
            if config.get(key) != EXPECTED_CONFIG[key]:
                raise SafeError('identity')
        if (len(environment) != len(EXPECTED_CONFIG['Env'])
                or set(environment) != set(EXPECTED_CONFIG['Env'])):
            raise SafeError('identity')
        for entry in environment:
            if type(entry) is not str or '=' not in entry:
                raise SafeError('identity')
            key = entry.split('=', 1)[0].lower()
            if ('proxy' in key or key in ('chrome_args', 'browser_args', 'ssl_cert_file',
                                         'ssl_cert_dir', 'requests_ca_bundle', 'node_tls_reject_unauthorized')):
                raise SafeError('identity')
        # Canonical strings are immutable and capture every accepted topology/config field.
        identity = (value['Id'], value['Image'], state['StartedAt'], state['Pid'],
                json.dumps(host, sort_keys=True), json.dumps(mounts, sort_keys=True),
                json.dumps(networks, sort_keys=True), json.dumps(config, sort_keys=True))
        return identity + ((image_identity(image_evidence, value['Image']),)
                           if image_evidence is not None else ())
    except (KeyError, TypeError, ValueError):
        raise SafeError('identity') from None


def namespace_identity(pid):
    """Local daemon only: compare nsfs inodes, without opening container files."""
    try:
        result = []
        for kind in ('net', 'pid'):
            host = os.stat('/proc/self/ns/' + kind)
            child = os.stat('/proc/' + str(pid) + '/ns/' + kind)
            host_id = (host.st_dev, host.st_ino)
            child_id = (child.st_dev, child.st_ino)
            if host_id == child_id:
                raise SafeError('identity')
            result.append(child_id)
        return tuple(result)
    except OSError:
        raise SafeError('identity') from None


HELPER_CODES = frozenset(('protocol', 'browser', 'challenge', 'target', 'authentication',
                          'cookies', 'privacy', 'identity', 'timeout', 'cleanup'))


def _expected_frame(frame, kind, fields):
    if type(frame) is not dict:
        raise SafeError('protocol')
    if frame.get('kind') == 'error':
        if set(frame) != {'kind', 'code'} or frame.get('code') not in HELPER_CODES:
            raise SafeError('protocol')
        raise SafeError(frame['code'])
    if frame.get('kind') != kind or set(frame) != fields:
        raise SafeError('protocol')
    return frame


def validate_png(png):
    if (type(png) is not bytes or not 45 <= len(png) <= 1048576
            or not png.startswith(b'\x89PNG\r\n\x1a\n')):
        raise SafeError('challenge')
    position, seen_header, seen_data, chunks = 8, False, False, 0
    while position + 12 <= len(png):
        length = struct.unpack('!I', png[position:position + 4])[0]
        kind = png[position + 4:position + 8]
        end = position + length + 12
        chunks += 1
        if end > len(png) or chunks > 4096 or not re.fullmatch(b'[A-Za-z]{4}', kind):
            raise SafeError('challenge')
        checksum = struct.unpack('!I', png[end - 4:end])[0]
        if zlib.crc32(png[position + 4:end - 4]) != checksum:
            raise SafeError('challenge')
        if not seen_header:
            if kind != b'IHDR' or length != 13:
                raise SafeError('challenge')
            width, height = struct.unpack('!II', png[position + 8:position + 16])
            if not 1 <= width <= 8192 or not 1 <= height <= 8192:
                raise SafeError('challenge')
            seen_header = True
        elif kind == b'IHDR':
            raise SafeError('challenge')
        if kind == b'IDAT':
            seen_data = True
        if kind == b'IEND':
            if length != 0 or end != len(png) or not seen_data:
                raise SafeError('challenge')
            return
        position = end
    raise SafeError('challenge')


def refresh(terminal, transport, stage, publisher):
    started = finished = published = False
    primary = None
    try:
        transport.start()
        started = True
        frame = _expected_frame(transport.receive(), 'captcha', {'kind', 'png', 'cap_required'})
        if type(frame['png']) is not str or type(frame['cap_required']) is not bool:
            raise SafeError('challenge')
        try:
            png = base64.b64decode(frame['png'], validate=True)
        except (ValueError, binascii.Error):
            raise SafeError('challenge') from None
        validate_png(png)
        image = stage.write_png(png)
        if not terminal.confirm_private_image(image):
            raise SafeError('privacy')
        transport.recheck()
        captcha = terminal.read_secret('Captcha: ') if frame['cap_required'] else ''
        username = terminal.read_secret('Username: ')
        password = terminal.read_secret('Password: ')
        for answer in (captcha, username, password):
            if type(answer) is not str or len(answer) > 4096 or any(ord(c) < 32 or ord(c) == 127 or 0xE000 <= ord(c) <= 0xE0FF for c in answer):
                raise SafeError('privacy')
        if not username or not password or (frame['cap_required'] and not captcha):
            raise SafeError('authentication')
        transport.recheck()
        transport.send({'kind': 'login', 'username': username, 'password': password, 'captcha': captcha})
        del username, password, captcha
        result = _expected_frame(transport.receive(), 'verified', {'kind', 'cookies'})
        cookies = validate_cookies(result['cookies'])
        transport.finish()
        finished = True
        transport.recheck()
        stage.cleanup()
        publisher.publish(cookies)
        published = True
    except BaseException as error:
        primary = (SafeError('publication_unknown') if getattr(publisher, 'published', False)
                   else error if isinstance(error, SafeError) else SafeError('privacy'))
    finally:
        cleanup_failed = False
        if started and not finished:
            try:
                transport.abort()
            except BaseException:
                cleanup_failed = True
        try:
            stage.cleanup()
        except BaseException:
            cleanup_failed = True
        if primary is None and cleanup_failed:
            primary = SafeError('publication_unknown' if published else 'cleanup')
    if primary is not None:
        raise primary from None


HELPER_SHA256 = '3793099c1f16d624d80b3f83373d5b825f81e9f9505da79f1f8f004591d40887'
HELPER_LENGTH = 45655
MINIMAL_ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
               'HOME': '/nonexistent', 'TMPDIR': '/run/audiobook-ops-owner-session'}


def validate_overlay_changes(data):
    if type(data) is not bytes or len(data) > 262144:
        raise SafeError('identity')
    try:
        text = data.decode('ascii')
    except UnicodeError:
        raise SafeError('identity') from None
    if any(ord(char) < 32 and char != '\n' for char in text):
        raise SafeError('identity')
    lines = text.splitlines()
    if len(lines) > 4096:
        raise SafeError('identity')
    state = ('/config', '/tmp', '/run', '/app/.cache', '/app/.config', '/app/.local',
             '/app/__pycache__', '/app/undetected_chromedriver/__pycache__')
    changed_parents = {'/app', '/app/undetected_chromedriver'}
    for line in lines:
        if len(line) < 4 or line[:2] not in ('A ', 'C ', 'D '):
            raise SafeError('identity')
        path = line[2:]
        if (not path.startswith('/') or '//' in path
                or any(part in ('.', '..') for part in path.split('/'))):
            raise SafeError('identity')
        allowed = any(path == prefix or path.startswith(prefix + '/') for prefix in state)
        allowed = allowed or (line[0] == 'C' and path in changed_parents | {'/app/chromedriver'})
        if not allowed:
            raise SafeError('identity')


class _TimedPipe:
    def __init__(self, fd, deadline):
        self.fd, self.deadline = fd, deadline
        os.set_blocking(fd, False)

    def _ready(self, writing=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SafeError('timeout')
        readable, writable, _ = select.select([] if writing else [self.fd],
                                             [self.fd] if writing else [], [], remaining)
        if not (writable if writing else readable):
            raise SafeError('timeout')

    def read(self, size):
        self._ready()
        return os.read(self.fd, size)

    def write(self, data):
        total = len(data)
        while data:
            self._ready(True)
            size = os.write(self.fd, data[:65536])
            if size <= 0:
                raise SafeError('protocol')
            data = data[size:]
        return total

    def flush(self):
        pass


class DockerTransport:
    """One fixed daemon, fixed inspect target, fixed reviewed source, no HTTP API."""
    def __init__(self, helper_source, deadline=None, runner=subprocess.run,
                 process_factory=subprocess.Popen):
        self.source, self.deadline = helper_source, deadline or time.monotonic() + 600
        self.runner, self.process_factory = runner, process_factory
        self.process = None
        self.identity = None

    def _inspect_image(self):
        # Local read only. Never pull, use a tag, or derive a selector from input.
        result = self.runner([*DOCKER, 'image', 'inspect', '--format', IMAGE_PROJECTION,
                              EXPECTED_REFERENCE], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=15, check=False, env=dict(MINIMAL_ENV), close_fds=True)
        if result.returncode != 0 or len(result.stdout) > MAX_FRAME:
            raise SafeError('identity')
        value = json.loads(result.stdout, object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(SafeError('identity')))
        if type(value) is not dict:
            raise SafeError('identity')
        return value

    def _inspect(self):
        try:
            result = self.runner([*DOCKER, 'inspect', '--format', '{{json .}}', CONTAINER],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, timeout=15, check=False,
                                 env=dict(MINIMAL_ENV), close_fds=True)
            if result.returncode != 0 or len(result.stdout) > MAX_FRAME:
                raise SafeError('identity')
            value = json.loads(result.stdout, object_pairs_hook=_unique_pairs)
            identity = inspect_identity(value, self._inspect_image())
            identity += (namespace_identity(identity[3]),)
            network_id = value['NetworkSettings']['Networks']['audiobook-ops-backend']['NetworkID']
            network_result = self.runner([*DOCKER, 'network', 'inspect', '--format', '{{json .}}', network_id],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, timeout=15, check=False,
                                         env=dict(MINIMAL_ENV), close_fds=True)
            if network_result.returncode != 0 or len(network_result.stdout) > MAX_FRAME:
                raise SafeError('identity')
            network = json.loads(network_result.stdout, object_pairs_hook=_unique_pairs)
            if (type(network) is not dict or network.get('Id') != network_id
                    or network.get('Name') != 'audiobook-ops-backend'
                    or network.get('Driver') != 'bridge' or network.get('Scope') != 'local'
                    or network.get('Internal') is not False or network.get('Ingress') is not False
                    or network.get('ConfigOnly') is not False):
                raise SafeError('identity')
            # Include network configuration, excluding mutable peer membership.
            identity += (json.dumps({key: item for key, item in network.items()
                                     if key != 'Containers'}, sort_keys=True),)

            changes = self.runner([*DOCKER, 'diff', identity[0]], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
                                  check=False, env=dict(MINIMAL_ENV), close_fds=True)
            if changes.returncode != 0:
                raise SafeError('identity')
            validate_overlay_changes(changes.stdout)
            return identity
        except subprocess.TimeoutExpired:
            raise SafeError('timeout') from None
        except (OSError, ValueError, TypeError):
            raise SafeError('identity') from None

    def start(self):
        if (self.process is not None or len(self.source) != HELPER_LENGTH
                or hashlib.sha256(self.source).hexdigest() != HELPER_SHA256):
            raise SafeError('identity')
        self.identity = self._inspect()
        bootstrap = (
            "import sys,hashlib,resource;resource.setrlimit(resource.RLIMIT_CORE,(0,0));"
            f"n={HELPER_LENGTH};b=b''\n"
            "while len(b)<n:\n"
            " p=sys.stdin.buffer.read(n-len(b))\n"
            " if not p: sys.exit(1)\n"
            " b+=p\n"
            f"if hashlib.sha256(b).hexdigest()!={HELPER_SHA256!r}: sys.exit(1)\n"
            "exec(compile(b,'<owner-helper>','exec'),{'__name__':'__main__'})")
        command = [*DOCKER, 'exec', '--interactive', '--user', '0:0', self.identity[0],
                   '/usr/bin/env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'LANG=C.UTF-8',
                   'HOME=/dev/shm', 'TMPDIR=/dev/shm', '/usr/local/bin/python3', '-I', '-c', bootstrap]
        try:
            self.process = self.process_factory(command, stdin=subprocess.PIPE,
                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                env=dict(MINIMAL_ENV), close_fds=True, bufsize=0)
            self.input = _TimedPipe(self.process.stdin.fileno(), self.deadline)
            self.output = _TimedPipe(self.process.stdout.fileno(), self.deadline)
            self.input.write(self.source)
        except BaseException:
            self.abort()
            raise SafeError('privacy') from None

    def send(self, frame):
        write_frame(self.input, frame)

    def receive(self):
        return read_frame(self.output)

    def recheck(self):
        if self.identity is None or self._inspect() != self.identity:
            raise SafeError('identity')

    def finish(self):
        if self.process is None:
            raise SafeError('protocol')
        try:
            self.process.stdin.close()
            if self.output.read(1):
                raise SafeError('protocol')
            remaining = min(15, self.deadline - time.monotonic())
            if remaining <= 0 or self.process.wait(timeout=remaining) != 0:
                raise SafeError('cleanup')
            self.process.stdout.close()
        except subprocess.TimeoutExpired:
            raise SafeError('timeout') from None
        except OSError:
            raise SafeError('cleanup') from None

    def abort(self):
        if self.process is None:
            return
        failed = False
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                failed = True
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        except BaseException:
            failed = True
        finally:
            if self.process.stdout is not None:
                try:
                    self.process.stdout.close()
                except OSError:
                    failed = True
        if failed:
            raise SafeError('cleanup') from None


class OwnerTerminal:
    """Controlling foreground terminal only, without an echo fallback."""
    def __init__(self, deadline=None):
        self.deadline = deadline or time.monotonic() + 240
        self.fd = None
        try:
            if not all(os.isatty(fd) for fd in (0, 1, 2)):
                raise SafeError('privacy')
            if len({os.fstat(fd).st_rdev for fd in (0, 1, 2)}) != 1:
                raise SafeError('privacy')
            self.fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY | os.O_CLOEXEC)
            if any(os.tcgetpgrp(fd) != os.getpgrp() for fd in (0, 1, 2, self.fd)):
                raise SafeError('privacy')
            termios.tcgetattr(self.fd)
        except BaseException:
            self.close()
            raise SafeError('privacy') from None

    def read_secret(self, prompt):
        saved = termios.tcgetattr(self.fd)
        private = list(saved)
        private[3] &= ~(termios.ECHO | termios.ECHONL)
        data = bytearray()
        changed = False
        try:
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, private)
            changed = True
            os.write(self.fd, prompt.encode('ascii'))
            while True:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                    raise SafeError('timeout')
                char = os.read(self.fd, 1)
                if not char:
                    raise SafeError('privacy')
                if char == b'\n':
                    break
                if len(data) >= 4096:
                    raise SafeError('privacy')
                data.extend(char)
            return data.decode('utf-8', errors='strict')
        except (OSError, UnicodeError, termios.error):
            raise SafeError('privacy') from None
        finally:
            if changed:
                termios.tcsetattr(self.fd, termios.TCSAFLUSH, saved)
                os.write(self.fd, b'\n')

    def confirm_private_image(self, path):
        os.write(self.fd, ('Open this local PNG using private GUI access: ' + str(path) + '\n').encode('ascii'))
        return self.read_secret('Type PRIVATE after viewing the image privately: ') == 'PRIVATE'

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


INSTALLED_DIRECTORY = '/usr/local/libexec/audiobook-ops'
INSTALLED_LAUNCHER = INSTALLED_DIRECTORY + '/owner_rutracker_refresh.py'
INSTALLED_HELPER = INSTALLED_DIRECTORY + '/owner_rutracker_helper.py'
RUN_DIRECTORY = '/run/audiobook-ops-owner-session'
SECRET_DIRECTORY = '/etc/audiobook-ops/secrets'
MAX_RUNTIME_SECONDS = 600
HOST_CODES = HELPER_CODES | {'publication', 'publication_unknown', 'busy'}


def read_private_script(directory, name, uid):
    fd = None
    try:
        directory.recheck()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory.fd)
        before = os.fstat(fd)
        _regular_private(before, uid, 0o700)
        parts, size = [], 0
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            parts.append(part)
            size += len(part)
            if size > MAX_FRAME:
                raise SafeError('privacy')
        directory.recheck()
        after = os.stat(name, dir_fd=directory.fd, follow_symlinks=False)
        _regular_private(after, uid, 0o700)
        if (_inode(before) != _inode(after) or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns):
            raise SafeError('privacy')
        return b''.join(parts)
    except OSError:
        raise SafeError('privacy') from None
    finally:
        if fd is not None:
            os.close(fd)


def _installed_helper():
    if __file__ != INSTALLED_LAUNCHER:
        raise SafeError('privacy')
    directory = Directory(INSTALLED_DIRECTORY, 0, 0o700)
    try:
        read_private_script(directory, 'owner_rutracker_refresh.py', os.geteuid())
        helper = read_private_script(directory, 'owner_rutracker_helper.py', os.geteuid())
        if len(helper) != HELPER_LENGTH or hashlib.sha256(helper).hexdigest() != HELPER_SHA256:
            raise SafeError('identity')
        return helper
    finally:
        directory.close()


def require_tmpfs(path, mountinfo=None):
    try:
        if mountinfo is None:
            with open('/proc/self/mountinfo', 'r', encoding='ascii') as stream:
                mountinfo = stream.read(1048577)
        if len(mountinfo) > 1048576:
            raise SafeError('privacy')
        best, filesystem = '', None
        for line in mountinfo.splitlines():
            left, right = line.split(' - ', 1)
            mount = left.split()[4]
            for encoded, decoded in (('\\040', ' '), ('\\011', '\t'), ('\\012', '\n'), ('\\134', '\\')):
                mount = mount.replace(encoded, decoded)
            if (path == mount or path.startswith(mount.rstrip('/') + '/')) and len(mount) > len(best):
                best, filesystem = mount, right.split()[0]
        if filesystem != 'tmpfs':
            raise SafeError('privacy')
    except (OSError, ValueError, IndexError):
        raise SafeError('privacy') from None


def _make_runtime_base(parent, owner_gid):
    name = 'audiobook-ops-owner-session'
    created = False
    fd = None
    try:
        parent.recheck()
        try:
            os.mkdir(name, 0o700, dir_fd=parent.fd)
            created = True
        except FileExistsError:
            pass
        if created:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent.fd)
            os.fchown(fd, parent.uid, owner_gid)
            os.fchmod(fd, 0o710)
        return Directory(parent.path + '/' + name, parent.uid, 0o710,
                         anchor=parent.anchor, gid=owner_gid)
    except OSError:
        raise SafeError('privacy') from None
    finally:
        if fd is not None:
            os.close(fd)


def _runtime_directory(record):
    require_tmpfs(RUN_DIRECTORY)
    parent = Directory('/run', 0, 0o755)
    try:
        return _make_runtime_base(parent, record.pw_gid)
    finally:
        parent.close()


class _RefreshLock:
    """One persistent root-private inode; never unlink a flock lock file."""
    def __init__(self, directory):
        self.fd = None
        fd = None
        try:
            directory.recheck()
            fd = os.open('refresh.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                         os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=directory.fd)
            before = os.fstat(fd)
            _regular_private(before, directory.uid, 0o600, os.getegid())
            if before.st_size != 0:
                raise SafeError('privacy')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SafeError('busy') from None
            directory.recheck()
            after = os.stat('refresh.lock', dir_fd=directory.fd, follow_symlinks=False)
            _regular_private(after, directory.uid, 0o600, os.getegid())
            if _inode(before) != _inode(after):
                raise SafeError('privacy')
            self.fd, fd = fd, None
        except OSError:
            raise SafeError('privacy') from None
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


def _owner_run(terminal, record, source):
    base = secrets_directory = stage = publisher = lock = None
    primary = None
    cleanup_failed = False
    try:
        base = _runtime_directory(record)
        lock = _RefreshLock(base)
        secrets_directory = Directory(SECRET_DIRECTORY, 0, 0o700, gid=0)
        stage = Stage(base, record.pw_uid, record.pw_gid)
        publisher = Publisher(secrets_directory, record.pw_gid)
        refresh(terminal, DockerTransport(source), stage, publisher)
    except BaseException as error:
        primary = error if isinstance(error, SafeError) else SafeError('privacy')
    finally:
        if stage is not None:
            try:
                stage.cleanup()
            except BaseException:
                cleanup_failed = True
        try:
            terminal.close()
        except BaseException:
            cleanup_failed = True
        for directory in (secrets_directory, base):
            if directory is not None:
                try:
                    directory.close()
                except BaseException:
                    cleanup_failed = True
        if lock is not None:
            try:
                lock.close()
            except BaseException:
                cleanup_failed = True
    if publisher is not None and publisher.published and (primary or cleanup_failed):
        raise SafeError('publication_unknown') from None
    if primary or cleanup_failed:
        raise primary or SafeError('cleanup') from None


def _abort_signal(_number, _frame):
    raise SafeError('privacy')


def _timeout_signal(_number, _frame):
    raise SafeError('timeout')


def main():
    terminal = None
    completed = False
    previous_signals = {}
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        terminal = OwnerTerminal()
        record = pwd.getpwnam('nik')
        authorize(os.geteuid(), os.getuid(), record.pw_uid, record.pw_gid, os.environ)
        if len(sys.argv) != 1 or not sys.flags.isolated or __file__ != INSTALLED_LAUNCHER:
            raise SafeError('privacy')
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_signals[number] = signal.signal(number, _abort_signal)
        previous_signals[signal.SIGALRM] = signal.signal(signal.SIGALRM, _timeout_signal)
        signal.alarm(MAX_RUNTIME_SECONDS)
        os.environ.clear()
        source = _installed_helper()
        _owner_run(terminal, record, source)
        completed = True
        signal.alarm(0)
        os.write(1, b'owner-refresh: installed; reload pending\n')
        return 0
    except BaseException as error:
        code = ('publication_unknown' if completed else error.code
                if isinstance(error, SafeError) and type(error.code) is str and error.code in HOST_CODES else 'privacy')
        try:
            os.write(2, ('owner-refresh: ' + code + '\n').encode('ascii'))
        except OSError:
            pass
        return 1
    finally:
        if terminal is not None:
            try:
                terminal.close()
            except OSError:
                pass
        signal.alarm(0)
        for number, handler in previous_signals.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    raise SystemExit(main())
