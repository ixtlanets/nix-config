# ReadMeABook split-host bundle

Этот каталог реализует утверждённую схему: ReadMeABook, Prowlarr, внутренние
FlareSolverr и RuTracker gateway, а также отдельный Transmission работают на
`um790pro`; проверенный publisher атомарно публикует книги в новое дерево на
`moscow`; существующие Audiobookshelf, системный Transmission и Absorb не
заменяются.

Реализация в репозитории сама ничего не разворачивает. До canary все timers
должны оставаться выключенными.

## Состав

- `docker-compose.yml` и `Dockerfile.readmeabook` — digest-pinned
  RMAB/Prowlarr/FlareSolverr/RuTracker-gateway/Transmission bundle; локальный
  RMAB image содержит проверенный compatibility patch для Transmission;
- `scripts/rutracker_gateway.py` — fail-closed compatibility gateway, который
  возвращает Prowlarr browser response FlareSolverr без HTTP-client replay;
- `scripts/publisher.py` — fail-closed manifest publisher и immutable ledger;
- `scripts/remote-wrapper.py` — forced SSH command, ограниченный incoming/final roots;
- `scripts/torrent-policy.py` — 50 GiB quota, одна активная загрузка, seed cleanup;
- `scripts/preflight.sh` — read-only проверки обоих хостов;
- `scripts/backup.sh` и `scripts/restore-rehearsal.sh` — backup и изолированная
  проверка восстановления;
- `systemd/` — publisher, cleanup, torrent policy, backup и health timers;
- `moscow/audiobookshelf-readmeabook.override.yml` — migration override для
  первого подключения read-only mount к существующему ABS container; постоянная
  декларация также находится в `hosts/moscow/ubuntu/audiobookshelf/`.

Полный rationale и canary gates находятся в
[`../../../../docs/superpowers/specs/2026-09-11-readmeabook-um790pro-design.md`](../../../../docs/superpowers/specs/2026-09-11-readmeabook-um790pro-design.md).

## Проверка в checkout

```bash
hosts/um790pro/docker/readmeabook/tests/run.sh
```

Тесты рендерят оба Compose-варианта и используют только disposable временные
каталоги, fake API и fake Docker. Они не подключаются к `um790pro` или `moscow`.

## Runtime paths и network

| Назначение | Путь или endpoint |
|---|---|
| Bundle на UM | `/home/nik/.local/share/nix-config-services/readmeabook` |
| Container state | `/home/nik/services/readmeabook` |
| Publisher state | `/home/nik/.local/state/readmeabook-publisher` |
| Operator config | `/home/nik/.config/readmeabook` |
| Persistent root-only secrets | `/etc/readmeabook/secrets` |
| RMAB UI | `http://100.95.213.117:3030` |
| Prowlarr UI | `127.0.0.1:9696`, только через SSH tunnel |
| FlareSolverr | `http://flaresolverr:8191`, только внутри Compose network |
| RuTracker gateway | `http://rutracker-gateway:8080`, только внутри Compose network |
| Moscow incoming | `/media/disk1/media/.readmeabook-incoming` |
| Moscow final | `/media/disk1/media/ReadMeABook` |
| ABS mount | `/readmeabook`, read-only |

Transmission не имеет host port и доступен RMAB как `http://transmission:9091`.
Policy подключается к адресу container bridge, найденному через `docker inspect`,
и отправляет `Host: transmission`; password не попадает в argv.

Upstream RMAB v1.2.2 считает любой ненулевой `torrent.error` окончательным
failure. Transmission использует эти коды также для временных tracker warning и
tracker error, хотя загрузка через DHT/PEX может продолжиться. Локальный image
patch меняет terminal condition на `error === 3` (local error); коды 1 и 2
остаются под обычным мониторингом. Build fail-closed, если ожидаемый mapper в
закреплённом upstream image не найден.

