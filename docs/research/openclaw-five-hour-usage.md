# OpenClaw: сохранённая история и rolling 5 часов

**Статус: partial** — достоверный подсчёт сохранённых model-response records, не полный журнал HTTP-попыток всех harness.

## Результат

- Охваченные model calls (UTC): 2026-10-05T23:45:50.078+00:00 — 2026-11-07T07:33:43.712+00:00; всего **72,489** уникальных записей вызовов.
- Все события (UTC): 2026-10-05T23:45:48.063+00:00 — 2026-11-07T07:34:03.558+00:00.
- Глобальный rolling максимум: **2,055 / 5h = 4.743% от справочных 43 330**.
- 43 330 — официальная оценка, **не гарантированная квота**. Сравнение с ней не заменяет проверку $20/5h.

### Пять неперекрывающихся максимумов по числу вызовов

| Начало (исключая), Europe/Moscow | Конец (включая), Europe/Moscow | Calls | % 43 330 |
|---|---|---:|---:|
| 2026-10-24T22:47:16.713+03:00 | 2026-10-25T03:47:16.713+03:00 | 2055 | 4.743% |
| 2026-10-22T12:45:43.304+03:00 | 2026-10-22T17:45:43.304+03:00 | 2032 | 4.690% |
| 2026-11-05T12:00:12.655+03:00 | 2026-11-05T17:00:12.655+03:00 | 1706 | 3.937% |
| 2026-10-18T23:19:34.116+03:00 | 2026-10-19T04:19:34.116+03:00 | 1615 | 3.727% |
| 2026-10-17T12:59:56.017+03:00 | 2026-10-17T17:59:56.017+03:00 | 1540 | 3.554% |

### Агенты и подагенты

| Группа | Всего records | Max/5h |
|---|---:|---:|
| main:root | 68626 | 2055 |
| main:subagent | 3583 | 637 |
| tonal:root | 78 | 44 |
| viewer:root | 202 | 140 |

### Контрфактическая стоимость Flash Go

Локальные usage всех подходящих моделей перепрайсены в Flash; не фактический счёт Go. Input не включает cacheRead; cacheWrite по input. Output уже включает reasoning (повторно не прибавлялся).

| Сценарий | Максимум $/5h | Число endpoint-windows >$20 | Сумма за историю $ |
|---|---:|---:|---:|
| schedule | 19.343469 | 0 | 449.928603 |
| all_offpeak | 19.343469 | 0 | 385.708351 |
| all_peak | 38.686938 | 2554 | 771.416702 |
| no_cache | 66.945267 | 29096 | 2018.608101 |

Пик schedule: 2026-10-24T22:48:14.062+03:00 — 2026-10-25T03:48:14.062+03:00; 2055 records, **$19.343469**; нулевой usage у 3 records внутри этого окна.
**Это не доказательство отсутствия $20-квоты:** за всю историю 1077 нулевых usage, из них 811 у успешных ответов; есть недоучёт. Пиковый записанный расход оставляет лишь $0.656531 запаса.
Количество превышений — число проверенных окон, заканчивающихся модельной записью, а не число независимых эпизодов или блокировок.

Календарные суммы UTC (не известные billing cycles Go):
- 2026-10: 62700 calls, $387.633636 по записанному usage.
- 2026-11: 9789 calls, $62.294967 по записанному usage.
Лимит $100/month тоже существенен; сумма за календарный месяц не доказывает конкретный момент исчерпания billing-cycle квоты.

## Первичные локальные источники

Каждая БД открыта `mode=ro`, `PRAGMA query_only=ON`, в read transaction; WAL учитывается. Ни сервисы, ни настройки не изменялись.

Таблицы: `transcript_events` (JSON/zstd), `session_transcript_archives` (zstd JSONL), `session_windows`; `subagent_runs` в общей state DB — только классификация. `trajectory_runtime_events.model.completed` — агрегат run, не добавлен повторно.

