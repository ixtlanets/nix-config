#!/usr/bin/env python3
"""Read-only local OpenClaw usage audit; never emits conversation bodies.

python3 docs/research/openclaw-five-hour-usage.py --quick
python3 docs/research/openclaw-five-hour-usage.py --write
Only --write replaces the companion JSON and Markdown deliverables.
"""
import argparse
import bisect
import collections
import ctypes
import ctypes.util
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

ROOT = Path('/home/nik/.openclaw')
OUT = Path(__file__).resolve().parent
UTC = dt.timezone.utc
MOSCOW = ZoneInfo('Europe/Moscow')
HOURS5 = 18_000_000
REFERENCE = 43_330


class Zstd:
    def __init__(self):
        self.lib = ctypes.CDLL(ctypes.util.find_library('zstd'))
        self.lib.ZSTD_decompressBound.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.ZSTD_decompressBound.restype = ctypes.c_ulonglong
        self.lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.ZSTD_decompress.restype = ctypes.c_size_t
        self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        self.lib.ZSTD_isError.restype = ctypes.c_uint

    def decode(self, blob):
        n = self.lib.ZSTD_decompressBound(blob, len(blob))
        if n > 512 * 1024**2:
            raise ValueError('zstd decompressed bound exceeds safety cap')
        dest = ctypes.create_string_buffer(n)
        size = self.lib.ZSTD_decompress(dest, n, blob, len(blob))
        if self.lib.ZSTD_isError(size):
            raise ValueError('zstd decompression failed')
        return dest.raw[:size]


def connect(path):
    c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    c.execute('PRAGMA query_only=ON')
    c.execute('BEGIN')  # consistent per-database WAL-aware read transaction
    return c


def millis(value):
    if isinstance(value, (int, float)):
        return int(value if value > 10**11 else value * 1000)
    if isinstance(value, str):
        try:
            return int(dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)
        except ValueError:
            return None
    return None


def iso(value, zone=UTC):
    return dt.datetime.fromtimestamp(value / 1000, UTC).astimezone(zone).isoformat(timespec='milliseconds') if value is not None else None


def price(usage, timestamp, scenario='schedule'):
    """Normalized pi usage: input excludes cacheRead; output includes reasoning."""
    inp = max(0, usage.get('input', 0)) + max(0, usage.get('cacheWrite', 0))
    cache = max(0, usage.get('cacheRead', 0))
    output = max(0, usage.get('output', 0))
    t = dt.datetime.fromtimestamp(timestamp / 1000, UTC)
    peak = t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)
    factor = 2 if scenario == 'all_peak' or (scenario == 'schedule' and peak) else 1
    if scenario == 'no_cache':
        inp += cache
        cache = 0
        factor = 2 if peak else 1
    return factor * (inp * .15 + output * .60 + cache * .003) / 1_000_000