FlareSolverr и RuTracker gateway также не имеют host ports. Gateway разрешает
только `rutracker.org` и paths `/`/`/forum/*`, принимает POST только для
`/forum/login.php`, ограничивает размер body и не ведёт access log. Prowlarr
использует gateway как Base URL RuTracker; прямой FlareSolverr Indexer Proxy для
этого indexer не нужен. FlareSolverr log level остаётся `warning`, потому что
`info` журналирует POST body с учётными данными indexer.

## Secrets

Authoritative copy должна находиться в `secrets/readmeabook/um790pro/`. Путь
защищён правилом `git-crypt` в корневом `.gitattributes`. Не добавлять secrets,
пока checkout не разблокирован и `git check-attr filter -- <file>` не показывает
`git-crypt`.

Runtime нужны persistent-файлы mode `0600` в root-owned каталоге
`/etc/readmeabook/secrets` mode `0700`:

- `rmab-jwt-secret`;
- `rmab-jwt-refresh-secret`;
- `rmab-config-encryption-key`;
- `rmab-postgres-password`;
- `transmission-password`;
- `rmab-api-token` — отдельный publisher token, используемый только для read
  calls (ограничение scopes описано ниже);
- `abs-api-token` — отдельный минимально привилегированный ABS token;
- `publisher-ssh-key` — отдельный private key без passphrase для systemd credential.

RMAB secrets читаются container entrypoint из Compose secrets и не появляются в
rendered Compose. Prowlarr/indexer credentials и RMAB admin password вводятся
через UI; их recovery copy также хранится только в зашифрованном secret bundle.
Нельзя переиспользовать credential Absorb или обычный interactive SSH key.

RMAB v1.2.2 не поддерживает scopes для API tokens. Обычный user token видит
только собственные requests и не получает нужное publisher поле `filePath`,
поэтому runtime `rmab-api-token` вынужденно наследует admin role. Publisher
использует его только для `GET /api/requests` и `GET /api/requests/:id`; token
хранится root-only и не передаётся контейнерам. Это upstream limitation, которое
нужно пересмотреть при обновлении RMAB.

## Подготовка `moscow`

Этот шаг выполняется отдельно после review. Он не изменяет старое дерево
`/media/disk1/media/Audiobooks` и существующий Transmission.

1. Установить wrapper из этого bundle как
   `/home/nik/.local/libexec/readmeabook-remote-wrapper.py`, owner `nik:nik`, mode
   `0755`.
2. Привилегированно создать incoming с `nik:nik`, mode `0700`, и final с
   `nik:nik`, mode `2775`. Оба каталога обязаны быть на одном filesystem.
3. Добавить public key в `/home/nik/.ssh/authorized_keys` одной строкой:

```text
restrict,command="READMABOOK_INCOMING_ROOT=/media/disk1/media/.readmeabook-incoming READMABOOK_FINAL_ROOT=/media/disk1/media/ReadMeABook READMABOOK_RSYNC_BIN=/usr/bin/rsync /home/nik/.local/libexec/readmeabook-remote-wrapper.py" ssh-ed25519 REPLACE_WITH_DEDICATED_PUBLIC_KEY readmeabook-publisher
```

`restrict` запрещает PTY, forwarding, agent/X11 forwarding и user rc. Wrapper
дополнительно canonicalize paths, запрещает symlinks и принимает только
capacity/prepare/rsync/verify/promote/unpublish protocol.

Проверка на самом `moscow`:

```bash
READMABOOK_INCOMING_ROOT=/media/disk1/media/.readmeabook-incoming \
READMABOOK_FINAL_ROOT=/media/disk1/media/ReadMeABook \
READMABOOK_ABS_URL=http://127.0.0.1:13378 \
./scripts/preflight.sh --host moscow
```

## Подготовка `um790pro`

`um790pro` сейчас работает под CachyOS (Arch Linux), поэтому этот bundle не
использует находящийся в репозитории старый NixOS-профиль хоста. Перед deployment
проверить и при необходимости установить runtime-зависимости:

```bash
sudo pacman -S --needed curl docker docker-compose ffmpeg openssh python rsync util-linux
sudo systemctl enable --now docker.service
```

