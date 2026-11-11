# DSH private vault pilot: техническая разведка и план исполнения

**Status: done (разведка). Исполнение не начиналось.** Снято 2026-11-10 17:18–17:40 MSK по SSH `nik@omarchy-vm` (hostname `codex-omarchy45-pilot`). Ничего не скачано из целевой группы, ни одна карточка/оригинал не созданы, Telegram read state не менялся, inference не запускался. Единственная запись — этот файл.

## 1. Итог

- Нужные компоненты на VM уже есть и проверены без чтения медицинского корпуса: read-only userbot-сокет v2 с потоковой загрузкой вложений, fail-closed OCR-драйвер с orientation gate, SHA-256 dedup, шаблон карточки, обёртка коммита vault.
- Готового «card builder» и entity-sync **скрипта** нет: карточка собирается по шаблону/процедуре, entity sync — по vault-заметке. Скилл `vault-entity-sync`, на который ссылаются skills, на VM отсутствует.
- Два решения блокируют запуск: (1) attachment-cache заполнен на 3.983 из 4 GiB — cached-загрузка упрётся в `cache_quota_exceeded`; (2) просмотр и подтверждение карточки должны идти по локальному каналу, потому что OCR-текст нельзя отдавать облачному агенту.
- Выбор сообщений безопасен: сокет отдаёт метаданные без текста (`media`), историю можно фильтровать локально до вывода. Группировка альбома (`grouped_id`) сокетом не отдаётся — нужен явный пользовательский выбор набора id.

## 2. Что есть на VM

| Компонент | Путь / запуск | Проверено |
|---|---|---|
| Userbot query-сокет v2 | `/home/nik/tg-userbot/data/query.sock` (srw-------), сервис `tg-userbot` active | `query.py capabilities`: `protocol_version:2`, `cached_download`, `attachments`, `media`, `download_attachment`, `marked_dialog_peers` |
| Клиент сокета | `/home/nik/tg-userbot/.venv/bin/python /home/nik/tg-userbot/query.py {capabilities,dialogs,participants,history,media,download_attachment,download_status}` | CLI-поверхность и JSON-поля сверены с `query_server.py` |
| OCR-драйвер | `/usr/bin/python3 /home/nik/vault/tools/local_document_ocr.py --spec <json> --cache-root <пустой каталог> [--api ... --model ...]` | `py_compile` OK, `--help` OK, 34 unit-теста OK |
| Dedup | `/usr/bin/python3 /home/nik/vault/tools/document_dedup.py --vault /home/nik/vault {check <file>,candidates --metadata-json '<json>',validate,backfill}` | `validate` на текущем vault: `errors: []`, 4.1 s |
| Коммит vault | `/home/nik/.local/bin/vault-commit --agent <hermes\|pablito> --message "<тема>" [--dry-run] [--validate-dedup] -- <пути>` | usage-контракт прочитан; стейджит только переданные пути |
| Шаблон карточки | `~/vault/Шаблоны/Импорт документа.md` | прочитан; задаёт `originals[]`, private-режим, порядок «предложение → подтверждение» |
| Медкарточка (схема) | `~/.openclaw/agents/main/agent/workshop-skills/vault-medical-records/SKILL.md` | frontmatter-схема, две секции в карточке человека, `## Динамика` |
| Entity sync | `~/vault/06 Справочник/Актуализация сущностей из новых источников.md` | процедура есть; **скилл `vault-entity-sync` отсутствует** |
| Инструменты ориентации | `tesseract` (+`osd`, `rus`), `pdftoppm`, `pdfinfo`, `magick` | бинарники и traineddata на месте |

Ключевые детали, на которые опирается план:

