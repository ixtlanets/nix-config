# DSH private vault pilot: исполнение (выборка, загрузка, dedup, OCR)

**Status: partial — технически всё прошло, но 1 из 4 страниц OCR вернула `STATUS: PARTIAL`, поэтому это не COMPLETE.** Прогон 2026-11-10 17:30–17:45 MSK на `nik@omarchy-vm` (`codex-omarchy45-pilot`). Постоянные карточки не создавались, vault не менялся, коммитов нет, read state Telegram не менялся, сервисы/код/quota не трогались. Всё медицинское содержимое (оригиналы, страницы, OCR-текст) остаётся только на VM в private cache; в этом отчёте — только технические id, размеры, хеши, счётчики и статусы.

## 1. Что сделано

| Шаг | Результат |
|---|---|
| Группа | `dialogs --search` → точное совпадение title ровно 1, `peer_id -5046720831`, `kind chat`, near-match 0 |
| Отправитель | `participants` (3 участника) → строгий token-match «Андрей» ровно 1: `sender_id 1542601938` |
| Окно истории | `history --limit 80`, только метаданные; последний contiguous блок фото этого sender — `354319`, `354320` (13:10) и `354321`, `354322` (13:17), все `out=false`, без подписей |
| Выбор | Однозначный: других фото-сообщений в окне после 2 ноября нет, sender единственный, блок последний. `grouped_id` сокет не отдаёт — contiguous трактовался как кандидат, а не как доказательство альбома |
| media | 4 вложения `photo`, `image/jpeg`, `available`, размеры 128 719 / 151 775 / 116 005 / 121 475 B |
| Загрузка | cached-режим по одному, `max-bytes 33554432`, все 4 `complete`, квота не тронута |
| Dedup | SHA-256 exact check каждого файла до OCR: `exact_matches: 0` × 4 (дублей нет, существующие карточки не читались) |
| OCR | штатный `local_document_ocr.py`, sequential, 4 источника × 1 страница, `all_valid: true`, exit 0 |
| Независимая проверка | `load_validated_ocr_blocks()` + пересчёт хешей/manifest на каждой странице: `verified_upright: true` × 4 |

## 2. Выбранные сообщения

| message_id | date (MSK) | attachment_id | bytes | sha256 | cache_ref |
|---|---|---|---|---|---|
| 354319 | 2026-11-10 13:10 | `photo:5447108697566944929` | 128 719 | `157dd56d4d045965fe04a8fa9231ce2aa6eb58928c75b6ba3e577001eddbadf0` | тот же + `.bin` |
| 354320 | 2026-11-10 13:10 | `photo:5447108697566944930` | 151 775 | `c30983eb0bd539c1e067863d795ce5ea68c12a58bbd13b2fdc5440edea5fff30` | тот же + `.bin` |
| 354321 | 2026-11-10 13:17 | `photo:5447108697566944946` | 116 005 | `f882d186cdb810c965d6f7f7527d35e56b370780f8907aee1ad164dbca78ebeb` | тот же + `.bin` |
| 354322 | 2026-11-10 13:17 | `photo:5447108697566944947` | 121 475 | `1ffe9d8933a0062ad17b312ca30dcb3927723a36aacb813ddfaf99b0e3ad4cb7` | тот же + `.bin` |

Итого 4 файла, 517 974 B, MIME `image/jpeg` → staging с суффиксом `.jpg`. Все `job_id` (cached download, 64-hex) записаны в `manifest.json` вместе с refs; отдельных job-id в отчёт не переношу — они избыточны при наличии `sha256`/`cache_ref`.

## 3. Dedup

- Exact-совпадений с существующим vault: **0** для каждого из 4 файлов.
- Дублей внутри набора: 0 (все 4 sha256 различны).
- `document_dedup.py candidates` **не запускался**: он требует извлечённых метаданных (patient/date/institution), а это медицинские факты — их извлечение относится к следующему локальному шагу (cardbuilder). Exact-проверка исключает повтор тех же байтов, но не другую фотографию того же документа; semantic candidates ещё необходимо проверить локально до постоянного сохранения.

## 4. OCR: статусы и ориентация

Прогон: `/usr/bin/python3 /home/nik/vault/tools/local_document_ocr.py --spec <RUN>/ocr-spec-run1.json --cache-root <RUN>/ocr/run1`, модель `unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M`, endpoint `http://192.168.1.174:8081/v1/chat/completions` (единственный approved literal, без прокси/редиректов). Запросы строго последовательные, по одной странице, без concurrency и без retry.

| source_id | pages | verified_upright | rotation (cw) | OCR status | LIMITATION |
|---|---|---|---|---|---|
| `msg354319` | 1 | 1 | 90° | COMPLETE | — |
| `msg354320` | 1 | 1 | 270° | COMPLETE | — |
| `msg354321` | 1 | 1 | 270° | COMPLETE | — |
| `msg354322` | 1 | 1 | 180° | **PARTIAL** | 1 строка (категория локально не распознана; текст остаётся на VM) |