Это операторские команды для будущего отдельного deployment-шага; реализация в
репозитории их не выполняет. Пакет `util-linux` предоставляет `/usr/bin/flock`,
которым systemd jobs сериализуют publisher, cleanup, torrent policy и backup.
При пересечении расписаний job ожидает общий lock до 30 минут, а не завершается
ошибкой из-за штатной конкуренции.

После этого:

1. Скопировать весь bundle в runtime bundle path, сохранив executable bits.
2. Создать state directories под `nik:nik`; downloads и staging находятся только
   под state root, не в Git checkout.
3. Скопировать `publisher.example.json` и `torrent-policy.example.json` в
   operator config без суффикса `.example`, заменить ABS library ID.
4. Развернуть runtime secrets root-only.
5. Скопировать unit templates в `/etc/systemd/system/` и выполнить только
   `systemctl daemon-reload`. Timers пока не включать.
6. Запустить read-only preflight:

```bash
sudo ./scripts/preflight.sh --host um790pro
```

7. Проверить rendered config, затем вручную запустить Compose:

```bash
sudo docker compose config
sudo docker compose pull prowlarr transmission flaresolverr rutracker-gateway
sudo docker compose build --pull readmeabook
sudo docker compose up -d
```

## Первичная настройка UI

Prowlarr открывается локально через tunnel:

```bash
ssh -L 9696:127.0.0.1:9696 nik@um790pro
```

В RMAB настроить:

- Prowlarr URL `http://prowlarr:9696` и отдельный API key;
- в Prowlarr настроить RuTracker Base URL
  `http://rutracker-gateway:8080/` и включить `Use Magnet Links`;
- Transmission URL `http://transmission:9091`, user `readmeabook` и dedicated
  password;
- download path `/downloads`, media path `/media`;
- audiobook template `{author}/{title} {asin}`;
- Audiobookshelf `http://100.81.67.47:13378`, существующий library ID и отдельный
  token;
- manual request/release approval;
- `trigger_scan_after_import`, RSS, BookDate, ebooks, watched lists, tagging,
  merge и transcoding выключены;
- seeding time 10080 minutes; окончательное правило ratio/time обеспечивает
  `torrent-policy.py`.

После завершения setup отдельно открыть `Admin -> Scheduled Jobs` и выключить
все внутренние расписания RMAB. В v1.2.2 мастер включает их независимо от
настроек отдельных features. Особо важно оставить выключенными `Library Scan`
и `Recently Added Check`: для каждого существующего ABS item без ASIN эти jobs
вызывают `POST /api/items/:id/match` в Audiobookshelf и тем самым могут изменить
metadata старой библиотеки. Initial library scan в мастере следует прервать после
первичного импорта каталога, до этой metadata-match фазы.

## Ежедневное использование

1. Открыть `http://100.95.213.117:3030/search` и искать по названию, автору или
   чтецу.
2. Открыть нужную карточку и нажать `Request`.
3. В `Admin -> Request Management` одобрить заявку. Если она остановилась в
   `Awaiting Release`, через `Actions` выбрать точный релиз RuTracker, сверив
   автора, название, чтеца, формат и размер.
4. Дождаться статуса `Downloaded`. Одобрять и доводить до `Downloaded` книги
   по одной: publisher намеренно блокируется при нескольких новых кандидатах.
5. Пока идёт семидневный canary soak и publisher timer выключен, вручную
   выполнить `sudo systemctl start readmeabook-publisher.service`. После
   production cutover publisher заберёт одну готовую книгу автоматически в
   течение пяти минут.
6. Книга появляется в существующей библиотеке Audiobookshelf и автоматически
   становится доступна в Absorb. Проверить автора, чтеца, серию и номер книги;
   неполные torrent-теги при необходимости исправить в Audiobookshelf.

Отклонение заявки, выбор релиза и request/release approval всегда остаются
ручными. ReadMeABook не получает права изменять metadata старого Audiobooks tree.

Setup-admin в RMAB всегда обходит request approval. Для ежедневных requests
использовать отдельного local user с ролью `user` и выключенным global
auto-approve; setup-admin используется для approval, выбора release и
администрирования.