- `media` возвращает `chat_id`, `message_id`, `attachments[]` и **не содержит текста сообщения**; `attachment_id` = `document:<id>` / `photo:<id>`, есть `download_ref` ([query_server.py](<ssh://nik@omarchy-vm/home/nik/tg-userbot/query_server.py>), `media_metadata`).
- `history` отдаёт `id`, `date`, `sender_id`, `attachments` и обрезанный текст — текст обязательно отфильтровывать локально ([message_view](<ssh://nik@omarchy-vm/home/nik/tg-userbot/query_server.py>)).
- Read state: в `query_server.py` нет `mark_read`/`send_read_ack`; операции только читают и скачивают выбранный файл, `send` — отдельная явная операция, которую пилот не вызывает ([READONLY_PROTOCOL.md](<ssh://nik@omarchy-vm/home/nik/tg-userbot/READONLY_PROTOCOL.md>)).
- Cached download: ответ сразу даёт `job_id`, затем `download_status` → `sha256`, `size`, `cache_ref` (`<sha256>.bin`); `path`/`content_base64` в cached-ответе отсутствуют. Inline-режим (≤8 MiB) наоборот возвращает `content_base64` и `path` — base64 нельзя печатать.
- OCR-драйвер: spec `{"sources":[{"id":"<safe-id>","paths":["<abs>",...]}]}`; сам делает `GET /v1/models` и требует точный id модели; PDF определяется **по суффиксу `.pdf`**, остальное — изображение; страницы рендерятся 220 dpi, EXIF нормализуется, OSD — необязательный сигнал, далее contact-sheet/4-way fallback и независимая upright-проверка; при любом невалидном результате exit≠0 и downstream блокируется ([local_document_ocr.py](<ssh://nik@omarchy-vm/home/nik/vault/tools/local_document_ocr.py>)).
- Окружение: у `/usr/bin/python3` есть PIL 13.0.0, у `tg-userbot/.venv` PIL нет — OCR запускать системным python3. Endpoint `192.168.1.174:8081` с VM доступен по TCP; модель в коде по умолчанию — `unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M`.

## 3. Жёсткие ограничения пилота

1. Весь медицинский пилот — private mode: OCR и любой анализ только на approved LAN-модели; оригиналы, страницы, OCR-текст, извлечённые факты и метаданные не уходят облачному провайдеру.
2. В облачный контекст разрешены только: число файлов/страниц, технические id (`peer_id`, `message_id`, `sender_id`, `job_id`, `sha256`, `cache_ref`), пути к скриптам, размеры, коды ошибок. Запрещены: заголовок чата, текст сообщений, имена/username/телефоны отправителей, имена файлов, base64.
3. Не выбирать все исторические вложения: только явно подтверждённый набор `message_id` (один альбом отправителя, не «все фото за период»).
4. Не вызывать `send`, не менять read state, не трогать `.env`/сессию; второй MTProto-клиент не поднимать.
5. Карточку и её текст не показывать облачному агенту: сборка/анализ — локально, просмотр и подтверждение — локальным каналом (файл на VM, Indexary, VNC). Облако получает только «approve/reject» и технические пути.
6. Vault не git-crypt, remote/push запрещены; коммит только через `vault-commit` и только своими путями ([vault AGENTS](<ssh://nik@omarchy-vm/home/nik/vault/AGENTS.md>)).

## 4. Санитизированный контракт вывода

Правило: **любой** вызов сокета идёт в pipe к локальному фильтру; сырой JSON не печатать. Белый список полей: `ok`, `peer_id`, `message_id`, `sender_id`, `date`, `id`, `kind`, `type`, `size`, `attachment_id`, `download_status`, `job_id`, `sha256`, `cache_ref`, `all_valid`, `page_count`, `errors`. Чёрный список: `title`, `text`, `sender_name`, `username`, `phone`, `name`, `content_base64`, `original_media`.

`query.py` возвращает exit 0 даже при `{"ok": false}` — проверять `ok`, а не только код возврата.

## 5. Проверяемый маршрут исполнения (после решений из §6)

Все команды — на VM, вывод только через фильтр.

**A. Найти группу (без вывода названия).**
```bash
cd /home/nik/tg-userbot
.venv/bin/python query.py dialogs --search "<подстрока>" --limit 200 \
 | python3 -c 'import json,sys; d=json.load(sys.stdin); rows=[r for r in d.get("dialogs",[]) if "<подстрока>" in (r.get("title") or "")]; print({"ok":d.get("ok"),"matches":len(rows),"peer_ids":[r["peer_id"] for r in rows]})'
```
`peer_id` — marked id (int), далее использовать его, не title.

**B. Найти отправителя.**
```bash
.venv/bin/python query.py participants <peer_id> \
 | python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("participants") or []; print({"ok":d.get("ok"),"members":len(rows),"target_ids":[r["id"] for r in rows if "<имя>" in (r.get("name") or "")]})'
```

**C. Прочитать окно истории и оставить только метаданные.**
```bash
.venv/bin/python query.py history <peer_id> --limit 200 \
 | python3 -c 'import json,sys; d=json.load(sys.stdin); ms=[{"id":m["id"],"sender_id":m.get("sender_id"),"date":m["date"],"media":[(a.get("kind"),a.get("type"),a.get("size"),a.get("attachment_id")) for a in m.get("attachments") or []]} for m in d.get("messages") or []]; print(json.dumps({"ok":d.get("ok"),"count":len(ms),"with_media":[m for m in ms if m["media"]],"next_offset_id":d.get("next_offset_id"),"has_more":d.get("has_more")}, ensure_ascii=False))'
```
Страницы — `--offset-id`/`min_id`; лимит 200. Альбом: contiguous-блок id одного `sender_id` с близкими `date` (у сокета нет `grouped_id`) — границы блока подтверждает пользователь.

**D. Метаданные выбранного сообщения (без текста).**
```bash
.venv/bin/python query.py media <peer_id> <message_id> \
 | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"ok":d.get("ok"),"attachments":[{"kind":a["kind"],"type":a.get("type"),"size":a.get("size"),"attachment_id":a.get("attachment_id"),"status":a.get("download_status")} for a in d.get("attachments") or []]}, ensure_ascii=False))'
```

**E. Скачать выбранное.**
```bash
# cached (до 1 GiB): сразу job_id, затем опрос
.venv/bin/python query.py download_attachment <peer_id> <message_id> <attachment_id> --mode cached --max-bytes 33554432
.venv/bin/python query.py download_status <job_id>
# inline fallback (≤8 MiB): base64 отбросить фильтром
.venv/bin/python query.py download_attachment <peer_id> <message_id> <attachment_id> --max-bytes 8388608 \
 | python3 -c 'import json,sys; d=json.load(sys.stdin); d.pop("content_base64",None); print(json.dumps({k:d.get(k) for k in ("ok","sha256","size","path","archive_status","download_status","error")}, ensure_ascii=False))'
```
Файл ложится в `~/tg-userbot/data/attachment-archive/<sha256>.bin` (0600, каталог 0700).

**F. Подготовить страницы для OCR.** Скопировать cache-файл в отдельный staging-каталог с правильным суффиксом: `application/pdf`/`.pdf` → `page-NN.pdf`, остальное → `page-NN.jpg`. Без суффикса `.pdf` драйвер будет читать PDF как изображение.

**G. Dedup до OCR.**
```bash
/usr/bin/python3 /home/nik/vault/tools/document_dedup.py --vault /home/nik/vault check <staged-file>
```
Точное совпадение — стоп, OCR/копирование не выполнять. Кандидаты — только после локального извлечения метаданных, решение пользователя.

**H. OCR.**
```bash
cat > /tmp/medpilot-spec.json <<'JSON'
{"sources":[{"id":"medpilot-<doc-id>","paths":["<staging>/page-01.jpg"]}]}
JSON
/usr/bin/python3 /home/nik/vault/tools/local_document_ocr.py \
  --spec /tmp/medpilot-spec.json \
  --cache-root /home/nik/.cache/hermes-document-processing/<doc-id>/ocr
```
`--cache-root` — новый пустой каталог на каждый прогон; stdout содержит только `all_valid`/счётчики; exit 0 обязателен. Модель и endpoint драйвер проверяет сам через `GET /v1/models`.

**I. Карточка (локально).** Черновик по `Шаблоны/Импорт документа.md` + схеме медкарточки собирается локально; в облако уходит только «черновик готов, путь X, страниц N». Подтверждение — локально. Перед коммитом: `document_dedup.py validate`, затем `vault-commit --dry-run`, затем коммит только путей задачи (карточка + оригинал + карточка человека).

## 6. Блокеры и открытые решения

1. **Квота attachment-cache.** Занято 4 276 289 442 B (3.983 GiB) из 4 GiB, свободно ~18 MiB ([query_server.py](<ssh://nik@omarchy-vm/home/nik/tg-userbot/query_server.py>), `MAX_CACHE_BYTES`). Cached-загрузка альбома может упасть с `cache_quota_exceeded`. Автоочистки нет (операторская операция). Варианты до запуска: оператор чистит старый cache, либо drop-in с другим `TG_QUERY_ARCHIVE_ROOT` (systemd-запись — вне этой фазы), либо inline ≤8 MiB как обход (пишет в тот же архив, base64 не печатать).
2. **Нет `grouped_id`.** Сокет не отдаёт группировку альбома; набор id подтверждает пользователь, автоматический выбор «все вложения периода» запрещён.
3. **Скилл `vault-entity-sync` отсутствует** на VM (искали по всему `~`). Процедура доступна как vault-заметка; при исполнении читать её, а не `skill`.
4. **Канал подтверждения.** Существующий private mode предполагает локальный анализ, но UI-подтверждение в Telegram/облачном агенте показало бы медтекст провайдеру. Нужно решение владельца: просмотр черновика на VM (файл/Indexary/VNC) + «ок» в DSH.
5. **`privacy` во frontmatter.** Медскилл фиксирует `privacy: standard` как конвенцию папки (19 из 20 карточек), а пилот объявлен private. Это разные вещи: private — режим обработки. Значение поля не менять без решения владельца, чтобы не рассинхронизировать папку.
6. **Vault грязный:** 60 незакоммиченных путей. Коммитить только свои, `git add -A` запрещён.

## 7. Намеренно не проверено

`GET /v1/models` и любая inference (по условию — отдельная проверка основного агента; драйвер всё равно проверяет модель при запуске); содержимое целевой группы, альбома, сообщений, имён отправителей; реальные меддокументы и карточки; запись в vault; изменение конфигов/сервисов. OSD-смоук на синтетическом тексте дал `Rotate` только для одной из трёх ориентаций — это согласуется с правилом «OSD необязателен, решает contact-sheet + 4-way fallback»; на реальных фото OSD ожидаемо ненадёжен.

## 8. Источники

- [query.py](<ssh://nik@omarchy-vm/home/nik/tg-userbot/query.py>), [query_server.py](<ssh://nik@omarchy-vm/home/nik/tg-userbot/query_server.py>), [READONLY_PROTOCOL.md](<ssh://nik@omarchy-vm/home/nik/tg-userbot/READONLY_PROTOCOL.md>), [README.md](<ssh://nik@omarchy-vm/home/nik/tg-userbot/README.md>).
- [local_document_ocr.py](<ssh://nik@omarchy-vm/home/nik/vault/tools/local_document_ocr.py>), [document_dedup.py](<ssh://nik@omarchy-vm/home/nik/vault/tools/document_dedup.py>), [unit-тесты OCR](<ssh://nik@omarchy-vm/home/nik/vault/tools/tests/test_local_document_ocr.py>).
- [document-ingestion](<ssh://nik@omarchy-vm/home/nik/.openclaw/skills/document-ingestion/SKILL.md>), [local-private-document-ocr](<ssh://nik@omarchy-vm/home/nik/.openclaw/skills/local-private-document-ocr/SKILL.md>), [vault AGENTS](<ssh://nik@omarchy-vm/home/nik/vault/AGENTS.md>).
- [vault-medical-records](<ssh://nik@omarchy-vm/home/nik/.openclaw/agents/main/agent/workshop-skills/vault-medical-records/SKILL.md>), [telegram-correspondence-read](<ssh://nik@omarchy-vm/home/nik/.openclaw/agents/main/agent/workshop-skills/telegram-correspondence-read/SKILL.md>).
- [Актуализация сущностей](<ssh://nik@omarchy-vm/home/nik/vault/06 Справочник/Актуализация сущностей из новых источников.md>), [шаблон импорта](<ssh://nik@omarchy-vm/home/nik/vault/Шаблоны/Импорт документа.md>), [vault-commit](<ssh://nik@omarchy-vm/home/nik/.local/bin/vault-commit>).
- Локальные копии инструкций: `docs/research/2026-11-10-openclaw-vm-inventory.md`, `/tmp/dsh-vault-pilot-instructions-20261110/` (sha256 копий `document-ingestion.md`, `local-private-document-ocr.md`, `vault-AGENTS.md` совпадают с каноническими на VM).
