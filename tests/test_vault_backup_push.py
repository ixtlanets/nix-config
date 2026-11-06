#!/usr/bin/env python3
"""Run the real backup shell script against tiny data and fake network/crypto."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(os.environ.get('VAULT_BACKUP_SCRIPT', Path(__file__).resolve().parents[1] / 'dotfiles/omarchy/bin/vault-backup-push'))


class BackupDeliveryTest(unittest.TestCase):
    def test_stalled_receiver_cannot_block_local_commit_and_other_receivers(self):
        with tempfile.TemporaryDirectory(prefix='vault-backup-test-') as directory:
            root = Path(directory)
            home, bin_dir = root / 'home', root / 'bin'
            backup = home / 'backups/vault'
            backup.mkdir(parents=True)
            bin_dir.mkdir()
            (home / 'vault/tools').mkdir(parents=True)
            (home / 'vault/note.md').write_text('tiny fixture\n')
            (home / '.history-base').mkdir(mode=0o700)
            (home / 'vault/tools/history_backup.py').write_text('''import pathlib, sys
command = sys.argv[1]
if command == 'snapshot':
    pathlib.Path(sys.argv[sys.argv.index('--output') + 1]).mkdir()
elif command == 'validate-stream':
    sys.stdout.buffer.write(sys.stdin.buffer.read())
''')
            for day in ('01', '02', '03'):
                path = backup / f'vault-2026-10-{day}.tar.zst.gpg'
                path.write_bytes(b'previous verified artifact')
                os.utime(path, (1, 1))
            stubs = {
                'date': '#!/bin/sh\nprintf "2026-11-05\\n"\n',
                'zstd': '#!/bin/sh\ncat\n',
                'gpg': '''#!/bin/bash
while (($#)); do
  if [[ "$1" == --output ]]; then shift; cat > "$1"; [[ ${TEST_ASSEMBLY_FAIL:-0} != 1 ]]; exit; fi
  shift
done
exit 2
''',
                'ssh': r'''#!/bin/bash
printf '%s\\n' "$*" >> "$TEST_CALLS"
if [[ "$*" == *nik@um790pro* ]]; then sleep 10; exit 1; fi
if [[ "$*" == *df\ -Pk* ]]; then echo 999999999; fi
exit 0
''',
                'rsync': '#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_CALLS"\nexit 1\n',
                # Production per-destination limits become deterministic fractions
                # of a second. The outer subprocess deadline models systemd.
                'timeout': '#!/bin/bash\n[[ $1 != --* ]] || shift; shift; exec /usr/bin/timeout --kill-after=.1s .2s "$@"\n',
            }
            for name, body in stubs.items():
                executable = bin_dir / name
                executable.write_text(body)
                executable.chmod(0o755)
            legacy = backup / '.incoming-vault-2026-10-31.tar.zst.gpg'
            legacy.write_bytes(b'legacy artifact with unknown completion status')
            stale = backup / '.assembling-vault-2026-11-04.tar.zst.gpg'
            stale.write_bytes(b'incomplete new protocol assembly')
            calls = root / 'calls'
            env = dict(os.environ, HOME=str(home), PATH=f'{bin_dir}:{os.environ["PATH"]}', TEST_CALLS=str(calls))
            failed = subprocess.run(['bash', str(SCRIPT)], env=dict(env, TEST_ASSEMBLY_FAIL='1'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1.5)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(len(list(backup.glob('vault-*.tar.zst.gpg'))), 3)
            self.assertEqual(list(backup.glob('.assembling-*')), [])
            self.assertFalse(calls.exists(), 'failed assembly must not start delivery')
            self.assertTrue(legacy.exists())
            process = subprocess.Popen(['bash', str(SCRIPT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                output, _ = process.communicate(timeout=1.5)
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate()
            self.assertTrue((backup / 'vault-2026-11-05.tar.zst.gpg').exists(), f'verified local archive stranded in .incoming by stalled receiver:\n{output.decode()}\n{sorted(p.name for p in backup.iterdir())}')
            self.assertLessEqual(len(list(backup.glob('vault-*.tar.zst.gpg'))), 3)
            self.assertEqual(list(backup.glob('.assembling-*')), [])
            self.assertEqual(legacy.read_bytes(), b'legacy artifact with unknown completion status')
            self.assertIn('nik@moscow', calls.read_text())
            self.assertIn('ubuntu@london', calls.read_text())
            self.assertNotEqual(process.returncode, 0, 'remote failures must remain visible')


class RemoteDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='vault-delivery-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin_dir = self.root / 'bin'
        self.bin_dir.mkdir()
        self.remote = self.root / 'remote'
        self.backup = self.remote / 'backups/vault'
        self.backup.mkdir(parents=True)
        self.archive = self.root / 'vault-2026-11-05.tar.zst.gpg'
        self.archive.write_bytes(b'new encrypted fixture')
        self.old = self.backup / 'vault-2026-11-01.tar.zst.gpg'
        self.old.write_bytes(b'last known good encrypted artifact')
        self.env = dict(os.environ, PATH=f'{self.bin_dir}:{os.environ["PATH"]}', TEST_REMOTE=str(self.remote), TEST_CALLS=str(self.root / 'calls'))
        self.write_stub('ssh', r'''#!/bin/bash
while [[ $1 == -o ]]; do shift 2; done
shift
export HOME="$TEST_REMOTE"
if [[ $# == 1 ]]; then exec bash -c "$1"; fi
exec "$@"
''')
        self.write_stub('rsync', r'''#!/bin/bash
printf '%s\n' "$*" >> "$TEST_CALLS"
args=("$@")
source="${args[-2]}"
target="${args[-1]#*:}"
mkdir -p "$(dirname "$TEST_REMOTE/$target")"
if [[ ${TEST_INTERRUPT:-0} == 1 ]]; then
  head -c 3 "$source" > "$TEST_REMOTE/$target"
  exit 23
fi
if [[ ${TEST_CORRUPT:-0} == 1 ]]; then
  printf 'corrupted payload' > "$TEST_REMOTE/$target"
  exit 0
fi
cp -- "$source" "$TEST_REMOTE/$target"
''')
        self.write_stub('df', '#!/bin/bash\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted on\\nfixture 999999999 0 ${TEST_FREE_KB:-999999999} 1%% /\\n"\n')

    def write_stub(self, name, body):
        path = self.bin_dir / name
        path.write_text(body)
        path.chmod(0o755)

    def deliver(self, **settings):
        # Source the exact production delivery boundary; no network or crypto.
        result = subprocess.run(['bash', '-c', 'source "$1"; deliver_backup nik@fixture 3 "$2"', 'fixture', str(SCRIPT), str(self.archive)], env=dict(self.env, **settings), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3)
        self.output = result.stdout.decode()
        return result.returncode

    def test_no_space_preserves_last_good_archive(self):
        self.assertNotEqual(self.deliver(TEST_FREE_KB='0'), 0, self.output)
        self.assertEqual(self.old.read_bytes(), b'last known good encrypted artifact')
        self.assertFalse((self.root / 'calls').exists(), 'must reject before rsync')
        self.assertIn('insufficient space', self.output)

    def test_interrupted_upload_is_hidden_and_resume_publishes_only_verified_data(self):
        self.assertNotEqual(self.deliver(TEST_INTERRUPT='1'), 0, self.output)
        final = self.backup / self.archive.name
        self.assertFalse(final.exists())
        self.assertTrue(self.old.exists())
        self.assertEqual((self.backup / f'.upload-{self.archive.name}').read_bytes(), b'new')
        self.assertEqual(self.deliver(), 0, self.output)
        self.assertEqual(final.read_bytes(), self.archive.read_bytes())
        self.assertTrue((self.backup / f'{self.archive.name}.sha256').exists())
        self.assertFalse((self.backup / f'.upload-{self.archive.name}').exists())
        self.assertTrue(self.old.exists(), 'unmarked legacy archive needs manual classification')

    def test_checksum_failure_does_not_publish(self):
        self.assertNotEqual(self.deliver(TEST_CORRUPT='1'), 0, self.output)
        self.assertFalse((self.backup / self.archive.name).exists())
        self.assertTrue(self.old.exists())
        self.assertIn('SHA256 mismatch', self.output)

    def test_wrong_sized_legacy_final_is_rejected_without_hashing(self):
        final = self.backup / self.archive.name
        final.write_bytes(b'partial')
        hash_log = self.root / 'remote-hashes'
        self.write_stub('sha256sum', r'''#!/bin/bash
if [[ "$PWD" == "$TEST_REMOTE/backups/vault" ]]; then
  printf '%s\n' "$*" >> "$TEST_HASH_LOG"
fi
exec /usr/bin/sha256sum "$@"
''')
        self.assertNotEqual(self.deliver(TEST_FREE_KB='0', TEST_HASH_LOG=str(hash_log)), 0, self.output)
        self.assertIn('insufficient space', self.output)
        self.assertFalse(hash_log.exists(), 'obviously partial legacy files should not incur a full remote read')
        self.assertEqual(final.read_bytes(), b'partial')
        self.assertTrue(self.old.exists())

    def test_matching_legacy_final_is_adopted_before_space_check(self):
        final = self.backup / self.archive.name
        final.write_bytes(self.archive.read_bytes())
        self.assertEqual(self.deliver(TEST_FREE_KB='0'), 0, self.output)
        self.assertFalse((self.root / 'calls').exists(), 'matching finalized archive should not be retransferred')
        self.assertTrue((self.backup / f'{self.archive.name}.sha256').exists())

    def test_remote_rotation_counts_only_verified_artifacts(self):
        import hashlib
        for day in ('01', '02', '03'):
            archive = self.backup / f'vault-2026-10-{day}.tar.zst.gpg'
            archive.write_bytes(b'previous verified artifact')
            archive.with_name(f'{archive.name}.sha256').write_text(f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n')
        self.assertEqual(self.deliver(), 0, self.output)
        self.assertFalse((self.backup / 'vault-2026-10-01.tar.zst.gpg').exists())
        self.assertEqual(len(list(self.backup.glob('*.sha256'))), 3)
        self.assertTrue(self.old.exists())


class ImmutableRetryTest(unittest.TestCase):
    def test_same_day_and_explicit_retry_do_not_rebuild_archive(self):
        with tempfile.TemporaryDirectory(prefix='vault-retry-test-') as directory:
            root = Path(directory)
            home, bin_dir = root / 'home', root / 'bin'
            backup = home / 'backups/vault'
            backup.mkdir(parents=True)
            (home / 'vault').mkdir()
            (home / '.history-base/backup-work').mkdir(parents=True, mode=0o700)
            bin_dir.mkdir()
            archive = backup / 'vault-2026-11-05.tar.zst.gpg'
            archive.write_bytes(b'immutable encrypted artifact')
            old = backup / 'vault-2026-10-23.tar.zst.gpg'
            old.write_bytes(b'preserved older artifact')
            for day in ('01', '02'):
                (backup / f'vault-2026-11-{day}.tar.zst.gpg').write_bytes(b'older artifact')
            for name, body in {
                'date': '#!/bin/bash\necho 2026-11-05\n',
                'python3': '#!/bin/bash\nif [[ $1 == - ]]; then exec /usr/bin/python3 "$@"; fi\necho "unexpected history rebuild" >&2; exit 99\n',
                'gpg': '#!/bin/bash\necho "unexpected encryption" >&2; exit 99\n',
                'timeout': '#!/bin/bash\nexit 1\n',
            }.items():
                path = bin_dir / name
                path.write_text(body)
                path.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=f'{bin_dir}:{os.environ["PATH"]}')
            for arguments in (['--retry-delivery'], []):
                result = subprocess.run(['bash', str(SCRIPT), *arguments], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=2)
                self.assertEqual(result.returncode, 1, result.stdout.decode())
                self.assertIn(b'reusing finalized local archive', result.stdout)
                self.assertNotIn(b'unexpected', result.stdout)
                self.assertEqual(archive.read_bytes(), b'immutable encrypted artifact')
                if arguments:
                    self.assertTrue(old.exists(), 'delivery-only retry must not perform local rotation')
                else:
                    self.assertLessEqual(len(list(backup.glob('vault-*.tar.zst.gpg'))), 3)


if __name__ == '__main__':
    unittest.main()