### Ручная заявка для книг вне Audible

Если книга не находится в основном UI, `scripts/manual-request.py` создаёт
обычную заявку от `nik-requester` по точному RuTracker topic ID. Скрипт сначала
проверяет, что requester имеет роль `user` и для него не действует auto-approve.
Без `--execute` команда только показывает выбранный релиз; секретные download
URL и GUID в вывод не попадают.

```bash
cd ~/.local/share/nix-config-services/readmeabook

READMABOOK_ADMIN_PASSWORD_FILE=<(pass api/readmeabook/admin | sed -n '1p') \
READMABOOK_REQUESTER_PASSWORD_FILE=<(pass api/readmeabook/requester | sed -n '1p') \
python3 scripts/manual-request.py --config manual-request.example.json \
  search --title 'Кляксы' --author 'Конофальский Борис'

READMABOOK_ADMIN_PASSWORD_FILE=<(pass api/readmeabook/admin | sed -n '1p') \
READMABOOK_REQUESTER_PASSWORD_FILE=<(pass api/readmeabook/requester | sed -n '1p') \
python3 scripts/manual-request.py --config manual-request.example.json \
  request --title 'Кляксы' --author 'Конофальский Борис' \
  --topic-id 6887881
```

После сверки title, размера, формата и seeders повторить вторую команду с
`--execute`. Безопасный результат — только `awaiting_approval`; любое другое
состояние считается ошибкой. Затем администратор отдельно одобряет заявку в UI.

Synthetic ID не существует в Audible/Audnexus, поэтому RMAB не может надёжно
дополнить такую заявку серией, номером в серии, годом, жанрами и чтецом. После
появления exact-path item в ABS оператор обязан сверить эти поля с первичным
каталогом и исправить metadata через ABS UI. Это намеренно не делает publisher:
его ABS credential используется только для read calls, и publisher не получает
право изменять старую библиотеку. При неоднозначной нумерации различать номер в
общей серии и номер в подцикле; например, «Глубокий рейд. Книга 4. КЛЯКСЫ» —
`Рейд #8`, хотя внутри подцикла «Глубокий рейд» это книга 4.

Для ручных заявок используется synthetic ID вида
`manual:rutracker:<topic-id>`. Publisher не ищет такой ID в ABS и подтверждает
публикацию по точному рассчитанному пути. Пароли передаются скрипту через
process substitution и не сохраняются в runtime config.

## Publisher и lifecycle

До canary publisher запускается только вручную через unit:

```bash
sudo systemctl start readmeabook-publisher.service
journalctl -u readmeabook-publisher.service
```

Полезные безопасные команды:

```bash
python3 scripts/publisher.py --config ~/.config/readmeabook/publisher.json status
sudo env CREDENTIALS_DIRECTORY=/etc/readmeabook/secrets \
  python3 scripts/publisher.py --config /home/nik/.config/readmeabook/publisher.json run-once
python3 scripts/publisher.py --config ~/.config/readmeabook/publisher.json cleanup --json
sudo env CREDENTIALS_DIRECTORY=/etc/readmeabook/secrets \
  python3 scripts/torrent-policy.py --config /home/nik/.config/readmeabook/torrent-policy.json status --json
```

Dry `run-once` не пишет ledger и не передаёт файлы. Любая ошибка execute-run
сохраняет общий `blocked.json`; после выяснения причины блок снимается только
командой `acknowledge --execute`.

RMAB сохраняет container path вида `/media/<author>/<book>`, тогда как publisher
работает с host path под `staging_root`. Пара `rmab_media_root`/`staging_root` в
publisher config задаёт явное отображение; после него canonical containment
проверяется повторно, поэтому `..`, symlink и пути вне staging отклоняются.

Staging удаляется лишь после точного ABS path+ASIN confirmation и окна 24 часа.
Torrent data удаляется только для hash, связанного с записью `published` в
ledger, когда достигнут ratio 1.0 или прошло семь дней. Неоднозначные/failed
pending entries автоматически не удаляются.