| БД | Агент | Events rows | Archives | Новых calls | Дубликатов events |
|---|---|---:|---:|---:|---:|
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/main/agent/openclaw-agent.sqlite>) | main | 242575 | 217 | 72209 | 2356 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/openclaw/agent/openclaw-agent.sqlite>) | openclaw | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/opencode/agent/openclaw-agent.sqlite>) | opencode | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/tonal/agent/openclaw-agent.sqlite>) | tonal | 252 | 0 | 78 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/viewer/agent/openclaw-agent.sqlite>) | viewer | 680 | 0 | 202 | 0 |
| [openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/agents/main/agent/openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | main | 221919 | 204 | 0 | 221919 |
| [openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak](</home/nik/.openclaw/agents/main/agent/openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak>) | main | 113911 | 187 | 0 | 113911 |
| [openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/agents/openclaw/agent/openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | openclaw | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak](</home/nik/.openclaw/agents/openclaw/agent/openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak>) | openclaw | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/agents/opencode/agent/openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | opencode | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak](</home/nik/.openclaw/agents/opencode/agent/openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak>) | opencode | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/agents/tonal/agent/openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | tonal | 252 | 0 | 0 | 252 |
| [openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak](</home/nik/.openclaw/agents/tonal/agent/openclaw-agent.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak>) | tonal | 252 | 0 | 0 | 252 |
| [openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/agents/viewer/agent/openclaw-agent.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | viewer | 680 | 0 | 0 | 680 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/openclaw/agent.nocow-backup-eejYbp/openclaw-agent.sqlite>) | openclaw | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/openclaw/agent.nocow-snapshots-lY6MwM/openclaw-agent.sqlite>) | openclaw | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/opencode/agent.nocow-backup-aNbD1J/openclaw-agent.sqlite>) | opencode | 0 | 0 | 0 | 0 |
| [openclaw-agent.sqlite](</home/nik/.openclaw/agents/opencode/agent.nocow-snapshots-5cyi2W/openclaw-agent.sqlite>) | opencode | 0 | 0 | 0 | 0 |
| [openclaw.sqlite.pre-codexmig-20261007.bak](</home/nik/.openclaw/state/openclaw.sqlite.pre-codexmig-20261007.bak>) | no transcript_events table | 0 | 0 | 0 | 0 |
| [openclaw.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak](</home/nik/.openclaw/state/openclaw.sqlite.pre-startup-migration-40c8b2fe-58dd-8746-8aed-9efefbcd12ea.bak>) | no transcript_events table | 0 | 0 | 0 | 0 |
| [openclaw.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak](</home/nik/.openclaw/state/openclaw.sqlite.pre-startup-migration-d562eabb-057f-8d26-8a5a-c87421e81694.bak>) | no transcript_events table | 0 | 0 | 0 | 0 |
| [database.sqlite](</home/nik/.openclaw/update-prep-20261019/sqlite-snapshots/2026-10-19T19-53-34-935Z-5758a415-1a60-42dd-9cad-31f6639a74c3/database.sqlite>) | no transcript_events table | 0 | 0 | 0 | 0 |
| [database.sqlite](</home/nik/.openclaw/update-prep-20261019/sqlite-snapshots/2026-10-19T19-53-47-067Z-1a121453-273a-4448-bdbd-0b4011a2305f/database.sqlite>) | main | 113770 | 187 | 0 | 113770 |

## Методика и полнота

