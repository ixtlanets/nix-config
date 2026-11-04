#!/usr/bin/env python3
"""Preview or add shared voice-typing terms through the running Hex CLI."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class SyncError(Exception):
    pass


def key(value):
    return value.casefold()


def phrase(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SyncError(f"Invalid {label}: expected a nonempty, trimmed string")
    if len(value) > 64:
        raise SyncError(f'Invalid {label}: exceeds Hex limit of 64 characters')
    if ',' in value:
        raise SyncError(f"Invalid {label}: commas are not supported by Hex CLI")
    return value


def desired_words(data):
    if not isinstance(data, dict) or not isinstance(data.get('handyCustomWords'), list) or not isinstance(data.get('voxtypeReplacements'), dict):
        raise SyncError('Invalid shared dictionary structure')
    terms = {}
    for word in data['handyCustomWords']:
        word = phrase(word, 'term')
        if key(word) in terms:
            raise SyncError(f'Duplicate term: {word}')
        terms[key(word)] = {'term': word, 'sounds_like': []}
    aliases = {}
    for alias, target in data['voxtypeReplacements'].items():
        alias, target = phrase(alias, 'alias'), phrase(target, 'target')
        if key(target) not in terms or terms[key(target)]['term'] != target:
            raise SyncError(f'Replacement target missing from handyCustomWords: {target}')
        if key(alias) in aliases:
            raise SyncError(f'Duplicate alias: {alias}')
        aliases[key(alias)] = target
        # Hex uses case-insensitive matching: self aliases aren't vocabulary spellings.
        if key(alias) != key(target):
            terms[key(target)]['sounds_like'].append(alias)
    if len(terms) > 500 or any(len(e['sounds_like']) > 16 for e in terms.values()):
        raise SyncError('Shared dictionary exceeds Hex vocabulary limits')
    return list(terms.values())


def plan_sync(desired, current):
    by_term = {}
    owners = {}
    for entry in current:
        if not isinstance(entry, dict):
            raise SyncError('Invalid Hex vocabulary entry')
        term = phrase(entry.get('term'), 'Hex term')
        if key(term) in by_term:
            raise SyncError(f'Duplicate Hex term: {term}')
        aliases = entry.get('sounds_like', [])
        if not isinstance(aliases, list):
            raise SyncError(f'Invalid Hex sounds_like for {term}')
        alias_keys = set()
        for alias in aliases:
            alias = phrase(alias, 'Hex alias')
            ak = key(alias)
            if ak in alias_keys:
                raise SyncError(f'Duplicate Hex alias for {term}: {alias}')
            if ak in owners and owners[ak] != key(term):
                raise SyncError(f'Conflicting Hex alias: {alias}')
            alias_keys.add(ak)
            owners[ak] = key(term)
        by_term[key(term)] = (term, alias_keys)
    if len(by_term) + sum(key(e['term']) not in by_term for e in desired) > 500:
        raise SyncError('Merged vocabulary exceeds 500 terms')
    plan = []
    for entry in desired:
        term = entry['term']
        existing = by_term.get(key(term))
        missing = []
        for alias in entry['sounds_like']:
            ak = key(alias)
            if ak in owners and owners[ak] != key(term):
                raise SyncError(f'Alias conflict: {alias} belongs to another term')
            if not existing or ak not in existing[1]:
                missing.append(alias)
        if len(missing) + (len(existing[1]) if existing else 0) > 16:
            raise SyncError(f'Merged vocabulary exceeds 16 aliases for {term}')
        if not existing or missing:
            plan.append({'term': existing[0] if existing else term, 'sounds_like': missing})
    return plan


def run_hex(executable, args, input_data=None):
    try:
        result = subprocess.run([executable, *args], check=False, capture_output=True, text=True, input=input_data)
    except OSError as exc:
        raise SyncError(f'Cannot execute Hex CLI: {exc}') from exc
    if result.returncode:
        raise SyncError(f'Hex CLI failed (exit {result.returncode}); no further changes attempted')
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise SyncError('Hex CLI returned invalid JSON') from exc
    if not isinstance(value, dict) or not isinstance(value.get('version'), int):
        raise SyncError('Unexpected Hex CLI reply')
    return value


def read_current(executable):
    value = run_hex(executable, ['vocabulary', 'list', '--json'])
    if value.get('status') != 'vocabulary' or not isinstance(value.get('entries'), list):
        raise SyncError('Unexpected Hex vocabulary reply')
    return value['entries']


def read_mode(executable):
    reply = run_hex(executable, ['settings', 'get', 'dictation_processing.default_mode', '--json'])
    items = reply.get('settings')
    if reply.get('status') != 'settings' or not isinstance(items, list) or len(items) != 1:
        raise SyncError('Unexpected Hex processing mode reply')
    item = items[0]
    if not isinstance(item, dict) or item.get('key') != 'dictation_processing.default_mode' or not isinstance(item.get('value'), dict):
        raise SyncError('Unexpected Hex processing mode reply')
    return item['value']


def plan_replacements(data, mode):
    rules = mode.get('replacements')
    if not isinstance(rules, list):
        raise SyncError('Invalid Hex processing replacements')
    known = {}
    for rule in rules:
        if not isinstance(rule, dict):
            raise SyncError('Invalid Hex replacement entry')
        alias = phrase(rule.get('matched_phrase'), 'Hex replacement alias')
        target = phrase(rule.get('output'), 'Hex replacement target')
        if key(alias) in known:
            raise SyncError(f'Duplicate Hex replacement alias: {alias}')
        known[key(alias)] = target
    missing = []
    for alias, target in data['voxtypeReplacements'].items():
        if key(alias) in known and key(known[key(alias)]) != key(target):
            raise SyncError(f'Replacement conflict for alias: {alias}')
        if key(alias) not in known:
            missing.append({'matched_phrase': alias, 'output': target})
    return missing


def mode_without_replacements(mode):
    return {k: v for k, v in mode.items() if k != 'replacements'}


def save_backup(entries, replacements, directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    fd, path = tempfile.mkstemp(prefix=f'vocabulary-{stamp}-', suffix='.json', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump({'entries': [{'term': e['term'], 'sounds_like': e.get('sounds_like', [])} for e in entries], 'replacements': [{'matched_phrase': r['matched_phrase'], 'output': r['output']} for r in replacements]}, output, ensure_ascii=False, indent=2)
            output.write('\n')
    except BaseException:
        os.unlink(path)
        raise
    return path


def apply_plan(executable, data, desired, current, mode, plan, rule_plan, backup_dir):
    if not plan and not rule_plan:
        return None
    backup = save_backup(current, mode['replacements'], backup_dir)
    try:
        for entry in plan:
            args = ['vocabulary', 'add', entry['term']]
            if entry['sounds_like']:
                args += ['--sounds-like', ','.join(entry['sounds_like'])]
            run_hex(executable, args + ['--json'])
        after = read_current(executable)
        preserved = [{'term': e['term'], 'sounds_like': e.get('sounds_like', [])} for e in current]
        if plan_sync(desired, after) or plan_sync(preserved, after):
            raise SyncError('Vocabulary readback is incomplete or previous terms were lost')
        live_mode = read_mode(executable)
        if live_mode != mode:
            raise SyncError('Processing mode changed concurrently; refusing to overwrite it')
        # Replan after vocabulary changes; keep the whole mode in memory only.
        missing = plan_replacements(data, live_mode)
        if missing:
            updated = dict(live_mode)
            updated['replacements'] = [*live_mode['replacements'], *missing]
            run_hex(executable, ['settings', 'apply', '--json', '-'], json.dumps({'dictation_processing.default_mode': updated}, ensure_ascii=False))
        verified = read_mode(executable)
        if mode_without_replacements(verified) != mode_without_replacements(mode):
            raise SyncError('Processing settings changed unexpectedly during sync')
        if plan_replacements(data, verified):
            raise SyncError('Processing replacements readback is incomplete')
        old = {key(r['matched_phrase']): r for r in mode['replacements']}
        now = {key(r['matched_phrase']): r for r in verified['replacements']}
        if any(now.get(k) != v for k, v in old.items()):
            raise SyncError('Previous processing replacements were not preserved')
    except SyncError as exc:
        raise SyncError(f'{exc}; partial changes possible; dictionary backup: {backup}') from exc
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--words', type=Path, default=Path(__file__).resolve().parents[1] / 'dotfiles/voice-typing/words.json')
    parser.add_argument('--hex', default=None, help='Path to Hex CLI')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Apply additive changes after backup')
    mode.add_argument('--check', action='store_true', help='Exit 1 if changes are needed')
    parser.add_argument('--backup-dir', type=Path, default=Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'hex-vocabulary')
    args = parser.parse_args(argv)
    try:
        executable = args.hex or shutil.which('hex')
        if not executable and sys.platform == 'darwin':
            executable = '/Applications/Hex.app/Contents/MacOS/hex'
        if not executable:
            raise SyncError('Hex CLI not found; specify --hex')
        with args.words.open(encoding='utf-8') as source:
            data = json.load(source)
        desired = desired_words(data)
        current = read_current(executable)
        mode_value = read_mode(executable)
        plan = plan_sync(desired, current)
        rule_plan = plan_replacements(data, mode_value)
        if args.apply:
            backup = apply_plan(executable, data, desired, current, mode_value, plan, rule_plan, args.backup_dir)
            print(f'Hex vocabulary verified; backup: {backup}' if backup else 'Hex vocabulary already up to date')
        else:
            print(json.dumps({'vocabulary_changes': plan, 'replacement_changes': rule_plan}, ensure_ascii=False, indent=2))
            if args.check and (plan or rule_plan):
                return 1
        return 0
    except (SyncError, OSError, ValueError) as exc:
        print(f'Hex vocabulary sync: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
