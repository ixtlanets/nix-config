# ReadMeABook рядом с Audiobookshelf на `moscow`

**Дата проверки:** 2026-09-11
**Статус:** historical Pi feasibility study; размещение ReadMeABook на
`moscow` отклонено. Утверждённая архитектура находится в
[`2026-09-11-readmeabook-um790pro-design.md`](./2026-09-11-readmeabook-um790pro-design.md).
Конфигурация и внешние системы в рамках исследования не изменялись.

**Проверенный upstream:** [`kikootwo/ReadMeABook`](https://github.com/kikootwo/ReadMeABook),
release [`v1.2.2`](https://github.com/kikootwo/ReadMeABook/releases/tag/v1.2.2)
(`7c7d7bc`) и `main` commit
[`bc37186`](https://github.com/kikootwo/ReadMeABook/commit/bc371860d06c921e2f474ada226b7a3c6427fca5)

## Краткий вывод

`moscow` **подходит по архитектуре, CPU и памяти** для небольшого семейного
ReadMeABook: это Raspberry Pi 4 с 64-bit ARM, четырьмя ядрами и 8 GB RAM, из
которых во время проверки свободно около 6.1 GiB. ReadMeABook публикует официальный
`linux/arm64` image, а upstream оценивает обычное потребление unified-container в
500 MB–1 GB. GPU для основного сценария не нужен.
[Build workflow](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/.github/workflows/build-unified-image.yml#L67-L75),
[upstream resource estimate](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/archive/README.unified.md#L191-L203)

Но развертывать текущий официальный image как полноценный production на Pi пока
не следует:

1. ARM64 image `v1.2.2` содержит **x86-64 `ffmpeg` и `ffprobe`**. Web app,
   PostgreSQL и Redis могут запуститься, но metadata tagging, bulk-import probing,
   chapter merge и MP3 -> M4B завершаются `Exec format error`. Upstream issue
   [#230](https://github.com/kikootwo/ReadMeABook/issues/230) открыт, а исправляющий
   PR [#241](https://github.com/kikootwo/ReadMeABook/pull/241) ещё не слит.
2. `/media/disk1`, где лежит библиотека и torrent data, заполнен: `df` показывает
   100%, доступно лишь около 11.6 GB. RMAB одновременно хранит download для
   seeding, копирует результат в library, а merge создаёт дополнительный временный
   файл. Сначала нужен заметный запас диска.
3. ReadMeABook требует Prowlarr и download client. Prowlarr на `moscow` отсутствует;
   существующий Transmission можно переиспользовать, но его RPC whitelist сейчас
   возвращает HTTP 403 контейнеру из Docker bridge. Нужна отдельная контролируемая
   настройка whitelist и проверка фактического download path.
4. В `v1.2.2` открыт воспроизводимый ABS-баг
   [#287](https://github.com/kikootwo/ReadMeABook/issues/287): request может повторно
   скачать уже имеющуюся книгу даже при точном совпадении ASIN и создать duplicate.
   Для pilot обязательны approval workflow и ручная проверка перед каждым download.
5. Хост всё ещё работает на Ubuntu 21.10, которая снята с поддержки с 14 июля
   2022 года. Это не мешает canary технически, но запрещает считать новый публичный
   сервис безопасным production до миграции на поддерживаемую ОС.
   [Ubuntu 21.10 EOL notice](https://lists.ubuntu.com/archives/ubuntu-announce/2022-July/000281.html)

Итого: **разумный следующий шаг — Tailscale-only canary на `moscow`**, после
освобождения диска, с отключёнными FFmpeg-функциями, без auto-approve и с
ограниченным ABS API key. Для полноценного deployment нужен исправленный ARM64
image и устранение либо локальный guardrail для duplicate bug.

## Что такое ReadMeABook в этой схеме

ReadMeABook — не ещё один audiobook player и не замена Absorb. Это request и
ingest automation:

```text
пользователь выбирает книгу в ReadMeABook
  -> Prowlarr ищет release в настроенных indexers
  -> Transmission скачивает release
  -> ReadMeABook копирует и организует файлы в audiobook library
  -> Audiobookshelf сканирует library
  -> Absorb продолжает воспроизводить её через Audiobookshelf
```

Upstream описывает именно цепочку request -> Prowlarr -> download client -> file
organization -> library import. Прямых упоминаний или интеграции с Absorb в
дереве ReadMeABook нет: RMAB и Audiobookshelf совместно используют файловую
библиотеку, а Absorb остаётся только клиентом Audiobookshelf и filesystem mount
не получает. [README](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/README.md#what-is-this)

Для работы нужны **оба** канала:

- HTTP API к Audiobookshelf: server URL, отдельный Bearer API key и library ID;
- read-write mount каталога Audiobookshelf в RMAB как media directory.

Код RMAB читает ABS libraries/items, запускает library scan и metadata match, а
некоторые admin flows умеют удалить library item из базы ABS. Поэтому нельзя
переиспользовать ABS API key, выданный для Absorb; нужен отдельный auditable
key/service user с
минимальными правами и доступом только к audiobook library.
[ABS client implementation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/audiobookshelf/api.ts#L29-L202),
[Audiobookshelf API keys](https://audiobookshelf.org/docs/documentation/server-management/api-keys/)

## Официальные варианты установки

| Вариант | Состояние в `v1.2.2` | Оценка для `moscow` |
|---|---|---|
| Prebuilt unified image + root `docker-compose.yml` | Основной Quick Start; один container | Лучший базовый путь после ARM fix |
| `docker run` того же unified image | Документирован upstream | Работает, но Compose лучше фиксирует mounts и policy |
| Локальная сборка `docker-compose.local.yml` | Собирает `dockerfile.unified` | Подходит для временного ARM patch; собирать лучше не на Pi |
| External PostgreSQL/Redis | Поддержаны через `DATABASE_URL`/`REDIS_URL` | Для маленького сервера лишняя сложность |
| Multi-container `docker-compose.debug.yml` | Ссылается на отсутствующий `Dockerfile` | Не является рабочим production path текущего checkout |

Актуальный Quick Start использует `ghcr.io/kikootwo/readmeabook:latest`, port
`3030` и шесть persistent/shared mounts. Unified image запускает внутри одного
container Node/Next.js, PostgreSQL 16 и Redis под `supervisord`; Postgres и Redis
слушают только container loopback.
[README setup](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/README.md#L49-L92),
[root Compose](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker-compose.yml),
[supervisord config](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker/unified/supervisord.conf)

Документация upstream местами устарела: `deployment/unified.md` всё ещё называет
отсутствующий `docker-compose.unified.yml`, а debug multi-container file требует
отсутствующий `Dockerfile`. Поэтому будущий bundle должен основываться на root
Compose и реальном `dockerfile.unified`, а не на archived examples.

### Какой image фиксировать

На дату проверки:

- release: `v1.2.2`, опубликован 2026-08-11;
- OCI index digest: `sha256:91fb3ee1943678003cd9c86990430c6268428f52c6ea3fb8a57e179f84855d45`;
- ARM64 manifest digest:
  `sha256:3d54571bf27f004919b96f97935ef905cdae3eb5f3f31a86476bf286945c32be`;
- ARM64 compressed layers: примерно 1.06 GB;
- manifests есть для `linux/amd64` и `linux/arm64`, но нет `linux/arm/v7`.

Следовательно, Pi должен оставаться на `aarch64`. `latest` mutable и для
repo-managed deployment непригоден: после выбора решения надо pin release и
platform digest, как уже сделано для Audiobookshelf.

## Критический дефект ARM64 image

CI честно создаёт ARM64 manifest, но release Dockerfile независимо от target
architecture скачивает файл `ffmpeg-release-amd64-static.tar.xz`.
[workflow](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/.github/workflows/build-unified-image.yml#L67-L75),
[Dockerfile](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/dockerfile.unified#L35-L39)

Проверка самого опубликованного ARM64 OCI layer, а не только source, показала:

```text
/usr/local/bin/ffmpeg:  ELF 64-bit LSB executable, x86-64
/usr/local/bin/ffprobe: ELF 64-bit LSB executable, x86-64
```

На `moscow` не зарегистрированы `binfmt_misc` emulators, поэтому эти файлы не
исполняются. Issue #230 приводит тот же фактический результат на ARM:
`ffprobe: Exec format error`; metadata tagging пропускается, chapter merge
ломается. [Upstream issue #230](https://github.com/kikootwo/ReadMeABook/issues/230)

Возможные варианты для следующего этапа:

1. **Предпочтительно:** дождаться merge PR #241 и нового release, проверить OCI
   layer и canary перед production.
2. Собрать производный ARM64 image из `v1.2.2`, заменив два x86 binaries на
   нативный Debian `ffmpeg`, затем pin собственный digest и зафиксировать patch в
   repo bundle.
3. Только для короткого canary использовать stock ARM64 image, но отключить
   metadata tagging и chapter merging и не запускать bulk import.

Просто наличие ARM64 manifest не является достаточной проверкой. Будущий
preflight должен выполнить внутри image `uname -m`, `file $(command -v ffmpeg)` и
`ffmpeg -version` до доступа к production library.

## Инвентаризация `moscow`

Read-only SSH-проверка 2026-09-11:

| Объект | Фактическое состояние |
|---|---|
| Host | Raspberry Pi 4 Model B rev 1.4, `aarch64`, 4 CPU |
| RAM | 7.6 GiB total, около 6.1 GiB available, swap отсутствует |
| Состояние | uptime 81 день, load во время проверок низкий, температура 56-58 C |
| OS/kernel | Ubuntu 21.10, Linux 5.13 raspi |
| Docker | Engine 20.10.12, architecture `arm64` |
| Compose | Python `docker-compose` 1.27.4; upstream file проходит `config`, но команды `docker compose` verbatim недоступны |
| Root FS | 361 GB, около 225 GB свободно |
| `/media/disk1` | 4.6 TB, `df` = 100%, около 11.6 GB свободно |
| Audiobooks | около 132 GB, 84 каталога / 7881 файлов |
| Audiobookshelf | `2.36.0`, около 92-95 MiB RAM |
| Home Assistant | около 409 MiB RAM |
| Portainer | около 26 MiB RAM |
| Port 3030 | свободен |

По памяти остаётся большой запас даже с ориентиром upstream 500 MB–1 GB для
RMAB и отдельным Prowlarr. PostgreSQL внутри image использует
`shared_buffers=128MB`; тяжелее всего будет не idle web app, а аудиоконвертация.
[Entrypoint PostgreSQL settings](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker/unified/entrypoint.sh#L272-L282)

По CPU Pi также приемлем для UI, queues, database, scanning и обычного file copy.
Upstream отмечает высокую CPU-нагрузку при MP3 -> AAC/M4B, низкую память и
дополнительный temp space размером примерно с исходники; M4A/M4B codec-copy
существенно легче. Поэтому даже после ARM fix chapter merging лучше сначала
оставить выключенным и замерить одну тестовую книгу.
[Chapter merge resources](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/features/chapter-merging.md#L519-L542)

### Настоящий capacity blocker — storage

RMAB сохраняет исходный torrent для seeding и копирует аудиофайлы в media
library. Для chapter merge нужен temp output примерно `sum(inputs) + 10%`.
[File organization](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/phase3/file-organization.md#L39-L50),
[space check implementation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/utils/chapter-merger.ts#L908-L942)

При 11.6 GB free несколько больших releases могут одновременно заполнить диск,
сломать seeding, import и сам Audiobookshelf. До canary следует:

- выяснить, чем заняты остальные ~4.5 TB, и освободить согласованный reserve;
- задать download/queue limits;
- хранить RMAB config/cache/PostgreSQL/Redis на root FS, где есть 225 GB;
- media и downloads оставить на внешнем диске только после восстановления запаса;
- при включении merge смонтировать отдельный temp directory на root FS, а не
  оставлять большие временные файлы неявно в container overlay.

## Интеграция с существующим Audiobookshelf

### API path

Из существующего Audiobookshelf container успешно доступен host endpoint
`http://172.17.0.1:13378/status`. Значит RMAB не должен ходить в ABS через
публичный `books.nikcode.xyz` и London: это ненужный hairpin и дополнительная
точка отказа.

Для воспроизводимой схемы лучше создать custom Docker bridge и добавить
`host.docker.internal:host-gateway`; в setup использовать
`http://host.docker.internal:13378`. Альтернатива — стабильный gateway custom
subnet. Конкретную сеть следует зафиксировать в будущем Compose, не полагаясь на
случайный container IP.

### Library path и права

Существующая библиотека:

```text
host:      /media/disk1/media/Audiobooks
RMAB:      /media
ABS:       /audiobooks
mode:      0775, owner uid 113, group gid 1001
```

RMAB должен получить mount
`/media/disk1/media/Audiobooks:/media` с read-write доступом и настройку
`mediaDir=/media`. Однако identity нельзя выбирать только по этому каталогу:
предполагаемый Transmission download tree принадлежит `113:124` и имеет mode
`0755`, поэтому process `1001:1001` сможет его читать, но не пройдёт upstream
write validation для download directory.
[Setup wizard path validation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/setup-wizard.md#validation)

Least-change кандидат — `PUID=113`, `PGID=124`, `UMASK=002`: UID 113 уже владеет
как audiobook directory, так и предполагаемым download tree. RMAB state
directories на root FS тогда надо заранее подготовить для этой identity; Postgres
в unified image отдельно сохраняет UID 103 и использует выбранный `PGID`.
Альтернатива — dedicated service UID и явный shared-group/ACL plan для обоих
деревьев. Выбор запрещено фиксировать до получения точного Transmission path и
проверки permissions; валидировать надо отдельными probe files, не рекурсивным
`chown` существующей библиотеки.

### ABS credential и изменение metadata

Initial RMAB scan не гарантированно read-only: для ABS items без ASIN processor
вызывает `POST /api/items/{id}/match`; без найденного file hash это fuzzy match.
Ошибки best-effort и не останавливают общий scan.
[Scan processor](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/processors/scan-plex.processor.ts#L183-L255),
[match implementation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/audiobookshelf/api.ts#L140-L171)

Для canary:

- создать отдельного non-admin ABS service user/API key;
- дать read access только к нужной library;
- первоначально не давать `update`/`delete`, чтобы metadata match и delete не
  могли изменить production ABS;
- выключить `Trigger library scan after import` и положиться на watcher только
  после отдельной проверки;
- сделать согласованный backup ABS metadata/database до расширения прав.

## Интеграция с существующим Transmission

Текущий host Transmission уже предоставляет RPC на port `9091` с
authentication, поэтому новый qBittorrent не нужен. Но live-проверка дала:

```text
host-local request -> HTTP 401 (authentication required)
Docker bridge request -> HTTP 403 (RPC whitelist rejects source)
```

Следовательно, RMAB пока не сможет даже проверить connection. Безопасное решение
для отдельного implementation step:

1. создать маленький pinned custom Docker subnet для RMAB;
2. добавить только этот subnet в Transmission RPC whitelist;
3. сохранить RPC authentication;
4. bind UI RMAB только к Tailscale address;
5. не использовать `network_mode: host`: unified image помещает в тот же network
   namespace app, PostgreSQL и Redis, теряя полезную изоляцию и создавая риск port
   conflicts.

Фактический download directory Transmission не удалось доказать без elevated
read. Его **нельзя угадывать** по старым каталогам. Во время implementation надо
получить путь через Transmission RPC, затем mount того же host directory в RMAB.

Upstream требует совпадения видимого пути. Поскольку Transmission работает на
host, ожидаемая настройка будет такой:

```text
Transmission сообщает: <REMOTE_HOST_DOWNLOAD_PATH>
RMAB mount:             <REMOTE_HOST_DOWNLOAD_PATH>:/downloads
RMAB downloadDir:       /downloads
remote path mapping:    remote=<REMOTE_HOST_DOWNLOAD_PATH>, local=/downloads
```

[Volume mapping rule](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/deployment/volume-mapping.md),
[Transmission support](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/phase3/download-clients.md)

Prowlarr придётся добавить отдельным service. Его LinuxServer image официально
поддерживает ARM64, поэтому архитектурного препятствия нет; version и ARM64
digest надо pin при реализации.
[LinuxServer Prowlarr supported architectures](https://github.com/linuxserver/docker-prowlarr#supported-architectures)

## Duplicate risk в `v1.2.2`

Issue #287 описывает ReadMeABook `v1.2.2` с Audiobookshelf `2.36.0` — ровно наши
целевые версии. После успешного scan RMAB повторно скачал три книги, хотя в его
собственной library table уже были точные совпадения ASIN, и создал duplicates в
ABS. Issue остаётся открытым.
[Upstream issue #287](https://github.com/kikootwo/ReadMeABook/issues/287)

До upstream fix или собственного regression-tested patch:

- выключить auto-approve для всех пользователей;
- разрешить request/download только администратору canary;
- перед approval вручную искать книгу в Absorb/ABS и RMAB library view;
- ограничить canary несколькими заранее выбранными отсутствующими книгами;
- не включать watched-list/RSS automation;
- после каждого import проверять, что появился один item, и иметь простой
  rollback для нового каталога.

Approval workflow уже реализован upstream, поэтому этот guardrail не требует
изобретать отдельный сервис.
[Request approval](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/admin-features/request-approval.md)

## AI и GPU

AI не нужен для поиска, download, organization или интеграции с ABS. Он нужен
только для опционального BookDate:

- hosted OpenAI, Claude или Gemini API;
- либо доступный по сети OpenAI-compatible endpoint (`custom`), где API key может
  быть пустым для local model.

RMAB image не содержит model runtime или CUDA. Поэтому GPU на Pi не нужен, а
локальную LLM на этом же Pi не следует включать в первый этап: upstream не даёт
для неё Pi benchmark, и она будет конкурировать за RAM/CPU с media server. Если
BookDate понадобится, проще направить RMAB на внешний API или уже существующий
model host.
[BookDate provider implementation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/bookdate/helpers.ts#L550-L854),
[BookDate UI custom provider](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/admin/settings/tabs/BookDateTab/BookDateTab.tsx#L83-L160)

## Сеть, auth и secrets

Root Compose публикует `3030:3030` на всех интерфейсах. Для canary это следует
заменить bind на Tailscale address и не создавать public DNS. Первый setup wizard
создаёт admin account; выполнить его надо из доверенной сети до любого будущего
public ingress.

Если позже понадобятся OIDC/Plex OAuth и public URL, `PUBLIC_URL` должен точно
совпадать с HTTPS origin. Для локального auth canary он не обязателен.
[Environment documentation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/backend/services/environment.md#L7-L34)

Unified entrypoint один раз генерирует JWT secrets, encryption key и PostgreSQL
password и сохраняет их в `/app/config/.secrets` с mode 0600. ABS, Prowlarr,
Transmission и AI credentials хранятся в PostgreSQL в encrypted form, зависящем
от `CONFIG_ENCRYPTION_KEY`. Поэтому backup/restore unit должен согласованно
сохранять как минимум `config`, PostgreSQL и Redis; потеря `.secrets` отдельно от
DB лишит доступа к зашифрованным credentials.
[Entrypoint secrets](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker/unified/entrypoint.sh#L121-L151),
[configuration encryption](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/config.service.ts#L43-L183)

## Рекомендуемый план следующего этапа

### Gate 0 — не начинать deployment

- Освободить и зарезервировать место на `/media/disk1`.
- Решить ARM64 strategy: новый upstream release либо свой minimal patched image.
- Проверить статус issues #230/#287 и PR #241 непосредственно перед реализацией.
- Получить точный Transmission download directory через RPC.

### Gate 1 — reproducible isolated bundle

Создать отдельный repo-managed bundle под
`hosts/moscow/ubuntu/readmeabook/`, не редактировать container через Portainer.
Pin image/digest, custom bridge subnet, Tailscale-only UI bind, state directories
на root FS, mounts download/media, healthcheck, snapshot/rollback и read-only
preflight. Это соответствует принятой для `moscow` модели управления
Audiobookshelf.

### Gate 2 — canary settings

```text
Backend:                  Audiobookshelf
ABS URL:                  http://host.docker.internal:13378
ABS key:                  отдельный limited service key
ABS library:              текущая audiobook library
Trigger scan after import: off
Download client:          существующий Transmission
Prowlarr:                 новый pinned ARM64 service
Media dir:                /media
Download dir:             /downloads
Process identity:         tentative 113:124, подтвердить после path/permission preflight
Metadata tagging:         off до ARM fix validation
Chapter merging:          off до ARM fix и CPU/storage benchmark
BookDate:                 skip
Auto-approve:             off из-за issue #287
Watched/RSS automation:   off
```

### Gate 3 — проверка одной книги

1. Импортировать только специально выбранную отсутствующую короткую книгу.
2. Проверить путь и ownership нового каталога без изменения старых файлов.
3. Убедиться, что ABS watcher видит ровно один item и Absorb его воспроизводит.
4. Проверить seek/progress в Absorb.
5. Проверить, что Transmission продолжает seeding и RMAB не удалил source раньше
   policy.
6. Создать повторный request той же книги только в безопасной test flow и
   подтвердить, что guardrail блокирует download.
7. После исправления image отдельно проверить `ffmpeg -version`, metadata tagging,
   M4A codec-copy и только затем MP3 conversion.

## Решение

**Железо `moscow` подходит; текущая operational среда и stock image — пока нет.**
RPi4/8 GB способен обслуживать ReadMeABook, Prowlarr и существующие media services
при небольшом числе пользователей. Первым bottleneck будет storage, затем CPU во
время transcoding, а не RAM.

Следующая implementation-задача оправдана только после Gate 0. Оптимальная форма
— repo-managed Tailscale-only canary с существующим Transmission, отдельным
Prowlarr, ограниченным ABS key, отключённым auto-approve и исправленным ARM64
image. Публичный ingress и полная автоматизация — отдельные последующие решения
после стабильного canary и обновления ОС.