- Считаются только `type=message`, `message.role=assistant` с provider/model/api: один сохранённый ответ/ошибка = одна наблюдаемая попытка. User/tool records не считаются. ToolUse-ответ тоже LLM call.
- Все ветки и старые windows включены, а не только active branch. Наследованные event id+original timestamp дедуплицируются в пределах агента; архивы/backup/snapshot не складываются повторно. Повторные попытки с новым event id сохранены отдельно.
- Live DB обрабатывается первой; retained pre-migration backups и update-prep snapshots добавляют только уникальные события. Необследованные сторонние tmp/catalog DB не являются OpenClaw transcript history.
- Временная метка вызова: `message.timestamp` (обычно начало), иначе `event.timestamp`; created_at — лишь fallback. Окна строго `(t−5h,t]`; проверена каждая правая граница, а не фиксированные часы.
- `:subagent:`/subagent registry/spawned_by выделены отдельно от root; обычный parent_session_key не достаточен (он бывает у fork).
- Синтетические delivery-mirror/automation-result/gateway-injected исключены. Native Codex mirror commentary/final нельзя считать одним запросом на сообщение; их usage агрегаты отдельно в JSON, не смешаны с per-call usage.
- Исключения: `{"synthetic_openclaw_messages": 547, "native_mirrored_messages": 709, "realtime_voice_messages_not_text_requests": 2}`.
- Диагностика: `{"repeated_nonempty_provider_response_ids": 0, "calls_without_response_id": 221, "usage_missing_or_non_numeric": 0, "all_zero_usage_calls": 1077, "cache_write_nonzero_calls": 2, "native_nonzero_usage_records": 19, "all_zero_usage_successful_calls": 811, "usage_component_total_mismatches": 0}`.
- Usage report states: `{"legacy_unspecified": 66507, "available": 5347, "unavailable": 635}`.
- Независимая проверка maxima через binary-search/prefix-sum oracle: `{"independent_binary_search_oracle": "passed", "max_count": 2055, "max_schedule_usd": 19.34346881400012}`.
- Native coverage checks: `{"main_codex_state_threads": 0, "main_codex_sessions_directory_exists": false, "acpx_codex_sessions_directory_exists": false}`. Нативный request ledger не восстановлен.
- Runtime messagesSnapshot cross-check (включая дубли в backups): `{"model_completed_events": 7487, "assistant_metadata_records": 21434, "matched_transcript_responses": 20838, "unmatched_or_truncated_response_metadata": 596, "truncated_or_absent_snapshots": 2}`. Run-level usage не прибавлялся к assistant records.
- Retained backup/snapshot добавили 0 новых model calls; дубликаты не суммировались. Это проверено union, а не предположено.

### Реальные исторические ошибки

Найдено 18 уникальных errorMessage с 429/rate-limit/quota/capacity маркерами. В JSON только timestamp/provider/model/id и категории — без исходного текста, потенциально содержащего приватные данные. Это ошибки исторических провайдеров, **не свидетельство квот Go**.
Проверены также 137 custom `openclaw:prompt-error` events; quota/rate markers в них: 0 (повторно как requests не добавлены).
Подтверждённые безопасные сигнатуры: Kimi — HTTP 429 + usage limit/quota; OpenAI — usage limit; closerouter — insufficient balance. Маркер balance означает нехватку средств, а не request rate-limit.

| Provider | Model | Error records |
|---|---|---:|
| openai | gpt-6.1-sol | 8 |
| kimi | k3.1-pro | 7 |
| closerouter | deepseek/deepseek-v4.1-flash | 3 |

### Что не покрыто

- Surviving local history only; deleted history before retained snapshots is unknowable.
- Internal SDK HTTP retries and compaction/summarization calls not necessarily persisted as assistant events.
- Native Codex mirrored commentary/final messages are not a per-request ledger; nonzero terminal usage kept separate.
- Foreign tokenizer and historical cache-hit patterns do not predict Flash Go exactly; missing/zero usage is not proof of free calls.
- Token-based counterfactual does not simulate stopping at $20 or later blocked/retried requests; Go billing/reset mechanics may differ.
- No guarantee of fixed 43330 requests; no claim that quotas are shared across models.

## Источник тарифных предпосылок

- [OpenCode Go usage limits](https://opencode.ai/docs/console/go/#usage-limits): $20/5h и $100/month для Flash, по предоставленному контексту.
- [OpenCode Go estimated requests](https://opencode.ai/docs/console/go/#estimated-requests): 43 330/5h — оценка, не фиксированный request limit.
- Тарифы из контекста: offpeak input/output/cache $0.15/$0.60/$0.003 per million; peak вдвое, weekdays 01–04,06–10 UTC. Не выполнялась отправка локальных данных внешним сайтам.

## Самопроверка

```bash
python3 docs/research/openclaw-five-hour-usage.py --self-test
python3 docs/research/openclaw-five-hour-usage.py --quick
python3 docs/research/openclaw-five-hour-usage.py --write
```

Без `--write` скрипт не пишет файлы. `--write` заменяет только companion Markdown/JSON. Перезапуск на live history может отличаться из-за новых событий. JSON содержит агрегаты и служебные IDs, но не переписку.
