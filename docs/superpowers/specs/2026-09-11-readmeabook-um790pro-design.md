# ReadMeABook на UM790Pro: утверждённый split-host design

**Дата:** 2026-09-11

**Статус:** superseded 2026-09-12 by
[`2026-09-12-hermes-audiobook-automation-design.md`](./2026-09-12-hermes-audiobook-automation-design.md)

**Research:**
[`2026-09-11-readmeabook-um790pro-split-host-research.md`](./2026-09-11-readmeabook-um790pro-split-host-research.md)

## Цель

Развернуть ReadMeABook как приватный request и ingest service на `um790pro`, не
перенося существующий Audiobookshelf, его библиотеку или текущий системный
Transmission с `moscow`.

Новые книги должны появляться в той же библиотеке Audiobookshelf и быть
прозрачно доступны существующим клиентам Absorb. Ошибка или остановка
`um790pro` не должна нарушать чтение уже опубликованной библиотеки.

## Главные ограничения upstream

- Stock ReadMeABook объединяет web/API и Bull processors в одном процессе и не
  предоставляет отдельную worker role. Перенести штатный filesystem worker на
  `moscow` настройкой Compose нельзя.
- ReadMeABook должен локально видеть completed downloads и writable media
  directory. Transmission RPC не переносит файлы; remote path mapping заменяет
  только строковый prefix.
- Организатор пишет сразу в окончательные имена и при retry пропускает уже
  существующий target без проверки размера или checksum.
- RMAB `filesHash` строится по именам файлов, а не по содержимому.
- Post-import webhook или completion marker отсутствует. Статус `downloaded`
  доступен через read-only API, но должен использоваться только как semantic
  trigger для отдельной проверки publisher.