## Добавление folder в Audiobookshelf

Только после успешной публикации canary и snapshot существующих ABS
config/database/metadata применить вместе с текущим Moscow Compose файл
`moscow/audiobookshelf-readmeabook.override.yml`. Он добавляет единственный
read-only bind mount и не меняет старый `/audiobooks` mount. После canary тот же
mount должен быть закреплён в repo-managed
`hosts/moscow/ubuntu/audiobookshelf/docker-compose.yml`, чтобы дальнейшая
синхронизация Moscow bundle не откатила topology.

После recreate container в существующей audiobook library через ABS UI добавить
folder `/readmeabook`. Не создавать новую library и не менять permissions
существующих пользователей. Absorb перенастраивать не нужно.

## Backup, rehearsal и upgrades

Backup без `--execute` только показывает sources. Execute-run кратко pause/unpause
пять контейнеров, создаёт PostgreSQL custom dump, копирует RMAB/Prowlarr/
FlareSolverr/Transmission config, operator config, secrets и publisher ledger, пишет
`SHA256SUMS` и атомарно публикует root-only snapshot в
`/var/backups/readmeabook`. Downloads, staging, pgdata и Redis files исключены.
После `unpause` Docker может сохранять переходный `unhealthy` до следующего
30-секундного container probe; внешний healthcheck повторяет проверку достаточно
долго, чтобы не поднимать ложную тревогу после штатного backup.

```bash
sudo ./scripts/backup.sh
sudo ./scripts/backup.sh --execute
sudo ./scripts/restore-rehearsal.sh --backup /var/backups/readmeabook/ID
sudo ./scripts/restore-rehearsal.sh --backup /var/backups/readmeabook/ID --execute
```

Rehearsal проверяет checksums и ledger, восстанавливает копию файлов только под
disposable rehearsal root и реально загружает dump в одноразовый PostgreSQL 16
container с pinned digest. Production paths не принимаются.

Перед image bump обязателен новый backup и успешный rehearsal. В rollback
используются совместимые image digests и весь соответствующий state snapshot;
после DB migration запрещено откатывать только image.

## Manual unpublish

Сначала preview, затем отдельная execute-команда с тем же immutable manifest ID:

```bash
python3 scripts/publisher.py --config ~/.config/readmeabook/publisher.json \
  unpublish MANIFEST_ID
sudo systemctl start readmeabook-unpublish@MANIFEST_ID.service
```

Команда находит ровно одну active publication в ledger и remote wrapper удаляет
только каталог с совпадающим sidecar manifest внутри нового final tree. Старый
Audiobooks tree недоступен wrapper.

Execute запускается только через template-unit от `nik`: так SSH использует
закреплённый `/home/nik/.ssh/known_hosts`, а ledger и `blocked.json` не получают
root-владельца. Прямой запуск `publisher.py unpublish --execute` через `sudo`
запрещён.

После удаления каталога watcher Audiobookshelf помечает запись как
`Отсутствует` (`isMissing=true`), но не удаляет её из базы. Оператор должен
открыть `Audiobookshelf -> Проблемы`, сверить единственную запись с preview path
и удалить только запись из базы, предварительно сняв флажок `Удалить из файловой
системы`. Publisher token остаётся read-only (`delete=false`); не расширять его
права ради редкой ручной операции unpublish.

## Canary gate

Timers остаются disabled, пока вручную не пройдены:

1. однофайловый M4B;
2. многофайловый MP3;
3. обрыв transfer и идемпотентный retry после acknowledgement;
4. duplicate request с fail-closed block;
5. ровно один новый ABS item;
6. playback, seek и progress в Absorb;
7. preview+execute unpublish canary item;
8. backup restore rehearsal;
9. семь дней без необъяснённых ошибок.

Только после этого включаются `readmeabook-publisher.timer`,
`readmeabook-cleanup.timer`, `readmeabook-torrent-policy.timer`,
`readmeabook-backup.timer` и `readmeabook-healthcheck.timer`. Manual release
approval остаётся включённым навсегда.