- Итого: `all_valid: true`, 4 источника / 4 страницы, статусы `COMPLETE 3`, `PARTIAL 1`; повороты `90°×1, 180°×1, 270°×2`; страниц с `verified_upright != true` нет.
- Почему не COMPLETE: одна страница помечена моделью как PARTIAL с одной строкой `LIMITATION`. Драйвер считает такую страницу валидной (PARTIAL — разрешённый статус), но по правилу пилота PARTIAL ≠ COMPLETE: карточка может быть собрана, однако ограничение обязано быть перенесено в неё, а страница `msg354322` требует локального просмотра (возможно, лучший кадр или ручная сверка).
- Ориентация: OSD как необязательный сигнал, решение принимал contact-sheet/4-way fallback + независимая upright-проверка; «уговорить» модель выбрать поворот не пытались, при неоднозначности драйвер упал бы fail-closed.

## 5. Артефакты (все на VM, private cache, 0700/0600)

`RUN=/home/nik/.cache/dsh-private-vault-pilot/20261110T1730Z`

| Путь | Назначение |
|---|---|
| `<RUN>/manifest.json` | главный локальный manifest: peer/sender, 4 items (message_id, attachment_id, sha256, size, mime, cache_ref, staged path, dedup), OCR refs на каждый source, сводка статусов |
| `<RUN>/jobs.json` | вход для staging (id/hash/size/mime) |
| `<RUN>/staging/msg<id>/page-01.jpg` | копии оригиналов с корректным суффиксом (sha256 сверен с архивом) |
| `<RUN>/ocr-spec-run1.json` | spec драйвера, received order |
| `<RUN>/ocr/run1/batch-result.json` | агрегат драйвера (`all_valid: true`) |
| `<RUN>/ocr/run1/msg<id>/{render-manifest.json,result.json,orientation/page-0001.json,ocr/page-0001.md,rendered/page-0001.jpg}` | страничные записи, manifest ориентации, OCR-текст |
| `<RUN>/ocr-run1-combined.md` | склеенный OCR по страницам (`## <source_id> page N`), только из validated-блоков |
| `<RUN>/ocr-run1.stdout`, `<RUN>/ocr-run1.stderr` | лог драйвера (stdout санитизирован фильтром, stderr пуст) |
| `<RUN>/bin/{qfilter,dl,stage,verify,combine}.py` | локальные скрипты прогона (фильтр сокета, загрузка, staging+dedup, независимая проверка, сборка combined) |
| `/home/nik/tg-userbot/data/attachment-archive/<sha256>.bin` | 4 оригинала (0600), штатный attachment-cache |

Контрольные хеши артефактов: `manifest.json f43e83a7…bd55f4`, `ocr-run1-combined.md 854095bc…361f5d`, `batch-result.json a0360f6b…200acc`.

Квота attachment-cache: до 4 276 289 442 B, после 4 276 810 212 B (+520 770 B: 4 файла + job-receipts), лимит 4 GiB — запас ~18.2 MiB. Никакой очистки, изменения quota, рестартов не было. Свободно на диске ~145 GiB.

## 6. Проверки отсутствия побочных эффектов

- Read state: в `query_server.py` нет `mark_read`/`read_ack`/`send_read` (grep = 0 совпадений), `query.py` их не вызывает; операции прогона — только `dialogs`, `participants`, `history`, `media`, `download_attachment`, `download_status`. Сообщений не отправлялось.
- Vault: `git status --porcelain` = 60 путей, как до прогона; новых файлов в `Вложения/Оригиналы` = 0; постоянных карточек нет; коммитов нет.
- Сервисы/код/vault tools не правились; `local_document_ocr.py` и `document_dedup.py` использованы как есть.
- В облачный контекст не попали: текст сообщений, заголовок чата, имена участников, имена файлов, base64, OCR-содержимое, медицинские факты. Сокет вызывался только через локальный whitelist-фильтр, `ok` проверялся отдельно от exit code.

## 7. Что дальше (следующий локальный шаг)

1. Локальный cardbuilder читает `<RUN>/manifest.json` → `ocr[*]` и `ocr-run1-combined.md`, **не** перезапуская OCR. Валидировать нужно тем же `load_validated_ocr_blocks()`, а не фактом существования `.md`.
2. Перенести в карточку `LIMITATION` страницы `msg354322` и статус `partial`; при желании — запросить у владельца лучший кадр этого документа.
3. Извлечь patient/date/institution локально, затем `document_dedup.py candidates --metadata-json`, показать кандидатов пользователю (автомерж запрещён).
4. Только после подтверждения — оригиналы в `Вложения/Оригиналы/`, карточка по шаблону, обратные ссылки, `document_dedup.py validate`, `vault-commit --dry-run`, коммит своих путей.
5. Квота attachment-cache остаётся на ~18 MiB: следующая cached-загрузка >18 MiB упрётся в `cache_quota_exceeded`; inline ≤8 MiB пишет в тот же архив и квоту не обходит. Решение по очистке — операторское.
