# ReadMeABook на `um790pro`, библиотека и Transmission на `moscow`

**Дата проверки:** 2026-09-11  
**Статус:** research complete / architecture grill input; принятые решения
зафиксированы в
[`2026-09-11-readmeabook-um790pro-design.md`](./2026-09-11-readmeabook-um790pro-design.md).
Сервисы и конфигурации в рамках исследования не изменялись.  

**Проверенный ReadMeABook:** release
[`v1.2.2`](https://github.com/kikootwo/ReadMeABook/releases/tag/v1.2.2)
(`7c7d7bc`) и `main`
[`bc37186`](https://github.com/kikootwo/ReadMeABook/commit/bc371860d06c921e2f474ada226b7a3c6427fca5)

## Краткий вывод

`um790pro` с большим запасом подходит для ReadMeABook и Prowlarr: это x86_64
Ryzen 9 7940HS, 16 logical CPU, 61 GiB RAM и около 51 GiB available. Ошибка
официального ARM64 image с x86-64 FFmpeg здесь не применима.

Однако исходная split-host схема содержит более фундаментальную проблему:
**ReadMeABook не является только request UI**. Тот же процесс, который обслуживает
web/API, запускает фоновые processors и сам читает завершённые downloads, создаёт
и модифицирует media files и копирует их в библиотеку. Поддерживаемой отдельной
роли worker у проекта нет.

Поэтому при сохранении системного Transmission и storage на `moscow` контейнеру
ReadMeABook на `um790pro` недостаточно HTTP-доступа к Transmission и
Audiobookshelf. Ему нужны одновременно:

1. filesystem-доступ к completed downloads на `moscow`;
2. read-write filesystem-доступ к каталогу назначения на `moscow`.

Штатный RMAB копирует каждый файл обычными read/write streams. Если оба mount
физически находятся на `moscow`, каждый байт проходит
`moscow -> um790pro -> moscow`. Более опасно то, что запись идёт сразу в
окончательное имя, а retry пропускает любой уже существующий target без проверки
размера или checksum. Обрыв Tailscale/SMB/NFS способен оставить усечённый файл,
который следующий retry примет за готовый.
[stream copy](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/utils/copy-file.ts#L1-L22),
[existence-only retry](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/utils/file-organizer.ts#L365-L455)

Итоговая оценка:

- **для закрытого canary:** исходная схема возможна через два remote mounts;
- **для unattended production:** она недостаточно надёжна без fork или
  дополнительного проверяемого publisher/import stage;
- **наиболее простая production-схема:** оставить системный Transmission на
  `moscow` для текущих задач, но дать RMAB отдельный Transmission на `um790pro` и
  публиковать готовую книгу на `moscow` одним атомарным transfer;
- если именно переиспользование Transmission на `moscow` является жёстким
  условием, следует явно принять двойной network transfer и добавить
  integrity/atomic-publish слой.

## Проверяемая целевая топология

Исходная гипотеза:

```text
um790pro
├─ ReadMeABook unified container
│  ├─ web/API
│  ├─ Bull processors
│  ├─ PostgreSQL
│  └─ Redis
└─ Prowlarr
    │
    ├─ HTTP/Tailscale ──> moscow:13378 Audiobookshelf
    ├─ HTTP/Tailscale ──> moscow:9091 Transmission RPC
    └─ filesystem mount ─> moscow downloads + audiobook destination

moscow
├─ transmission-daemon 3.00
├─ Audiobookshelf 2.36.0
├─ /media/disk1/BT/download
├─ /media/disk1/media/Audiobooks
└─ Absorb clients
```

`Prowlarr` не требует filesystem mount: RMAB использует только его HTTP API.
[Prowlarr client](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/integrations/prowlarr.service.ts#L77-L205)

## Факты: live-состояние хостов

Read-only SSH-проверка 2026-09-11:

| Объект | `um790pro` | `moscow` |
|---|---|---|
| CPU/arch | Ryzen 9 7940HS, x86_64, 8C/16T | Raspberry Pi 4, aarch64 |
| RAM | 61 GiB total, около 51 GiB available, 61 GiB swap | Audiobookshelf и storage host |
| Root/storage | Btrfs 1.9 TiB, около 170 GiB free, 91% used | `/media/disk1` ext4 4.6 TiB, около 268 GiB free, 94% used |
| Docker | Engine 29.7.2, Compose 5.5.0 | Audiobookshelf container 2.36.0 |
| Tailscale | `100.95.213.117` | `100.81.67.47` |
| Активная ОС | CachyOS rolling | Ubuntu 21.10 |

На `um790pro` уже работает много container workloads, но текущего дефицита CPU
или RAM нет. Ограничение для local staging — свободное место: 170 GiB нельзя
считать безлимитным при root filesystem, заполненном на 91%.

Live network check с `um790pro` до `moscow`:

```text
tailscale ping:                 direct, около 117 ms
http://100.81.67.47:13378/status: HTTP 200
http://100.81.67.47:9091/transmission/rpc: HTTP 401
TCP 22 / 13378 / 9091 / 445:   reachable
TCP 2049:                      closed
```

HTTP 401 от Transmission означает, что путь доступен и RPC authentication
работает; это не тот HTTP 403 whitelist failure, который наблюдался с локального
Docker bridge на `moscow`. Реальный запрос с credentials и Docker network всё
равно является обязательным preflight.

На `moscow`:

```text
transmission-daemon: 3.00-1ubuntu2, systemd service, uid:gid 113:124
/media/disk1/BT/download:             uid:gid 113:124, mode 0755, около 5 GiB
/media/disk1/media/Audiobooks:        uid:gid 113:1001, mode 0775, около 132 GiB
Samba [media]: /media/disk1, RW, valid users = nik
NFS server: inactive
```

Точный текущий `download-dir` Transmission нельзя доказать без RPC credentials
или elevated read: `/etc/transmission-daemon/settings.json` имеет mode 0600.
Существование `/media/disk1/BT/download` — сильная улика, но не основание
фиксировать mapping. Implementation preflight должен вызвать authenticated
`session-get` и получить `download-dir`.
[Transmission session fields](https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#41-session-parameters)

## Факт: UI/API и worker штатно не разделяются

Unified image запускает PostgreSQL, Redis и один Next.js app process под
`supervisord`. После старта server entrypoint вызывает `/api/init`; scheduler
создаёт `JobQueueService`, а его constructor сразу регистрирует processors для
search, download, monitor, organization и scan.

Источники:

- [supervisord topology](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker/unified/supervisord.conf#L1-L48)
- [app startup and `/api/init`](https://github.com/kikootwo/ReadMeABook/blob/7c7d7bc7dd04c120d1ecffd5b48f37f0896a3a41/docker/unified/app-start.sh#L40-L143)
- [queue constructor starts processors](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/job-queue.service.ts#L196-L234)
- [processors include file organization](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/job-queue.service.ts#L324-L355)

В upstream нет отдельного worker command, worker image или documented
`WORKER_ROLE`/`DISABLE_PROCESSORS` mode. Вынести только filesystem-worker на
`moscow` нельзя изменением Compose. Для этого нужен fork/refactor, а запуск двух
обычных app replicas опасен: оба способны регистрировать processors и scheduler.

## Факт: какие paths действительно нужны RMAB

### Completed downloads

Transmission RPC возвращает `downloadDir`; RMAB формирует
`path.join(downloadDir, torrent.name)`, затем remote path mapping меняет только
строковый prefix. После этого organizer выполняет `stat`, recursive directory
walk, FFprobe/FFmpeg и read на локально видимом пути.

[Transmission path construction](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/integrations/transmission.service.ts#L509-L549),
[path mapper](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/utils/path-mapper.ts#L20-L127),
[official volume mapping rule](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/deployment/volume-mapping.md#L5-L32)

Следовательно, RPC не transport для media data. Download tree должен быть
смонтирован или предварительно синхронизирован на `um790pro`.

Даже read-only download mount не полностью соответствует stock defaults:

- setup wizard проверяет `download_dir` пробной записью;
- metadata tagging создаёт `${sourceFile}.tmp` рядом с torrent source и после
  copy удаляет temp;
- originals сохраняются для seeding.

[path write test](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/setup/test-paths/route.ts#L24-L43),
[tag temp path](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/utils/metadata-tagger.ts#L55-L90)

Для read-only canary source mount пришлось бы как минимум отключить tagging и
обойти/исправить write validation. Чище дать RMAB RW только отдельному download
subtree, а не всему `/media/disk1/BT/download`.

### Media destination

RMAB создаёт `[media_dir]/[path template]`, пишет audio и cover, выполняет chmod,
иногда rename format extensions и может создавать merged M4B. Значит destination
нужен RW. По умолчанию source сохраняется для seeding, то есть filesystem usage
временно удваивается.
[file organization](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/phase3/file-organization.md#L3-L50)

## Точное mapping-предположение для remote Transmission

После authenticated preflight и создания отдельного subtree ожидаемая форма:

```text
moscow Transmission download path:
  /media/disk1/BT/download/readmeabook

um790pro host mount:
  /srv/readmeabook-moscow/downloads

RMAB container mount:
  /srv/readmeabook-moscow/downloads:/downloads

RMAB settings:
  download_dir = /downloads
  remotePathMappingEnabled = true
  remotePath = /media/disk1/BT/download/readmeabook
  localPath  = /downloads
```

При `torrent-add` RMAB reverse-transforms `/downloads` обратно в московский
absolute path и передаёт его как per-torrent `download-dir`. После завершения
прямое mapping преобразует reported Moscow path в `/downloads/...`.
[RMAB torrent-add](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/integrations/transmission.service.ts#L217-L264),
[Transmission RPC torrent-add](https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#34-adding-a-torrent)

Это **предлагаемый контракт, не подтверждённая текущая настройка**. Отдельный
subtree требует согласованной ownership/ACL настройки: сейчас Samba user `nik`
не имеет Unix write permission в directory `113:124/0755`, даже если share
объявлен `read only = No`.

### Transmission 3.00 и labels

RMAB передаёт `labels: [category]` непосредственно в `torrent-add` и позже умеет
назначить `postImportCategory` через `torrent-set`.
[RMAB labels](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/integrations/transmission.service.ts#L238-L262),
[post-import category](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/processors/organize-files.processor.ts#L998-L1043)

У `moscow` Transmission 3.00. Его official 3.00 RPC spec поддерживает labels в
`torrent-get`/`torrent-set`, но не в `torrent-add`; добавление labels в
`torrent-add` отмечено только для Transmission 4.0.
[current RPC history](https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#protocol-version-history),
[Transmission 3.00 torrent-add contract](https://github.com/transmission/transmission/blob/bb6b5a062ee594dfd4b7a12a6b6e860c43849bfd/extras/rpc-spec.txt#L394-L422)

Source 3.00 просто не читает неизвестный `labels` argument при add, поэтому
torrent, вероятно, добавится, но начальная метка `readmeabook` не будет назначена.
Isolation нельзя строить только на label; отдельный download path остаётся
обязательным. Compatibility нужно подтвердить одним paused canary torrent либо
обновить Transmission отдельным решением.

## Cross-host data-plane варианты

| Вариант | Network path одной книги | Upstream changes | Integrity | Оценка |
|---|---|---:|---|---|
| A. Downloads и final media смонтированы с `moscow` на `um790pro` | `moscow -> UM -> moscow` | нет | слабая: direct final write, existence-only retry | только canary |
| B. Downloads с `moscow`, local staging на UM, затем verified publisher | `moscow -> UM`, затем `UM -> moscow` | publisher | можно сделать atomic | приемлемо, если Moscow Transmission обязателен |
| C. Отдельный Transmission + staging на UM, затем publisher | local organize, затем один `UM -> moscow` | publisher | можно сделать atomic | предпочтительно для production |
| D. RMAB filesystem-worker на `moscow` | local Moscow copy | fork/refactor RMAB | потенциально хорошо | самый дорогой в сопровождении |

### A. Два remote mounts

Можно использовать существующий SMB server или добавить NFS export. SMB уже
доступен по Tailscale на TCP/445; NFS сейчас выключен. У обоих один и тот же
application-level риск, потому что RMAB намеренно использует read/write streams,
а не server-side copy primitive.

Для NFS нельзя использовать `soft`: upstream `nfs(5)` предупреждает о возможной
silent data corruption. Default `hard` повторяет запросы неограниченно, поэтому
при недоступном `moscow` RMAB process может надолго зависнуть. Нужны `_netdev`,
network-online ordering, mountpoint assertions и fail-closed запуск container.
[Linux `nfs(5)`](https://man7.org/linux/man-pages/man5/nfs.5.html),
[`systemd.mount(5)`](https://man7.org/linux/man-pages/man5/systemd.mount.5.html)

У upstream есть реальный пример remote download server, где файл появлялся на
локальном mount с задержкой и первый organization получал `ENOENT`. Конкретный
ebook retry bug закрыт, но сам факт delayed filesystem visibility применим к
split-host design.
[ReadMeABook issue #55](https://github.com/kikootwo/ReadMeABook/issues/55)

Direct remote media mount также открывает RMAB write access к production library.
Его надо ограничить отдельным folder, а не всем существующим деревом.

### B. Moscow Transmission + local staging + publisher

RMAB читает отдельный московский download subtree, но пишет сначала на локальный
NVMe `um790pro`. Отдельный publisher:

1. определяет завершённую organization job;
2. синхронизирует книгу во временный directory на `/media/disk1`;
3. проверяет manifest/size/checksum;
4. делает local atomic directory rename на `moscow`;
5. только после этого инициирует или ждёт ABS scan;
6. удаляет local staging лишь после подтверждения наличия книги в ABS.

Это не upstream feature. Нельзя объявлять production готовым publisher, который
ориентируется только на timeout/mtime: нужен явный completion signal или чтение
состояния RMAB job и idempotent manifest.

Network volume остаётся двойным, но final library никогда не видит намеренно
частичный каталог. На UM требуется bounded staging quota: свободно около 170 GiB.

### C. Dedicated Transmission для RMAB на `um790pro`

Существующий system Transmission на `moscow` остаётся без изменений для прочих
задач. Новый download client обслуживает только RMAB. Download, tagging, merge и
organization выполняются на локальном NVMe; publisher передаёт готовую книгу на
`moscow` один раз и атомарно публикует её.

Это наиболее простая production architecture по data integrity и bandwidth, но
она меняет решение «RMAB обязан пользоваться существующим Transmission». Кроме
того, seeding потребляет место и upload bandwidth `um790pro`, поэтому нужны quota,
concurrency limit и cleanup policy.

### D. Worker на `moscow`

Архитектурно красиво оставить control plane на UM, а copy/tag/import worker рядом
с диском. Но stock RMAB этого не умеет. Нужны как минимум role-separated
entrypoints, shared external Postgres/Redis, гарантированно single scheduler,
отдельная registration processors и regression tests. Это уже собственный fork,
не Compose-настройка.

## Прозрачная дополнительная папка Audiobookshelf

Audiobookshelf library содержит массив `folders`; scanner объединяет items из
всех folders под одним library ID.
[ABS Library schema](https://github.com/advplyr/audiobookshelf/blob/e8ed9870343f2fa54771020f1c130e46ac9e319f/docs/objects/Library.yaml#L70-L100),
[LibraryScanner](https://github.com/advplyr/audiobookshelf/blob/e8ed9870343f2fa54771020f1c130e46ac9e319f/server/scanner/LibraryScanner.js#L143-L165)

Рекомендуемая физическая граница:

```text
/media/disk1/media/Audiobooks   # существующие книги
/media/disk1/media/ReadMeABook  # только новые imports
```

В текущий ABS container смонтирован только первый host path как `/audiobooks`.
Чтобы второй стал folder той же библиотеки, требуется:

```text
host /media/disk1/media/ReadMeABook -> ABS container /readmeabook
ABS existing library folders:
  - /audiobooks
  - /readmeabook
```

Это одна библиотека, а не две: library ID, browse/search и user permissions
остаются общими. Следовательно, Absorb продолжает использовать тот же ABS server
и library, а новые items появляются после scan без настройки отдельной клиентской
библиотеки. Последнее — вывод из сохранения library ID; его надо подтвердить
canary в используемой версии Absorb.

Не следует создавать `/media/disk1/media/Audiobooks/ReadMeABook` как лишний
wrapper-level внутри текущего root: ABS определяет книгу как folder и ожидает
структуру `{Author}/{Book}`; дополнительный top-level способен исказить grouping.
[ABS directory structure](https://audiobookshelf.org/docs/documentation/libraries/book-library/directory-structure/)

Отдельный sibling folder также позволяет выдать RMAB RW только новому дереву и
откатить одну imported book directory, не затрагивая старые книги.

## Сеть, auth и blast radius

Предлагаемые private endpoints:

```text
RMAB -> Prowlarr:     http://prowlarr:9696         # private Compose network
RMAB -> ABS:          http://100.81.67.47:13378   # Tailscale
RMAB -> Transmission: http://100.81.67.47:9091    # Tailscale + Basic Auth
RMAB UI:              100.95.213.117:3030         # Tailscale-only bind
Prowlarr UI:          no host publish, либо loopback/Tailscale admin-only
```

Transmission RPC использует HTTP POST, CSRF session ID и optional HTTP Basic
Auth. Текущий daemon требует auth. Host/IP whitelist и authentication — разные
проверки.
[Transmission RPC transport/auth](https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md#22-transport-mechanism),
[Transmission RPC settings](https://github.com/transmission/transmission/blob/main/docs/Editing-Configuration-Files.md#rpc)

ABS key должен быть отдельным от Absorb и действовать от минимально
привилегированного service user. RMAB не только читает libraries/items: его scan
может вызывать metadata match для items без ASIN. Ручной `trigger library scan`
в ABS требует admin, поэтому для canary лучше выключить
`trigger_scan_after_import` и полагаться на watcher/существующий periodic scan.
[RMAB ABS API client](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/services/audiobookshelf/api.ts#L29-L202),
[ABS scan authorization](https://github.com/advplyr/audiobookshelf/blob/e8ed9870343f2fa54771020f1c130e46ac9e319f/server/controllers/LibraryController.js#L1254-L1273),
[ABS API keys](https://audiobookshelf.org/docs/documentation/server-management/api-keys/)

Открытый issue RMAB #287 описывает ровно v1.2.2 + ABS 2.36.0: уже имеющиеся книги
повторно скачиваются даже при exact ASIN match. Split-host deployment это не
исправляет. До upstream fix нужны manual approval, проверка ABS перед download,
выключенные watched/RSS automation и canary на отсутствующей книге.
[ReadMeABook issue #287](https://github.com/kikootwo/ReadMeABook/issues/287)

SMB/NFS mount credentials должны находиться в root-only host credential file, а
не в Compose YAML. RMAB secrets (`config/.secrets`), PostgreSQL, Redis и Prowlarr
`/config` требуют согласованных snapshots. Нельзя публиковать 3030/9696 на
`0.0.0.0` по upstream examples без отдельного ingress/auth решения.

## Prowlarr и ресурсы

Prowlarr x86-64 image официально поддерживается. Ему нужен только persistent
`/config`, PUID/PGID/TZ и internal port 9696; media mounts не нужны.
[LinuxServer Prowlarr](https://github.com/linuxserver/docker-prowlarr/blob/main/README.md)

Upstream оценивает unified RMAB примерно в 500 MB–1 GB RAM; на `um790pro` это
малозначимо по сравнению с 51 GiB available. FFmpeg tagging и chapter merge будут
работать на x86_64 и получат значительно больше CPU, чем на Pi. GPU для основного
workflow не нужен.
[RMAB resource estimate](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/archive/README.unified.md#L191-L203),
[chapter merge resources](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/features/chapter-merging.md#L519-L542)

Тем не менее local staging, downloads и merge temp обязаны иметь quota/space
guard: root filesystem уже 91% full. State и media staging нельзя оставлять
неограниченными в container overlay.

## Рекомендация

### Если Moscow Transmission — жёсткое условие

Разрешён только **Tailscale-only manual canary**, не unattended production:

1. отдельный Moscow download subtree и отдельный final ABS folder;
2. узкий SMB/NFS export, а не RW ко всему `/media/disk1`;
3. authenticated Transmission `session-get` для точного mapping;
4. fail-closed mount checks до запуска container;
5. metadata tagging и chapter merge выключены;
6. ABS trigger scan, auto-approve, watched lists и RSS выключены;
7. одна заведомо отсутствующая короткая книга;
8. после download вручную проверить sizes/duration всех targets до ABS scan;
9. смоделировать restart/временную потерю mount до расширения pilot.

Для production добавить verified publisher и atomic publication либо делать
собственный RMAB fork с локальным worker на `moscow`.

### Если можно оставить Moscow Transmission только для старых задач

Предпочтительная production topology:

```text
um790pro:
  ReadMeABook + Prowlarr + dedicated Transmission
  local downloads + local staging + persistent state

verified publisher over Tailscale:
  local staging -> moscow hidden incoming -> checksum -> atomic rename

moscow:
  /media/disk1/media/ReadMeABook
  second folder of the existing ABS library
```

Так media bytes пересекают WAN один раз, RMAB никогда не пишет непосредственно в
видимую ABS library, текущий Transmission и существующие книги изолированы.

## Решения для следующего grill

Ниже именно решения пользователя, а не факты, которые ещё надо «исследовать»:

1. **Обязательно ли RMAB должен использовать Transmission на `moscow`?**
   Рекомендация: нет; оставить его для старых задач, создать dedicated client на
   UM.
2. **Canary или сразу production contract?** Рекомендация: canary независимо от
   выбранного data plane из-за issue #287.
3. **Допустим ли отдельный verified publisher?** Рекомендация: да; без него remote
   final writes не дают приемлемой atomicity.
4. **Можно ли добавить sibling folder в существующую ABS library?** Рекомендация:
   да, `/media/disk1/media/ReadMeABook` как второй folder того же library ID.
5. **Какова seeding policy и storage quota на UM?** Зависит от решения 1;
   рекомендованы bounded queue и reserve threshold.
6. **Нужны ли tagging/merge в первом pilot?** Рекомендация: нет; включать по одному
   после проверки базового import и publisher.
7. **Кто получает доступ к UI?** Рекомендация: один admin через Tailscale; public
   ingress и family accounts — после canary.

## Что остаётся проверить перед реализацией

- authenticated `session-get` и paused `torrent-add` против Transmission 3.00;
- Docker-container reachability `um790pro -> moscow`, не только host curl;
- actual Tailscale throughput небольшим disposable fixture, без чтения всей
  библиотеки;
- exact ABS library folders и watcher settings через отдельный service key;
- CIFS/NFS ownership на disposable directories под будущей RMAB identity;
- image digests для RMAB и Prowlarr непосредственно перед deployment;
- текущий статус issue #287;
- restore rehearsal для RMAB state и one-book rollback.
