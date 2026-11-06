"""Offline DockerTransport admission; captured identity + synthetic topology/Env."""
import hashlib
import copy
import json
from pathlib import Path
import types
import subprocess
import unittest
from unittest.mock import patch

from test_owner_rutracker_refresh import owner, valid_inspect, SCRIPT


FIXTURES = Path(__file__).with_name('fixtures') / 'owner-image-identity'


def fixture(name, digest):
    raw = (FIXTURES / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise AssertionError('fixture raw SHA256 mismatch: ' + name)
    return json.loads(raw)


def manifest_container():
    captured = fixture('container-identity-projection.json',
                       '7758715b158796d49cbdfee8b724378d30a101c6d9d546755a7401846e2c184f')
    value = valid_inspect()  # Synthetic HostConfig/Mounts/Networks/Env, not captured.
    value.update({key: item for key, item in captured.items() if key != 'Config'})
    value['Config'] = dict(value['Config'], **captured['Config'])
    return value


def manifest_image():
    return fixture('image-projection.json',
                   'dd24599ec1364a0b2cb8805822c9bfab21fe0e8709f9789d6555d8a129c91d48')


class ImageAdmissionTests(unittest.TestCase):
    def transport(self, container=None, image=None, image_reply=None):
        container = manifest_container() if container is None else container
        image = manifest_image() if image is None else image
        calls, bootstrap = [], []

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[3:5] == ['image', 'inspect']:
                if image_reply is not None:
                    if isinstance(image_reply, Exception):
                        raise image_reply
                    return image_reply
                value = image
            elif argv[3:5] == ['network', 'inspect']:
                value = {'Name': 'audiobook-ops-backend', 'Id': 'b' * 64,
                         'Driver': 'bridge', 'Scope': 'local', 'Internal': False,
                         'Ingress': False, 'ConfigOnly': False}
            elif argv[3] == 'diff':
                return types.SimpleNamespace(returncode=0, stdout=b'')
            else:
                self.assertEqual(argv[3], 'inspect')
                value = container
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(value).encode())

        def factory(argv, **kwargs):
            bootstrap.append(argv)
            # Observe admission without executing Docker or privileged bootstrap.
            raise OSError('synthetic stop before bootstrap')

        transport = owner.DockerTransport(SCRIPT.with_name('owner_rutracker_helper.py').read_bytes(),
                                          runner=runner, process_factory=factory)
        return transport, calls, bootstrap

    def assert_denied(self, container=None, image=None, image_reply=None, code='identity'):
        transport, calls, bootstrap = self.transport(container, image, image_reply)
        with patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
            with self.assertRaises(owner.SafeError) as raised:
                transport.start()
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(bootstrap, [])
        self.assertIsNone(transport.identity)

    def assert_admitted(self, container, image):
        transport, calls, bootstrap = self.transport(container, image)
        with patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
            with self.assertRaises(owner.SafeError) as raised:
                transport.start()
        self.assertEqual(raised.exception.code, 'privacy')
        self.assertEqual(len(bootstrap), 1)
        return transport, calls, bootstrap

    def test_docker29_manifest_id_reaches_bootstrap_admission(self):
        transport, calls, bootstrap = self.transport()
        with patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
            with self.assertRaises(owner.SafeError) as raised:
                transport.start()
        self.assertEqual(raised.exception.code, 'privacy')  # Deliberate factory stop.
        self.assertEqual(len(bootstrap), 1)
        self.assertEqual(transport.identity[:4],
                         (manifest_container()['Id'], owner.EXPECTED_MANIFEST,
                          '2026-10-29T21:08:36.328329781Z', 3303))

    def test_public_manifest_raw_hash_establishes_config_relation(self):
        raw = (FIXTURES / 'pinned-manifest.json').read_bytes()
        self.assertEqual('sha256:' + hashlib.sha256(raw).hexdigest(), owner.EXPECTED_MANIFEST)
        self.assertEqual(len(raw), 2572)
        manifest = json.loads(raw)
        self.assertEqual(manifest['schemaVersion'], 2)
        self.assertEqual(manifest['mediaType'], 'application/vnd.oci.image.manifest.v1+json')
        self.assertNotIn('manifests', manifest)
        self.assertEqual(manifest['config']['mediaType'], 'application/vnd.oci.image.config.v1+json')
        self.assertEqual(manifest['config']['digest'], owner.EXPECTED_IMAGE)
        self.assertEqual(owner.EXPECTED_CONFIG_DIGEST, owner.EXPECTED_IMAGE)
        self.assertEqual(owner.EXPECTED_DESCRIPTOR,
                         {'digest': owner.EXPECTED_MANIFEST, 'size': len(raw),
                          'mediaType': manifest['mediaType']})

    def test_fixed_local_image_lookup_is_mandatory_before_bootstrap(self):
        transport, calls, bootstrap = self.assert_admitted(manifest_container(), manifest_image())
        image_calls = [(argv, kwargs) for argv, kwargs in calls if argv[3:5] == ['image', 'inspect']]
        self.assertEqual(len(image_calls), 1)
        argv, kwargs = image_calls[0]
        self.assertEqual(argv, [*owner.DOCKER, 'image', 'inspect', '--format',
                                owner.IMAGE_PROJECTION, owner.EXPECTED_REFERENCE])
        self.assertEqual(kwargs, {'stdin': subprocess.DEVNULL, 'stdout': subprocess.PIPE,
                                 'stderr': subprocess.DEVNULL, 'timeout': 15, 'check': False,
                                 'env': dict(owner.MINIMAL_ENV), 'close_fds': True})
        self.assertEqual(bootstrap[0][:7], [*owner.DOCKER, 'exec', '--interactive', '--user', '0:0'])
        self.assertEqual(bootstrap[0][7], manifest_container()['Id'])
        # The format uses only fields actually present in the production projection.
        self.assertEqual(owner.IMAGE_PROJECTION,
                         '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},'
                         '"Descriptor":{{json (index . "Descriptor")}},"Os":{{json .Os}},'
                         '"Architecture":{{json .Architecture}}}')

    def test_classic_config_id_requires_pinned_daemon_lookup(self):
        image = manifest_image()
        image['Id'] = owner.EXPECTED_IMAGE
        for descriptor in ('absent', None, image['Descriptor']):
            candidate = copy.deepcopy(image)
            if descriptor == 'absent':
                del candidate['Descriptor']
            else:
                candidate['Descriptor'] = descriptor
            with self.subTest(descriptor=descriptor):
                self.assert_admitted(valid_inspect(), candidate)

    def test_direct_classic_fixture_compatibility_does_not_admit_unproved_manifest(self):
        self.assertEqual(owner.inspect_identity(valid_inspect())[1], owner.EXPECTED_IMAGE)
        with self.assertRaises(owner.SafeError) as raised:
            owner.inspect_identity(manifest_container())
        self.assertEqual(raised.exception.code, 'identity')
        self.assert_denied(valid_inspect(), {})

    def test_pinned_config_image_does_not_authorize_substituted_actual_image(self):
        for actual in ('sha256:' + 'd' * 64, 'tag:latest', '', None):
            with self.subTest(actual=actual):
                container, image = manifest_container(), manifest_image()
                container['Image'] = image['Id'] = actual
                self.assertEqual(container['Config']['Image'], owner.EXPECTED_REFERENCE)
                self.assert_denied(container, image)

    def test_wrong_daemon_id_cannot_corroborate_either_store(self):
        for container in (manifest_container(), valid_inspect()):
            for actual in ('sha256:' + 'd' * 64, owner.EXPECTED_IMAGE, owner.EXPECTED_MANIFEST, None):
                if actual == container['Image']:
                    continue
                with self.subTest(container_id=container['Image'], daemon_id=actual):
                    self.assert_denied(container, dict(manifest_image(), Id=actual))

    def test_wrong_config_reference_is_denied_for_both_stores(self):
        for container in (manifest_container(), valid_inspect()):
            image = dict(manifest_image(), Id=container['Image'])
            for reference in ('ghcr.io/flaresolverr/flaresolverr:latest',
                              'ghcr.io/flaresolverr/flaresolverr@sha256:' + 'd' * 64,
                              'ghcr.io/flaresolverr/flaresolverr@' + owner.EXPECTED_IMAGE):
                invalid = copy.deepcopy(container)
                invalid['Config']['Image'] = reference
                with self.subTest(reference=reference, store=container['Image']):
                    self.assert_denied(invalid, image)

    def test_manifest_descriptor_is_required(self):
        for missing in ('absent', None, {}, []):
            image = manifest_image()
            if missing == 'absent':
                del image['Descriptor']
            else:
                image['Descriptor'] = missing
            with self.subTest(missing=missing):
                self.assert_denied(image=image)

    def test_wrong_descriptor_is_denied_for_both_stores(self):
        for container in (manifest_container(), valid_inspect()):
            for key, wrong in [('digest', 'sha256:' + 'd' * 64),
                               ('digest', owner.EXPECTED_IMAGE), ('size', 2571),
                               ('size', '2572'), ('size', True),
                               ('mediaType', 'application/vnd.oci.image.index.v1+json'),
                               ('mediaType', 'application/vnd.docker.distribution.manifest.list.v2+json')]:
                image = dict(manifest_image(), Id=container['Image'])
                image['Descriptor'][key] = wrong
                with self.subTest(store=container['Image'], key=key, wrong=wrong):
                    self.assert_denied(container, image)
            for key in ('digest', 'mediaType', 'size'):
                image = dict(manifest_image(), Id=container['Image'])
                del image['Descriptor'][key]
                with self.subTest(store=container['Image'], missing=key):
                    self.assert_denied(container, image)

    def test_repo_digest_evidence_is_required_for_both_stores(self):
        for container in (manifest_container(), valid_inspect()):
            for bad in ('absent', None, [], owner.EXPECTED_REFERENCE, [123],
                        ['ghcr.io/flaresolverr/flaresolverr:latest'],
                        ['ghcr.io/flaresolverr/flaresolverr@sha256:' + 'd' * 64]):
                image = dict(manifest_image(), Id=container['Image'])
                if bad == 'absent':
                    del image['RepoDigests']
                else:
                    image['RepoDigests'] = bad
                with self.subTest(store=container['Image'], bad=bad):
                    self.assert_denied(container, image)

    def test_missing_id_and_wrong_platform_are_denied(self):
        for container in (manifest_container(), valid_inspect()):
            for key, wrong in [('Id', None), ('Os', 'windows'), ('Architecture', 'arm64')]:
                image = dict(manifest_image(), Id=container['Image'])
                image[key] = wrong
                with self.subTest(store=container['Image'], key=key):
                    self.assert_denied(container, image)
                del image[key]
                self.assert_denied(container, image)

    def test_malformed_image_json_and_command_failures_stop_before_bootstrap(self):
        for raw in (b'', b'{', b'[]', b'null', b'\xff', b'x' * (owner.MAX_FRAME + 1)):
            with self.subTest(raw=raw[:16]):
                self.assert_denied(image_reply=types.SimpleNamespace(returncode=0, stdout=raw))
        self.assert_denied(image_reply=types.SimpleNamespace(returncode=1, stdout=json.dumps(manifest_image()).encode()))
        self.assert_denied(image_reply=OSError('synthetic command failure'))
        self.assert_denied(image_reply=subprocess.TimeoutExpired('synthetic command', 15), code='timeout')

    def test_duplicate_image_json_keys_stop_before_bootstrap(self):
        raw = json.dumps(manifest_image()).encode()
        raw = b'{"Id":"sha256:' + b'd' * 64 + b'",' + raw[1:]
        self.assert_denied(image_reply=types.SimpleNamespace(returncode=0, stdout=raw), code='protocol')

    def test_nonfinite_image_json_is_refused_even_in_extra_field(self):
        raw = json.dumps(dict(manifest_image(), extra=float('nan'))).encode()
        self.assert_denied(image_reply=types.SimpleNamespace(returncode=0, stdout=raw), code='identity')

    def test_drift_in_image_evidence_is_refused_on_recheck(self):
        for container in (manifest_container(), valid_inspect()):
            for change in ('Id', 'Descriptor', 'RepoDigests', 'Os', 'Architecture'):
                image = dict(manifest_image(), Id=container['Image'])
                transport, calls, bootstrap = self.transport(container, image)
                with patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
                    transport.identity = transport._inspect()
                    if change == 'RepoDigests':
                        # Still independently valid, but the retained proof changed.
                        image[change].append('fixture.invalid/other@' + owner.EXPECTED_MANIFEST)
                    elif change == 'Descriptor':
                        image[change]['size'] = 123
                    else:
                        image[change] = 'changed'
                    with self.subTest(store=container['Image'], change=change):
                        with self.assertRaises(owner.SafeError) as raised:
                            transport.recheck()
                        self.assertEqual(raised.exception.code, 'identity')
                self.assertEqual(bootstrap, [])

    def test_store_shape_drift_is_refused_even_when_each_proof_is_valid(self):
        container, image = manifest_container(), manifest_image()
        transport, calls, bootstrap = self.transport(container, image)
        with patch.object(owner, 'namespace_identity', return_value=((4, 11), (4, 12))):
            transport.identity = transport._inspect()
            container['Image'] = image['Id'] = owner.EXPECTED_IMAGE
            with self.assertRaises(owner.SafeError) as raised:
                transport.recheck()
        self.assertEqual(raised.exception.code, 'identity')
        self.assertEqual(bootstrap, [])


if __name__ == '__main__':
    unittest.main()