def window_summary(rows, weight=None, top=5):
    """All endpoint-anchored (end-5h,end] windows; exact, no fixed buckets."""
    rows = sorted(rows, key=lambda r: r['t'])
    if not rows:
        return {'calls': 0, 'maximum': None, 'top_nonoverlapping': [], 'endpoint_windows_above_20': 0}
    times = [r['t'] for r in rows]
    prefix = [0.0]
    for r in rows:
        prefix.append(prefix[-1] + (r[weight] if weight else 1))
    candidates = []
    left = 0
    for right, t in enumerate(times):
        while times[left] <= t - HOURS5:
            left += 1
        value = prefix[right + 1] - prefix[left]
        candidates.append((value, t, left, right + 1))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    def describe(x):
        value, end, lo, hi = x
        d = {'start_exclusive_utc': iso(end - HOURS5), 'end_inclusive_utc': iso(end),
             'start_exclusive_moscow': iso(end - HOURS5, MOSCOW), 'end_inclusive_moscow': iso(end, MOSCOW),
             'count': hi - lo, 'percent_43330': (hi - lo) / REFERENCE * 100,
             'by_group': dict(collections.Counter(r['group'] for r in rows[lo:hi])),
             'all_zero_usage_records': sum(not any(r.get('usage', {}).get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite']) for r in rows[lo:hi])}
        if weight:
            d['usd'] = value
        return d
    chosen = []
    for x in candidates:
        if all(x[1] <= y[1] - HOURS5 or x[1] - HOURS5 >= y[1] for y in chosen):
            chosen.append(x)
            if len(chosen) == top:
                break
    return {'calls': len(rows), 'first_utc': iso(times[0]), 'last_utc': iso(times[-1]),
            'maximum': describe(candidates[0]), 'top_nonoverlapping': [describe(x) for x in chosen],
            'endpoint_windows_above_20': sum(x[0] > 20 + 1e-9 for x in candidates) if weight else None,
            'total_usd': prefix[-1] if weight else None}


def candidates(quick):
    live = sorted(ROOT.glob('agents/*/agent/openclaw-agent.sqlite'))
    if quick:
        return live
    backups = sorted(ROOT.glob('agents/*/agent/openclaw-agent.sqlite.pre-*.bak'))
    backups += sorted(ROOT.glob('agents/*/agent.nocow-*/openclaw-agent.sqlite'))
    backups += sorted(ROOT.glob('state/openclaw.sqlite*.bak'))
    backups += sorted(ROOT.glob('update-prep-*/sqlite-snapshots/*/database.sqlite'))
    return live + backups


def audit(quick=False):
    zstd = Zstd()
    registry = set()
    state = connect(ROOT / 'state/openclaw.sqlite')
    for key, in state.execute('SELECT child_session_key FROM subagent_runs'):
        registry.add(key)
    state.close()
    native_coverage = {}
    native_state = ROOT / 'agents/main/agent/codex-home/state_5.sqlite'
    if native_state.is_file():
        nc = connect(native_state)
        native_coverage['main_codex_state_threads'] = nc.execute('SELECT count(*) FROM threads').fetchone()[0]
        nc.close()
    native_coverage['main_codex_sessions_directory_exists'] = (ROOT / 'agents/main/agent/codex-home/sessions').is_dir()
    native_coverage['acpx_codex_sessions_directory_exists'] = (ROOT / 'acpx/codex-home/sessions').is_dir()
    calls = {}
    native = {}
    sources = []
    diagnostics = collections.Counter()
    excluded = collections.Counter()
    event_types = collections.Counter()
    usage_states = collections.Counter()
    errors = []
    archive_hashes = set()
    all_event_min = None
    all_event_max = None
    event_seen = set()
    missing_usage_models = collections.Counter()
    custom_errors = collections.Counter()
    snapshot_checks = collections.Counter()
    seen_responses = set()
    seen_call_timestamps = set()

    def accept(e, agent, sid, skey, subagent, fallback_t, source_stats):
        nonlocal all_event_min, all_event_max
        if not isinstance(e, dict):
            diagnostics['non_object_events'] += 1
            return
        kind = e.get('type', 'unknown')
        t = millis(e.get('timestamp')) or fallback_t
        # Dedupe source copies, archives and fork-inherited history using event id + original time.
        event_id = e.get('id') or hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()
        event_key = (agent, event_id, t)
        if event_key in event_seen:
            source_stats['duplicate_events'] += 1
            return
        event_seen.add(event_key)
        source_stats['unique_events_added'] += 1
        event_types[kind] += 1
        if t is not None:
            all_event_min = min(all_event_min, t) if all_event_min is not None else t
            all_event_max = max(all_event_max, t) if all_event_max is not None else t
        if kind != 'message':
            if e.get('customType') == 'openclaw:prompt-error':
                custom_errors['events'] += 1
                error_text = json.dumps((e.get('data') or {}).get('error')).lower()
                if any(s in error_text for s in ['429', 'rate limit', 'rate_limit', 'too many requests', 'quota', 'usage limit', 'credit', 'balance', 'capacity', 'budget']):
                    custom_errors['quota_or_rate_markers'] += 1
            return
        m = e.get('message') or {}
        if not isinstance(m, dict) or m.get('role') != 'assistant':
            return
        provider, model, api = m.get('provider'), m.get('model'), m.get('api')
        meta = m.get('__openclaw') or {}
        usage = m.get('usage') or {}
        t = millis(m.get('timestamp')) or t
        if t is None:
            diagnostics['assistant_missing_timestamp'] += 1
            return
        group = agent + (':subagent' if subagent or ':subagent:' in skey or skey in registry else ':root')
        row = {'t': t, 'agent': agent, 'group': group, 'provider': provider, 'model': model,
               'stop_reason': m.get('stopReason'), 'usage': usage, 'event_id': event_id,
               'session_id': sid, 'response_id': m.get('responseId')}
        if provider == 'openclaw' or api == 'openclaw-transcript':
            excluded['synthetic_openclaw_messages'] += 1
            return
        if meta.get('mirrorOrigin'):
            excluded['native_mirrored_messages'] += 1
            # These are run/turn-level aggregates, NOT one request each.
            if any(usage.get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite']):
                nkey = (agent, meta.get('runId') or sid, meta.get('mirrorIdentity') or event_id)
                native[nkey] = row
            return
        if api == 'realtime':
            excluded['realtime_voice_messages_not_text_requests'] += 1
            return
        if not provider or not model or not api:
            excluded['assistant_missing_model_metadata'] += 1
            return
        key = (agent, event_id, t, provider, model)
        if key in calls:
            diagnostics['duplicate_call_identity'] += 1
            return
        calls[key] = row
        if row['response_id']:
            seen_responses.add((agent, provider, row['response_id']))
        seen_call_timestamps.add((agent, provider, model, t))
        source_stats['unique_calls_added'] += 1
        states = usage.get('usageReport', {})
        usage_states[states.get('state', 'legacy_unspecified') if isinstance(states, dict) else 'unknown'] += 1
        if not all(isinstance(usage.get(k), (int, float)) for k in ['input', 'output', 'cacheRead', 'cacheWrite']):
            missing_usage_models[str((provider, model))] += 1
        err = m.get('errorMessage') or ''
        if not isinstance(err, str):
            err = json.dumps(err)
        lower = err.lower()
        # Never store raw error text: it can contain prompts, URLs or request headers.
        tags = []
        if '429' in lower:
            tags.append('http_429')
        if any(s in lower for s in ['rate limit', 'rate_limit', 'ratelimit', 'too many requests']):
            tags.append('rate_limit')
        if any(s in lower for s in ['quota', 'usage limit', 'insufficient_quota', 'credit', 'balance', 'budget', 'capacity']):
            tags.append('quota_or_capacity')
        if tags:
            errors.append({'timestamp_utc': iso(t), 'timestamp_moscow': iso(t, MOSCOW),
                           'agent': agent, 'provider': provider, 'model': model, 'event_id': event_id,
                           'session_id': sid, 'tags': tags, 'stop_reason': m.get('stopReason')})

    for path in candidates(quick):
        c = connect(path)
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        s = collections.Counter()
        info = {'path': str(path), 'stats': s}
        if 'transcript_events' not in tables:
            info['skip'] = 'no transcript_events table'
            sources.append(info)
            c.close()
            continue
        meta = c.execute('SELECT agent_id FROM schema_meta WHERE agent_id IS NOT NULL LIMIT 1').fetchone() if 'schema_meta' in tables else None
        agent = meta[0] if meta else (path.parts[path.parts.index('agents') + 1] if 'agents' in path.parts else 'unknown')
        info['agent'] = agent
        cols = {r[1] for r in c.execute('PRAGMA table_info(transcript_events)')}
        wincols = {r[1] for r in c.execute('PRAGMA table_info(session_windows)')}
        subfields = [name for name in ['parent_session_key', 'spawned_by'] if name in wincols]
        windows = {}
        for r in c.execute('SELECT session_id, session_key' + ''.join(', ' + f for f in subfields) + ' FROM session_windows'):
            # parent_session_key alone can denote fork, not necessarily a spawned worker.
            windows[r[0]] = (r[1], bool(r[2 + subfields.index('spawned_by')]) if 'spawned_by' in subfields else False)
        info['session_windows'] = len(windows)
        query = 'SELECT session_id, event_json, ' + ('event_zstd' if 'event_zstd' in cols else 'NULL') + ', created_at FROM transcript_events'
        for sid, raw, compressed, created in c.execute(query):
            s['transcript_rows'] += 1
            if raw is None:
                raw = zstd.decode(compressed)
                s['zstd_rows'] += 1
            skey, subagent = windows.get(sid, ('', False))
            accept(json.loads(raw), agent, sid, skey, subagent, created, s)
        if 'session_transcript_archives' in tables:
            for sid, skey, encoding, blob, digest, created in c.execute('SELECT session_id,session_key,encoding,archive_blob,archive_sha256,created_at FROM session_transcript_archives'):
                s['archive_records'] += 1
                if digest in archive_hashes:
                    s['duplicate_archive_blobs'] += 1
                    continue
                archive_hashes.add(digest)
                raw = zstd.decode(blob) if encoding == 'zstd' else blob
                assert hashlib.sha256(raw).hexdigest() == digest or hashlib.sha256(blob).hexdigest() == digest, 'archive hash mismatch'
                for line in raw.splitlines():
                    if line.strip():
                        s['archive_events'] += 1
                        accept(json.loads(line), agent, sid, skey, windows.get(sid, ('', False))[1], created, s)
        if 'trajectory_runtime_events' in tables:
            # Run-level usage is not an extra request. Check the surviving per-call snapshots
            # only for response metadata absent from the transcript union.
            for raw, in c.execute("SELECT event_json FROM trajectory_runtime_events WHERE json_extract(event_json,'$.type')='model.completed'"):
                event = json.loads(raw)
                data = event.get('data')
                if not isinstance(data, dict) or not isinstance(data.get('messagesSnapshot'), list):
                    snapshot_checks['truncated_or_absent_snapshots'] += 1
                    continue
                snapshot_checks['model_completed_events'] += 1
                for m in data['messagesSnapshot']:
                    if not isinstance(m, dict) or m.get('role') != 'assistant' or m.get('provider') == 'openclaw':
                        continue
                    if isinstance(m.get('__openclaw'), dict) and m['__openclaw'].get('mirrorOrigin'):
                        continue
                    snapshot_checks['assistant_metadata_records'] += 1
                    rid, t = m.get('responseId'), millis(m.get('timestamp'))
                    matched = (rid and (agent, m.get('provider'), rid) in seen_responses) or (agent, m.get('provider'), m.get('model'), t) in seen_call_timestamps
                    if matched:
                        snapshot_checks['matched_transcript_responses'] += 1
                    else:
                        snapshot_checks['unmatched_or_truncated_response_metadata'] += 1
        if 'session_transcript_cold_archives' in tables:
            info['cold_archive_records'] = c.execute('SELECT count(*) FROM session_transcript_cold_archives').fetchone()[0]
            if info['cold_archive_records']:
                diagnostics['unprocessed_cold_archives'] += info['cold_archive_records']
        sources.append(info)
        c.close()

    rows = sorted(calls.values(), key=lambda r: r['t'])
    usage_rows = [r for r in rows if all(isinstance(r['usage'].get(k), (int, float)) for k in ['input', 'output', 'cacheRead', 'cacheWrite'])]
    for r in usage_rows:
        for scenario in ['schedule', 'all_offpeak', 'all_peak', 'no_cache']:
            r[scenario] = price(r['usage'], r['t'], scenario)
    # Conservatively identify duplicate provider response IDs, without assuming one ID always equals one call.
    response_counts = collections.Counter((r['provider'], r['response_id']) for r in rows if r['response_id'])
    diagnostics['repeated_nonempty_provider_response_ids'] = sum(n - 1 for n in response_counts.values() if n > 1)
    diagnostics['calls_without_response_id'] = sum(not r['response_id'] for r in rows)
    diagnostics['usage_missing_or_non_numeric'] = len(rows) - len(usage_rows)
    diagnostics['all_zero_usage_calls'] = sum(not any(r['usage'].get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite']) for r in usage_rows)
    diagnostics['cache_write_nonzero_calls'] = sum(r['usage'].get('cacheWrite', 0) > 0 for r in usage_rows)
    diagnostics['native_nonzero_usage_records'] = len(native)
    diagnostics['all_zero_usage_successful_calls'] = sum(r['stop_reason'] in ['stop', 'toolUse', 'length'] and not any(r['usage'].get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite']) for r in usage_rows)
    diagnostics['usage_component_total_mismatches'] = sum(sum(r['usage'].get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite']) != r['usage'].get('totalTokens') for r in usage_rows)
    calendar_costs = collections.defaultdict(lambda: {'calls': 0, 'schedule_usd': 0.0})
    for r in usage_rows:
        month = dt.datetime.fromtimestamp(r['t'] / 1000, UTC).strftime('%Y-%m')
        calendar_costs[month]['calls'] += 1
        calendar_costs[month]['schedule_usd'] += r['schedule']
    # Independent binary-search oracle for the rolling maxima (separate from the two-pointer implementation).
    times = [r['t'] for r in rows]
    prefix = [0.0]
    for r in rows:
        prefix.append(prefix[-1] + r.get('schedule', 0))
    oracle_count = max(i + 1 - bisect.bisect_right(times, t - HOURS5) for i, t in enumerate(times))
    oracle_cost = max(prefix[i + 1] - prefix[bisect.bisect_right(times, t - HOURS5)] for i, t in enumerate(times))
    assert oracle_count == window_summary(rows, top=1)['maximum']['count']
    assert abs(oracle_cost - window_summary(usage_rows, 'schedule', top=1)['maximum']['usd']) < 1e-7
    native_rows = list(native.values())
    for r in native_rows:
        r['schedule'] = price(r['usage'], r['t'])
    out = {'status': 'partial', 'generated_at_utc': dt.datetime.now(UTC).isoformat(), 'quick_live_only': quick,
           'coverage': {'all_events_first_utc': iso(all_event_min), 'all_events_last_utc': iso(all_event_max),
                        'model_calls_first_utc': iso(rows[0]['t']) if rows else None,
                        'model_calls_last_utc': iso(rows[-1]['t']) if rows else None},
           'sources': sources, 'diagnostics': dict(diagnostics), 'excluded_messages': dict(excluded),
           'verification': {'independent_binary_search_oracle': 'passed', 'max_count': oracle_count, 'max_schedule_usd': oracle_cost},
           'calendar_months_utc_not_billing_cycles': dict(calendar_costs),
           'custom_prompt_errors_checked': dict(custom_errors), 'native_coverage_checks': native_coverage,
           'runtime_snapshot_crosscheck': dict(snapshot_checks),
           'all_zero_usage_by_provider_stop_reason': [{'provider': p, 'stop_reason': s, 'records': n} for (p, s), n in collections.Counter((r['provider'], r['stop_reason']) for r in usage_rows if not any(r['usage'].get(k, 0) for k in ['input', 'output', 'cacheRead', 'cacheWrite'])).most_common()],
           'event_types': dict(event_types), 'usage_report_states': dict(usage_states),
           'missing_usage_models': dict(missing_usage_models), 'requests': window_summary(rows),
           'groups': {g: window_summary([r for r in rows if r['group'] == g], top=1) for g in sorted({r['group'] for r in rows})},
           'models': [{'provider': p, 'model': m, 'calls': n} for (p, m), n in collections.Counter((r['provider'], r['model']) for r in rows).most_common()],
           'stop_reasons': dict(collections.Counter(r['stop_reason'] or 'unknown' for r in rows)),
           'usage_totals': {k: sum(r['usage'].get(k, 0) for r in usage_rows) for k in ['input', 'output', 'cacheRead', 'cacheWrite', 'reasoningTokens', 'totalTokens']},
           'costs': {scenario: window_summary(usage_rows, scenario) for scenario in ['schedule', 'all_offpeak', 'all_peak', 'no_cache']},
           'native_mirror_usage_only': {'records': len(native_rows), 'request_count_unknown': True,
                                      'usage_totals': {k: sum(r['usage'].get(k, 0) for r in native_rows) for k in ['input', 'output', 'cacheRead', 'cacheWrite']},
                                      'terminal_time_schedule_estimate': window_summary(native_rows, 'schedule')},
           'rate_limit_or_quota_errors': errors,
           'method': {'window': '(end - 5 hours, end], timestamps from message.timestamp then event.timestamp; all endpoints tested',
                      'dedup': 'agent + original event id + event timestamp across live DB, branches, archives and backups; call key also includes message timestamp/provider/model; archives deduplicated by SHA-256',
                      'count': 'assistant model response records, including recorded error/aborted retries; synthetic openclaw, native mirrored messages and realtime excluded; not a complete HTTP attempt ledger',
                      'cost': 'normalized usage input+cacheWrite at uncached input rate, cacheRead at cache rate, output at output rate; reasoning not added twice; no-cache sensitivity prices cacheRead as input',
                      'prices_per_million_offpeak': {'input': .15, 'output': .60, 'cacheRead': .003},
                      'peak_multiplier': 2, 'peak_utc': 'Mon-Fri [01:00,04:00), [06:00,10:00)',
                      'reference_requests_estimate_not_quota': REFERENCE,
                      'reference_cost_per_5h_usd': 20,
                      'privacy': 'local read-only sqlite with WAL, libzstd; no conversation/error bodies emitted; no network',
                      'additional_coverage_checks': 'native codex threads table and sessions directory existence; all custom prompt-error events checked for quota markers'},
           'limitations': ['Surviving local history only; deleted history before retained snapshots is unknowable.',
                           'Internal SDK HTTP retries and compaction/summarization calls not necessarily persisted as assistant events.',
                           'Native Codex mirrored commentary/final messages are not a per-request ledger; nonzero terminal usage kept separate.',
                           'Foreign tokenizer and historical cache-hit patterns do not predict Flash Go exactly; missing/zero usage is not proof of free calls.',
                           'Token-based counterfactual does not simulate stopping at $20 or later blocked/retried requests; Go billing/reset mechanics may differ.',
                           'No guarantee of fixed 43330 requests; no claim that quotas are shared across models.']}
    return out


def markdown(d):
    r = d['requests']
    peak = r['maximum']
    lines = ['# OpenClaw: сохранённая история и rolling 5 часов', '',
             '**Статус: partial** — достоверный подсчёт сохранённых model-response records, не полный журнал HTTP-попыток всех harness.', '',
             '## Результат', '',
             f"- Охваченные model calls (UTC): {r['first_utc']} — {r['last_utc']}; всего **{r['calls']:,}** уникальных записей вызовов.",
             f"- Все события (UTC): {d['coverage']['all_events_first_utc']} — {d['coverage']['all_events_last_utc']}.",
             f"- Глобальный rolling максимум: **{peak['count']:,} / 5h = {peak['percent_43330']:.3f}% от справочных 43 330**.",
             '- 43 330 — официальная оценка, **не гарантированная квота**. Сравнение с ней не заменяет проверку $20/5h.', '',
             '### Пять неперекрывающихся максимумов по числу вызовов', '',
             '| Начало (исключая), Europe/Moscow | Конец (включая), Europe/Moscow | Calls | % 43 330 |',
             '|---|---|---:|---:|']
    for w in r['top_nonoverlapping']:
        lines.append(f"| {w['start_exclusive_moscow']} | {w['end_inclusive_moscow']} | {w['count']} | {w['percent_43330']:.3f}% |")
    lines += ['', '### Агенты и подагенты', '', '| Группа | Всего records | Max/5h |', '|---|---:|---:|']
    for group, stats in d['groups'].items():
        lines.append(f"| {group} | {stats['calls']} | {stats['maximum']['count']} |")
    lines += ['', '### Контрфактическая стоимость Flash Go', '',
              'Локальные usage всех подходящих моделей перепрайсены в Flash; не фактический счёт Go. Input не включает cacheRead; cacheWrite по input. Output уже включает reasoning (повторно не прибавлялся).', '',
              '| Сценарий | Максимум $/5h | Число endpoint-windows >$20 | Сумма за историю $ |', '|---|---:|---:|---:|']
    for name, stats in d['costs'].items():
        lines.append(f"| {name} | {stats['maximum']['usd']:.6f} | {stats['endpoint_windows_above_20']} | {stats['total_usd']:.6f} |")
    w = d['costs']['schedule']['maximum']
    lines += ['', f"Пик schedule: {w['start_exclusive_moscow']} — {w['end_inclusive_moscow']}; {w['count']} records, **${w['usd']:.6f}**; нулевой usage у {w['all_zero_usage_records']} records внутри этого окна.",
              f"**Это не доказательство отсутствия $20-квоты:** за всю историю {d['diagnostics']['all_zero_usage_calls']} нулевых usage, из них {d['diagnostics']['all_zero_usage_successful_calls']} у успешных ответов; есть недоучёт. Пиковый записанный расход оставляет лишь ${(20-w['usd']):.6f} запаса.",
              'Количество превышений — число проверенных окон, заканчивающихся модельной записью, а не число независимых эпизодов или блокировок.', '',
              'Календарные суммы UTC (не известные billing cycles Go):']
    for month, totals in d['calendar_months_utc_not_billing_cycles'].items():
        lines.append(f"- {month}: {totals['calls']} calls, ${totals['schedule_usd']:.6f} по записанному usage.")
    lines += ['Лимит $100/month тоже существенен; сумма за календарный месяц не доказывает конкретный момент исчерпания billing-cycle квоты.', '',
              '## Первичные локальные источники', '',
              'Каждая БД открыта `mode=ro`, `PRAGMA query_only=ON`, в read transaction; WAL учитывается. Ни сервисы, ни настройки не изменялись.', '',
              'Таблицы: `transcript_events` (JSON/zstd), `session_transcript_archives` (zstd JSONL), `session_windows`; `subagent_runs` в общей state DB — только классификация. `trajectory_runtime_events.model.completed` — агрегат run, не добавлен повторно.', '',
              '| БД | Агент | Events rows | Archives | Новых calls | Дубликатов events |', '|---|---|---:|---:|---:|---:|']
    for s in d['sources']:
        st = s['stats']
        lines.append(f"| [{Path(s['path']).name}](<{s['path']}>) | {s.get('agent', s.get('skip',''))} | {st.get('transcript_rows',0)} | {st.get('archive_records',0)} | {st.get('unique_calls_added',0)} | {st.get('duplicate_events',0)} |")
    lines += ['', '## Методика и полнота', '',
              '- Считаются только `type=message`, `message.role=assistant` с provider/model/api: один сохранённый ответ/ошибка = одна наблюдаемая попытка. User/tool records не считаются. ToolUse-ответ тоже LLM call.',
              '- Все ветки и старые windows включены, а не только active branch. Наследованные event id+original timestamp дедуплицируются в пределах агента; архивы/backup/snapshot не складываются повторно. Повторные попытки с новым event id сохранены отдельно.',
              '- Live DB обрабатывается первой; retained pre-migration backups и update-prep snapshots добавляют только уникальные события. Необследованные сторонние tmp/catalog DB не являются OpenClaw transcript history.',
              '- Временная метка вызова: `message.timestamp` (обычно начало), иначе `event.timestamp`; created_at — лишь fallback. Окна строго `(t−5h,t]`; проверена каждая правая граница, а не фиксированные часы.',
              '- `:subagent:`/subagent registry/spawned_by выделены отдельно от root; обычный parent_session_key не достаточен (он бывает у fork).',
              '- Синтетические delivery-mirror/automation-result/gateway-injected исключены. Native Codex mirror commentary/final нельзя считать одним запросом на сообщение; их usage агрегаты отдельно в JSON, не смешаны с per-call usage.',
              f"- Исключения: `{json.dumps(d['excluded_messages'], ensure_ascii=False)}`.",
              f"- Диагностика: `{json.dumps(d['diagnostics'], ensure_ascii=False)}`.",
              f"- Usage report states: `{json.dumps(d['usage_report_states'], ensure_ascii=False)}`.",
              f"- Независимая проверка maxima через binary-search/prefix-sum oracle: `{json.dumps(d['verification'], ensure_ascii=False)}`.",
              f"- Native coverage checks: `{json.dumps(d['native_coverage_checks'], ensure_ascii=False)}`. Нативный request ledger не восстановлен.",
              f"- Runtime messagesSnapshot cross-check (включая дубли в backups): `{json.dumps(d['runtime_snapshot_crosscheck'], ensure_ascii=False)}`. Run-level usage не прибавлялся к assistant records.",
              f"- Retained backup/snapshot добавили {sum(s['stats'].get('unique_calls_added',0) for s in d['sources'] if not s['path'].endswith('/agent/openclaw-agent.sqlite'))} новых model calls; дубликаты не суммировались. Это проверено union, а не предположено.", '',
              '### Реальные исторические ошибки', '',
              f"Найдено {len(d['rate_limit_or_quota_errors'])} уникальных errorMessage с 429/rate-limit/quota/capacity маркерами. В JSON только timestamp/provider/model/id и категории — без исходного текста, потенциально содержащего приватные данные. Это ошибки исторических провайдеров, **не свидетельство квот Go**.",
              f"Проверены также {d['custom_prompt_errors_checked'].get('events',0)} custom `openclaw:prompt-error` events; quota/rate markers в них: {d['custom_prompt_errors_checked'].get('quota_or_rate_markers',0)} (повторно как requests не добавлены).",
              'Подтверждённые безопасные сигнатуры: Kimi — HTTP 429 + usage limit/quota; OpenAI — usage limit; closerouter — insufficient balance. Маркер balance означает нехватку средств, а не request rate-limit.', '',
              '| Provider | Model | Error records |', '|---|---|---:|']
    counter = collections.Counter((e['provider'], e['model']) for e in d['rate_limit_or_quota_errors'])
    for (p, m), n in counter.most_common():
        lines.append(f'| {p} | {m} | {n} |')
    lines += ['', '### Что не покрыто', ''] + ['- ' + text for text in d['limitations']]
    lines += ['', '## Источник тарифных предпосылок', '',
              '- [OpenCode Go usage limits](https://opencode.ai/docs/console/go/#usage-limits): $20/5h и $100/month для Flash, по предоставленному контексту.',
              '- [OpenCode Go estimated requests](https://opencode.ai/docs/console/go/#estimated-requests): 43 330/5h — оценка, не фиксированный request limit.',
              '- Тарифы из контекста: offpeak input/output/cache $0.15/$0.60/$0.003 per million; peak вдвое, weekdays 01–04,06–10 UTC. Не выполнялась отправка локальных данных внешним сайтам.', '',
              '## Самопроверка', '', '```bash',
              'python3 docs/research/openclaw-five-hour-usage.py --self-test',
              'python3 docs/research/openclaw-five-hour-usage.py --quick',
              'python3 docs/research/openclaw-five-hour-usage.py --write',
              '```', '',
              'Без `--write` скрипт не пишет файлы. `--write` заменяет только companion Markdown/JSON. Перезапуск на live history может отличаться из-за новых событий. JSON содержит агрегаты и служебные IDs, но не переписку.', '']
    return '\n'.join(lines)


def self_test():
    base = int(dt.datetime(2026, 11, 9, 0, tzinfo=UTC).timestamp() * 1000)
    rows = [{'t': base + x, 'group': 'test', 'usd': 10} for x in [0, 1, HOURS5, HOURS5 + 1]]
    assert window_summary(rows)['maximum']['count'] == 2
    assert window_summary(rows, 'usd')['maximum']['usd'] == 20
    assert window_summary(rows, 'usd')['endpoint_windows_above_20'] == 0
    u = {'input': 1_000_000, 'output': 1_000_000, 'cacheRead': 1_000_000, 'cacheWrite': 0}
    assert abs(price(u, base) - .753) < 1e-9
    assert abs(price(u, base + 2 * 3600_000) - 1.506) < 1e-9
    assert abs(price(u, base + 2 * 3600_000, 'no_cache') - 1.8) < 1e-9
    print('self-test: passed (half-open boundaries, window sums, pricing and peak schedule)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quick', action='store_true', help='live agent databases + their SQL archives only')
    ap.add_argument('--write', action='store_true', help='replace only companion JSON and Markdown')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        result = audit(args.quick)
        if args.write:
            (OUT / 'openclaw-five-hour-usage.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            (OUT / 'openclaw-five-hour-usage.md').write_text(markdown(result))
        print(json.dumps({k: result[k] for k in ['coverage', 'diagnostics', 'excluded_messages', 'requests', 'groups', 'stop_reasons', 'costs', 'native_mirror_usage_only']}, ensure_ascii=False, indent=2))
