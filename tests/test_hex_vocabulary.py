import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sync-hex-vocabulary.py'
spec = importlib.util.spec_from_file_location('sync_hex', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.data = {'handyCustomWords': ['Hex', 'Voxtype'], 'voxtypeReplacements': {'хекс': 'Hex', 'voxtype': 'Voxtype'}}
        self.desired = sync.desired_words(self.data)
        self.mode = {'name': 'Global', 'post_processing': {'prompt': 'private'}, 'replacements': [{'matched_phrase': 'manual', 'output': 'Manual'}]}
        self.current = [{'term': 'Hex', 'sounds_like': ['local']}, {'term': 'Unmanaged'}]

    def test_plan_preserves_manual_entries_and_self_alias(self):
        current = [{'term': 'Hex', 'sounds_like': ['local']}, {'term': 'Local', 'sounds_like': ['extra']}, {'term': 'Voxtype'}]
        self.assertEqual(sync.plan_sync(self.desired, current), [{'term': 'Hex', 'sounds_like': ['хекс']}])
        current[0]['sounds_like'].append('хекс')
        self.assertEqual(sync.plan_sync(self.desired, current), [])
        self.assertEqual(sync.plan_replacements(self.data, self.mode)[1], {'matched_phrase': 'voxtype', 'output': 'Voxtype'})

    def test_conflicts_detected_before_plan(self):
        with self.assertRaises(sync.SyncError):
            sync.plan_sync(self.desired, [{'term': 'Other', 'sounds_like': ['ХЕКС']}])
        with self.assertRaises(sync.SyncError):
            sync.plan_replacements(self.data, {'replacements': [{'matched_phrase': 'ХЕКС', 'output': 'Other'}]})
        with self.assertRaises(sync.SyncError):
            sync.desired_words({'handyCustomWords': ['Hex'], 'voxtypeReplacements': {'хекс': 'Missing'}})
        with self.assertRaises(sync.SyncError):
            sync.desired_words({'handyCustomWords': ['Hex', 'HEX'], 'voxtypeReplacements': {}})

    def test_limits(self):
        with self.assertRaises(sync.SyncError):
            sync.desired_words({'handyCustomWords': ['x' * 65], 'voxtypeReplacements': {}})
        with self.assertRaises(sync.SyncError):
            sync.plan_sync(self.desired, [{'term': 'Hex', 'sounds_like': [f'local{i}' for i in range(16)]}])

    def test_apply_and_readback_with_private_backup(self):
        state = {'entries': json.loads(json.dumps(self.current)), 'mode': json.loads(json.dumps(self.mode))}
        def fake_run(_exe, args, input_data=None):
            if args[:2] == ['vocabulary', 'list']:
                return {'version': 4, 'status': 'vocabulary', 'entries': state['entries']}
            if args[:2] == ['settings', 'get']:
                return {'version': 4, 'status': 'settings', 'settings': [{'key': 'dictation_processing.default_mode', 'value': state['mode']}]}
            if args[:2] == ['settings', 'apply']:
                state['mode'] = json.loads(input_data)['dictation_processing.default_mode']
                return {'version': 4, 'status': 'ok'}
            term = args[2]
            entry = next((e for e in state['entries'] if e['term'] == term), None)
            if not entry:
                entry = {'term': term, 'sounds_like': []}
                state['entries'].append(entry)
            if '--sounds-like' in args:
                entry.setdefault('sounds_like', []).extend(args[args.index('--sounds-like') + 1].split(','))
            return {'version': 4, 'status': 'ok'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(sync, 'run_hex', side_effect=fake_run):
            path = Path(sync.apply_plan('hex', self.data, self.desired, self.current, self.mode, sync.plan_sync(self.desired, self.current), sync.plan_replacements(self.data, self.mode), Path(tmp) / 'backup'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn('private', path.read_text())
            self.assertEqual(json.loads(path.read_text())['entries'][1]['term'], 'Unmanaged')
            self.assertEqual(sync.plan_sync(self.desired, state['entries']), [])
            self.assertEqual(sync.plan_replacements(self.data, state['mode']), [])
            self.assertEqual(state['entries'][0]['sounds_like'], ['local', 'хекс'])
            self.assertEqual(state['mode']['post_processing'], self.mode['post_processing'])

    def test_cli_failure_is_reported_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sync, 'run_hex', side_effect=sync.SyncError('failed')):
            with self.assertRaisesRegex(sync.SyncError, 'partial changes possible.*backup'):
                sync.apply_plan('hex', self.data, self.desired, self.current, self.mode, sync.plan_sync(self.desired, self.current), [], Path(tmp))

    def test_subprocess_error_never_prints_private_stderr(self):
        from types import SimpleNamespace
        with patch.object(sync.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='secret prompt')):
            with self.assertRaises(sync.SyncError) as failure:
                sync.run_hex('hex', ['settings', 'apply', '--json', '-'], '{}')
        self.assertNotIn('secret prompt', str(failure.exception))

    def test_concurrent_mode_change_refuses_apply(self):
        current = [{'term': 'Hex', 'sounds_like': ['хекс']}, {'term': 'Voxtype'}]
        changed = dict(self.mode, name='Changed')
        with tempfile.TemporaryDirectory() as tmp, patch.object(sync, 'read_current', return_value=current), patch.object(sync, 'read_mode', return_value=changed), patch.object(sync, 'run_hex') as run:
            with self.assertRaisesRegex(sync.SyncError, 'changed concurrently'):
                sync.apply_plan('hex', self.data, self.desired, current, self.mode, [], sync.plan_replacements(self.data, self.mode), Path(tmp))
            run.assert_not_called()

    def test_failed_readback_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sync, 'run_hex', return_value={'version': 4, 'status': 'ok'}), patch.object(sync, 'read_current', return_value=[]):
            with self.assertRaisesRegex(sync.SyncError, 'readback is incomplete'):
                sync.apply_plan('hex', self.data, self.desired, self.current, self.mode, sync.plan_sync(self.desired, self.current), [], Path(tmp))


if __name__ == '__main__':
    unittest.main()