- В RMAB v1.2.2 открыт duplicate bug
  [#287](https://github.com/kikootwo/ReadMeABook/issues/287) для интеграции с
  Audiobookshelf 2.36.0.

Эти ограничения исключают прямую unattended-запись из RMAB в remote ABS
library. Между local staging и production library вводится отдельный verified
publisher.

## Утверждённая топология

```text
um790pro
├── repo-managed Compose bundle
│   ├── ReadMeABook unified container
│   ├── Prowlarr
│   ├── FlareSolverr (internal-only)
│   ├── RuTracker compatibility gateway (internal-only)
│   └── dedicated Transmission
├── local downloads
├── local RMAB media staging
├── persistent RMAB/Prowlarr/Transmission state
└── publisher + ledger
     │
     └── rsync/SSH через Tailscale
          │
          ▼
moscow
├── /media/disk1/media/.readmeabook-incoming
├── /media/disk1/media/ReadMeABook
├── существующий Audiobookshelf
│   ├── /audiobooks   -> существующая библиотека
│   └── /readmeabook  -> новый sibling folder
├── существующий system Transmission (без изменений)
└── Absorb (без изменений)
```

Предполагаемое место исходников bundle:
`hosts/um790pro/docker/readmeabook/`. Runtime state, downloads, staging и
plaintext secrets не находятся в Git worktree.

## Границы ответственности

### `um790pro`

- обслуживает UI/API ReadMeABook;
- выполняет поиск через Prowlarr;
- использует внутренний FlareSolverr через ограниченный RuTracker gateway;
- скачивает только RMAB jobs через отдельный Transmission;
- организует книги в local staging;
- проверяет содержимое и публикует готовые каталоги на `moscow`;
- хранит request/publisher state и временные данные.

FlareSolverr и RuTracker gateway не публикуют host ports. Prowlarr использует
gateway как RuTracker Base URL, а gateway передаёт разрешённые `/forum/*`
запросы в `http://flaresolverr:8191` и возвращает browser response напрямую.
Это необходимо, потому что повторный HTTP-client request с Cloudflare cookies
снова получает 403. Gateway не хранит credentials, не ведёт access log,
запрещает произвольные target hosts и binary torrent downloads; Prowlarr
использует magnet links. Трафик к доменам RuTracker направляется существующим
host-level sing-box через лондонский маршрут; остальные контейнеры сохраняют
обычный VLESS egress.

### `moscow`

- остаётся источником истины для опубликованных media;
- продолжает обслуживать Audiobookshelf и Absorb независимо от `um790pro`;
- принимает только проверенные книги в отдельное дерево;
- не предоставляет RMAB write access к старому
  `/media/disk1/media/Audiobooks`;
- существующий `transmission-daemon` не используется RMAB и не изменяется.

## Пользовательский workflow

1. Setup-admin входит в RMAB через tailnet только для approval и управления.
2. Отдельный local user создаёт request; admin вручную подтверждает request и
   конкретный release.
3. Dedicated Transmission скачивает release локально на `um790pro`.
4. RMAB копирует и организует исходники в local media staging.
5. Publisher обнаруживает готового кандидата через read-only RMAB API.
6. Publisher проверяет RMAB state и локальные файлы.
7. Книга передаётся в hidden incoming tree на `moscow`.
8. Publisher сверяет destination manifest и атомарно переименовывает каталог в
   видимый final path.
9. Audiobookshelf watcher обнаруживает новую книгу во втором folder той же
   library.
10. Publisher подтверждает exact path+ASIN через read-only ABS API. Встроенные
    RMAB `Library Scan` и `Recently Added Check` остаются выключенными: v1.2.2
    вызывает ABS metadata match для старых items без ASIN.
11. Absorb показывает и воспроизводит книгу без новой клиентской настройки.

После canary механические шаги 3–10 автоматизируются. Выбор и approval release
навсегда остаются ручными.

## RMAB → publisher contract

### Semantic trigger

Publisher использует отдельный static RMAB API token только для read calls:

1. опрашивает `GET /api/requests` по завершённым audiobook requests;
2. получает detail через `GET /api/requests/:id`;
3. требует `request.status=downloaded` либо более поздний completed status;
4. требует `audiobook.status=completed`;
5. canonicalizes `audiobook.filePath` и требует, чтобы он находился строго под
   configured staging root;
6. при наличии job result требует последний `organize_files` со статусом
   `completed`, `success=true`, тем же target path и пустым `errors`.

Job result усиливает проверку, но не является единственным источником истины.
Publisher не читает PostgreSQL RMAB напрямую, не парсит logs и не считает один
filesystem quiet period доказательством завершённости.

В RMAB v1.2.2 API tokens не имеют scopes. Для чтения всех requests вместе с
`filePath` нужен token, наследующий admin role; обычный user token видит только
свои requests и не получает это поле. Поэтому credential изолирован в root-only
systemd credential и publisher ограничивает себя двумя GET endpoints. После
обновления RMAB это временное исключение следует заменить настоящим read-only
scope.

### Content validation

До network transfer publisher:

- запрещает symlinks, devices, sockets и пути за пределами staging root;
- принимает только утверждённые audio extensions;
- требует минимум один audio file;
- запускает `ffprobe` для каждого audio file и требует ненулевую duration;
- строит отсортированный manifest из relative path, byte size и SHA-256;
- повторяет построение manifest после stability interval и требует полного
  совпадения двух проходов;
- проверяет отсутствие `.part`, `.tmp` и других незавершённых файлов;
- проверяет disk reserve на обоих хостах;
- выполняет duplicate guard по request ID, ASIN, final path и данным ABS.

Любая неоднозначность считается ошибкой и блокирует публикацию.

### Transfer и atomic publication

1. `rsync` пишет в уникальный hidden incoming directory на том же ext4
   filesystem, что и final library.
2. Файлы не видны Audiobookshelf во время передачи.
3. На `moscow` заново вычисляются размеры и SHA-256; они должны совпасть с source
   manifest.
4. Publisher убеждается, что final book path отсутствует.
5. Incoming book directory переименовывается в final path одним local
   filesystem `rename`.
6. Manifest сохраняется в publisher ledger и вместе с опубликованной книгой как
   служебный JSON sidecar.

Шаблон final path:

```text
/media/disk1/media/ReadMeABook/{author}/{title} {asin}
```

Это штатный default RMAB template. Поддерживаемые в выбранной версии variables:
`author`, `title`, `narrator`, `asin`, `year`; series placeholders отсутствуют.

### Идемпотентность

Ledger keyed по RMAB request ID и содержит как минимум:

- request ID;
- ASIN, если есть;
- canonical staging и final paths;
- полный content manifest;
- timestamps transfer, publication и ABS confirmation;
- lifecycle status и последнюю ошибку.

Повторный запуск с тем же request ID и manifest является no-op. Несовпадение
manifest, уже существующий final path или возможное совпадение в ABS блокируют
pipeline до ручного решения.

## Audiobookshelf

Новый host path:

```text
/media/disk1/media/ReadMeABook
```

однократно монтируется в существующий ABS container как `/readmeabook` и
добавляется вторым folder той же audiobook library. Существующий library ID и
права пользователей сохраняются; отдельная библиотека не создаётся.

RMAB получает отдельный минимально привилегированный ABS service credential. Он
не может удалять или изменять старые items. `trigger_scan_after_import`
выключен: обнаружение выполняет ABS filesystem watcher или существующий
периодический scan. Publisher не изменяет ABS database.

Перед добавлением folder создаётся snapshot существующих ABS config, database и
metadata, а также копия текущего Compose. Media tree целиком не дублируется.

## Network и authentication

- RMAB bind: `100.95.213.117:3030`, только Tailscale address.
- RMAB использует локальную admin account с уникальным password; OIDC не нужен.
- Prowlarr не публикует host port. Первичная ручная настройка выполняется через
  SSH port forwarding.
- RMAB, Prowlarr и Transmission используют private Compose network.
- Dedicated Transmission имеет outbound network, но в canary не получает
  public peer-port forwarding.
- Tailscale Serve не изменяется: его основной URL уже занят другим service.
- Публичный reverse proxy и DNS для RMAB отсутствуют.

## Publisher SSH identity

Publisher подключается к `moscow` как существующий пользователь `nik`, но
использует отдельный keypair. Запись key в `authorized_keys` запрещает PTY,
agent/X11/TCP forwarding и произвольный shell. Forced-command wrapper принимает
только узкий протокол операций внутри двух разрешённых roots:

- hidden incoming;
- final `/media/disk1/media/ReadMeABook`.

Wrapper обязан canonicalize все paths и запрещать traversal, symlinks и
операции над старым audiobook tree. Он предоставляет только необходимые rsync,
manifest verification, atomic rename и explicit unpublish operations.

Новый final tree создаётся один раз с owner `nik:nik`, mode `2775`; каталоги
сохраняют setgid, обычные media files получают mode `0664`. Родительский
`/media/disk1/media` сейчас не writable для `nik`, поэтому bootstrap требует
отдельного привилегированного шага.

## Secrets

Зашифрованный authoritative source хранится под
`secrets/readmeabook/um790pro/` и защищён существующим `git-crypt` workflow.
Plaintext material разворачивается вне Compose bundle как persistent root-only
files в `/etc/readmeabook/secrets` и не попадает в Git, generated Compose output
или logs. Systemd выдаёт job только заявленные credentials через собственный
временный credential directory.

К secrets относятся:

- RMAB application/encryption secrets;
- RMAB local admin bootstrap credential;
- Prowlarr API key и indexer credentials;
- dedicated Transmission RPC credential;
- minimal ABS API credential;
- restricted publisher SSH private key.

Нельзя переиспользовать ключи Absorb или обычный interactive SSH private key.

## Content policy

- В canary включены только обычные audiobook requests.
- BookDate, ebook sidecars, Goodreads/Hardcover shelves, RSS и watched-list
  automation выключены.
- Русский язык предпочтителен, английский разрешён; сомнительные release
  требуют явного approval.
- Предпочтительны M4B и M4A; MP3 и FLAC разрешены.
- AA/AAX, DRM content и неподдерживаемые форматы отклоняются.
- Metadata tagging, chapter merge и transcoding выключены для первого canary и
  включаются позже по одному после отдельной проверки.
- Prowlarr indexers первоначально настраиваются вручную; credentials не
  описываются в Compose или design docs.

## Capacity и lifecycle

- Одновременно активна не более одной RMAB download.
- Downloads и media staging вместе ограничены 50 GiB.
- Release больше 20 GiB отклоняется.
- Новая загрузка запрещена, если свободно меньше 100 GiB на `um790pro` или
  меньше 200 GiB на `moscow`.
- Torrent source сохраняется до ratio `1.0` или семи дней, в зависимости от
  того, что наступит раньше. Поскольку штатные RMAB cleanup controls не
  выражают весь этот контракт, его обеспечивает отдельная guarded cleanup
  policy.
- Local organized staging удаляется только после ABS confirmation и
  24-часового safety window.
- Failed/incomplete staging изолируется на семь дней, после чего удаляется
  только если ledger доказывает, что данные не используются.

## Failure model

Pipeline работает fail closed:

- publisher validation или network failure создаёт persistent blocked state;
- новые RMAB downloads не продолжаются до ручного acknowledgement;
- бесконечные retries запрещены;
- partial remote transfer остаётся только в hidden incoming;
- ABS никогда не видит incomplete book;
- ambiguity duplicate guard не превращается в warning-only flow.

Внешних уведомлений нет. RMAB UI, publisher status command и `journalctl`
являются единственными surfaces наблюдения. Поэтому blocked state должен быть
явно виден в status output и сохраняться после reboot.

## Backup и upgrade

Ночной backup включает:

- PostgreSQL dump RMAB;
- RMAB config и encryption material;
- Prowlarr config;
- publisher ledger;
- dedicated Transmission config.

Downloads и staging не резервируются. Перед каждым upgrade создаётся
application-consistent backup, фиксируются текущие image digests и готовится
совместимая команда rollback. Возврат только старого image без соответствующего
state запрещён после database migration.

RMAB, Prowlarr и Transmission pin по version и OCI digest. `latest` и
автоматические image updates запрещены. Release notes и canary повторяются перед
каждым bump.

## Rollback опубликованной книги

Publisher предоставляет только ручную команду:

```text
unpublish <manifest-id>
```

Она:

1. находит ровно один final directory по immutable ledger record;
2. показывает paths и manifest оператору;
3. требует явного подтверждения;
4. удаляет только этот directory внутри нового `ReadMeABook` tree;
5. никогда не принимает path старой библиотеки.

Автоматический unpublish по timeout запрещён. Если ABS ошибочно связал новый
folder с существующим item, дальнейшая автоматизация останавливается и для
восстановления используется pre-change ABS metadata snapshot.

## Canary

Publisher запускается вручную. Systemd polling timer выключен до прохождения
всех gates:

1. импорт заведомо отсутствующего однофайлового M4B;
2. импорт многофайлового MP3;
3. искусственный обрыв SSH/transfer и безопасный idempotent retry;
4. повторный request уже имеющейся книги и подтверждение fail-closed duplicate
   guard;
5. появление ровно одного нового ABS item;
6. воспроизведение, seek и сохранение progress в Absorb;
7. проверка manual `unpublish` на canary item;
8. restore rehearsal RMAB state и publisher ledger;
9. семь дней без необъяснённых ошибок.

После gates включается systemd timer с интервалом пять минут. Release approval
остаётся ручным.

## Process supervision

- RMAB, Prowlarr и dedicated Transmission управляются repo-owned Compose.
- Publisher, backup, cleanup и health checks управляются systemd units/timers.
- Docker restart policies не заменяют dependency и failure checks publisher.
- На CachyOS сервисы остаются repo-owned Compose bundle и systemd templates;
  старый NixOS-профиль `um790pro` в этой работе не используется.

## Реализация в репозитории

Bundle, publisher, guarded remote wrapper, torrent lifecycle policy, unit и
disposable filesystem tests, read-only preflight, backup/restore rehearsal,
systemd templates, Moscow Compose override и canary runbook находятся в
`hosts/um790pro/docker/readmeabook/`.

Следующий этап — review generated configuration и destructive path guards,
после чего deployment выполняется отдельным подтверждённым шагом.

До отдельного подтверждения запрещено:

- запускать или пересоздавать containers на `um790pro`;
- менять существующий Transmission на `moscow`;
- добавлять mount/folder в production Audiobookshelf;
- создавать remote media directories или authorized key;
- применять старый NixOS-профиль `um790pro`;
- начинать canary download.

## Out of scope

- публичный ingress;
- семейные accounts или OIDC;
- перенос существующих книг;
- изменение существующего system Transmission;
- изменение Absorb;
- собственный split-worker fork ReadMeABook;
- BookDate, ebook automation, RSS или watched lists;
- автоматический выбор release;
- внешние Telegram/Home Assistant notifications;
- tagging, merge и transcoding в первом canary.
