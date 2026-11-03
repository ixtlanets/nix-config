# Московский VLESS pilot: подготовка, переход на Caddy и откат

## Статус развёртывания 2026-10-31

Серверный пилот развёрнут на Ubuntu `132.243.191.232`: Caddy обслуживает HTTPS-подписки на 443 и автоматически получил сертификат Let's Encrypt; sing-box 1.13.5 принимает VLESS+REALITY на 24443 и отправляет пользовательский трафик через Frankfurt:24443. Обе службы active/enabled, перезапусков после установки нет. nginx и certbot установлены, но nginx и certbot.timer inactive/disabled; прежний сертификат сохранён.

Независимые Standards/Spec проверки и повторные проверки исправлений завершены. Parent выполнил 24/24 offline-теста без пропусков, включая Caddy 2.6.2 и Xray 26.10.31; оба настоящих профиля также прошли Xray `run -test`. До и после hardening прошли семь runtime-проверок: московский egress, прямой резерв, неверный UUID, изолированный отказ outbound без прямого выхода, HTTPS-подписки и отрицательные пути, состояния служб, отсутствие секретов в journal. Google через московский профиль вернул 204; одновременно на Frankfurt наблюдался трафик к London:1080. Последнее подтверждает работающий London-путь, но не исключительное причинное соответствие одного пакета одному запросу на общем узле.

SSH принимает только publickey, root-доступ по ключу сохранён. Firewall разрешает входящие TCP 22/80/443/24443, established/related, loopback и ICMP; остальные входящие блокируются. Отдельный SSH-сеанс по ключу проверен, таймер отката отменён. zenbook, Frankfurt, London и Goar не изменялись; PID рабочего zenbook 1257, Frankfurt engine 1043631 сохранены.

Подготовлена одна персональная пилотная подписка. Импорт/обновление в реальном Incy, домашние 500 Мбит/с и параллельная нагрузка ещё не проверены; массового перевода нет. Целевой контракт: [moscow1-vless-target.md](moscow1-vless-target.md). Приватные receipts, идентичность и архив восстановления хранятся в `/home/nik/.local/state/moscow1-setup-20261031/`; серверный staging и откат - `/root/moscow1-pilot-20261031/` и `/var/backups/moscow1/caddy-pilot-03`.

`moscow1-vless.service` разрешает `AF_NETLINK` в `RestrictAddressFamilies`:
sing-box подписывается на обновления маршрутов, иначе запуск завершается с
`subscribe route updates: address family not supported by protocol`.
Это непривилегированная подписка; capabilities остаются пустыми, TUN не используется.

## Состав и приватные данные

`hosts/moscow1/ubuntu/vless/build.py` — offline CLI Python stdlib. Он принимает
приватный JSON и **новый** каталог вывода, отказывается перезаписывать каталог или
следовать симлинку вывода. Внешний формат ввода сохранён. Родительский каталог
ввода/вывода должен быть root-owned, `0700`; сами файлы — `0600`. Секреты и
результат генерации не помещать в публичный репозиторий. CLI не печатает входные
данные, UUID, токены или ссылки. Содержимое `private-input.json` читает только
parent при подготовке/выполнении генерации.

Поля входа (значения ниже — описания/PLACEHOLDER, не готовая конфигурация):

```json
{
  "hostname": "moscow1.nikcode.xyz",
  "ip": "132.243.191.232",
  "reality_private_key": "PLACEHOLDER_X25519_PRIVATE_BASE64URL",
  "reality_public_key": "PLACEHOLDER_MATCHING_PUBLIC_BASE64URL",
  "short_id": "PLACEHOLDER_EVEN_LOWERCASE_HEX_2_TO_16",
  "frankfurt_outbound": "PLACEHOLDER_SING_BOX_VLESS_OBJECT",
  "devices": [{
    "name": "pilot",
    "uuid": "PLACEHOLDER_FRESH_MOSCOW_UUID",
    "subscription_token": "PLACEHOLDER_SECRETS_TOKEN_URLSAFE_32",
    "direct_frankfurt_outbound": "PLACEHOLDER_DEVICE_EXISTING_SING_BOX_VLESS_OBJECT"
  }]
}
```

Оба outbound-объекта имеют allowlist: `type=vless`, `server=31.58.85.163`,
`server_port=24443`, `uuid`, `flow=xtls-rprx-vision`, `tls`; необязательные `tag`
и `packet_encoding=xudp`. TLS: `enabled=true`, `server_name`,
`utls={enabled:true,fingerprint:...}`, `reality={enabled:true,public_key:...,short_id:...}`;
`insecure` допускается только `false`. Обходы вроде `detour`, произвольных адресов,
дополнительных полей и повторных JSON-ключей отклоняются. Ключи — канонические
32-байтовые base64url без padding; short ID — 1–8 байт hex. UUID Москвы свежие,
не совпадают с транзитом/резервом; имена, UUID, токены и резервные UUID устройств
уникальны. Длину токена проверяет генератор, криптографическую случайность
обеспечивает parent (`secrets.token_urlsafe(32)`).

Parent подставляет только разрешённые существующие Frankfurt identities;
генератор не добавляет пользователей во Frankfurt. Транзит пилота использует ранее
разрешённую identity, это не заявление о конечной выделенной identity. Пока
готовится одно реальное pilot-устройство; синтетический тест двух устройств не
означает готовность массового перехода. Нельзя придумывать резервные UUID.

Пример запуска parent в приватном каталоге (без печати результата):

```bash
umask 077
python3 hosts/moscow1/ubuntu/vless/build.py "$PRIVATE_INPUT" "$NEW_PRIVATE_BUNDLE"
```

Генерируются `server.json`, `Caddyfile`, две unit-конфигурации, подписки
`subscriptions/s/<token>/incy.json` и loopback sing-box клиенты в `client-tests/`.
JSON подписки — массив **полных Xray-конфигураций**: Moscow первым, Frankfurt direct
backup вторым. Поля sing-box преобразуются в Xray: `uuid` → `settings.vnext[].users[].id`,
`server/server_port` → `address/port`, `tls.reality.public_key/short_id` →
`streamSettings.realitySettings.publicKey/shortId`, `utls.fingerprint` → `fingerprint`,
`packet_encoding` → `settings.packetEncoding`. Flow, SNI и персональная резервная
identity сохраняются. Основной профиль использует отдельные московские ключи и
`24443`, SNI `www.google.com`, fingerprint `firefox`.

Каждый профиль включает SOCKS `127.0.0.1:10808`, HTTP `127.0.0.1:10809`, IPv4 DNS,
статический bootstrap московского имени, DoH через proxy, прямые private/RU
исключения, блок UDP 443, затем proxy. Это Incy pilot; специальные существующие
правила других платформ требуют отдельной адаптации, без молчаливой унификации.
Резерв выбирается вручную, автоматического failover нет. Поддержка массива и
сохранение резерва после обновления должны проверяться в реальной Incy.

## Caddy и защита подписок

Одна штатная `caddy.service` Ubuntu обслуживает HTTPS 443 и HTTP 80. Сертификаты
получает/продлевает сам Caddy, хранилище `/var/lib/caddy/moscow1` (`caddy:caddy 0700`),
без ссылки на существующий LE сертификат. nginx/certbot и `/etc/letsencrypt` остаются
для отката. Renewal hook не нужен и не устанавливается.

HTTP имеет catchall 404, без перенаправления токенов на HTTPS. Встроенный обработчик
ACME Caddy должен перехватывать активные challenges перед обычными HTTP routes;
это отдельный native gate проверки на установленной версии. HTTPS обслуживает
только `/healthz` и точные raw URI персональных JSON, GET/HEAD. Query string,
альтернативное percent encoding, лишние slash, traversal, подкаталоги и другие
методы/пути не совпадают с raw URI. После совпадения путь файла фиксирован rewrite;
корень статический, browse нет, reverse proxy нет. Дерево копируется без симлинков.
`Cache-Control: no-store` задаётся и для контента, и для обычных/ошибочных ответов.

Файлы подписок — `root:caddy 0640`, каталоги `0750`, `Caddyfile` — `root:caddy 0640`:
он содержит токены. Caddy может читать, но не изменять подписки/конфигурацию.
Admin только `localhost:2019`; автосохранение конфигурации отключено. Caddy 2.6.2
не понимает Caddyfile `persist_config`: `adapt-caddy.py` приватно адаптирует
Caddyfile в native JSON, устанавливает `admin.config.persist=false`, а deploy
валидирует и устанавливает `/etc/caddy/moscow1.json` (`root:caddy 0640`). Unit
запускает именно JSON; Caddyfile остаётся защищённым исходником. Access log не
включён. Runtime namespace `http.log.access`, `http.log.error`, `admin.api` исключены
из default logger: они могут включать URI или конфигурацию. TLS/ACME operational
messages сохраняются. Не включать debug или дополнительные log sinks. Parent обязан
проверить journald на синтетическом токене после native запуска, включая ошибки.

Адаптация/валидация Caddy может напечатать секретные пути. Никогда не запускать
`caddy adapt`, `validate`, `fmt --diff`, `cat Caddyfile` с выводом в общие логи.
Установщик перенаправляет диагностику в root-only backup. Parent любые свои
проверки также перенаправляет в приватные файлы, без публикации содержимого.

## Первый переход (выполняет parent на Москве)

1. Подтвердить официальный Ubuntu apt origin пакетов `caddy`, `nginx`, `certbot`,
   штатный Caddy unit и account. Установить их через apt отдельно; deploy не ставит
   пакеты, не скачивает файлы, не меняет firewall. nginx должен быть active на 80,
   `certbot.timer` enabled; дождаться завершения уже запущенного certbot job.
2. Сохранить пакетный `/etc/caddy/Caddyfile` в отдельном root-only backup, записать
   его SHA256 и состояния Caddy, остановить пакетный Caddy и **отдельно** убрать
   default из `/etc/caddy/Caddyfile`. Не считать, что эти команды уже выполнялись.
   Установщик откажется от любого существующего Caddyfile, даже похожего на default;
   не удаляет и не «усыновляет» его. Откат deploy возвращает состояние на момент
   запуска deploy; восстановление предварительно убранного default — отдельный шаг
   parent из этой копии. Не трогать nginx config или `/etc/letsencrypt`.
   Текущее исходное состояние Caddy — inactive/masked. Перед deploy parent явно
   выполняет `systemctl unmask caddy.service`, проверяет inactive/disabled и сохраняет
   это в preflight evidence. Deploy не поддерживает masked. Его rollback возвращает
   состояние после unmask; для полного возврата parent отдельно восстанавливает
   пакетный Caddyfile и исходную маску, проверяет nginx и certbot timer.
3. Проверить, что 443 свободен и нет посторонних пользователей Caddy. Проверить
   бинарник sing-box 1.13.5:
   `a056076cff3aa1ced5ed794743b9f87b2dee7dc068280d2665c1e0b45533e793`.
   Проверить bundle и заморозить его хэши для review; не менять во время установки.
4. Запустить локально, без SSH-обёртки внутри script:

   ```bash
   bash hosts/moscow1/ubuntu/vless/deploy.sh install "$PRIVATE_BUNDLE" "$PINNED_BINARY" /var/backups/moscow1/caddy-pilot-01
   ```

   IP guard проверяет локальный адрес `132.243.191.232`, OS guard — Ubuntu. Это
   установщик **первого** перехода: отказывается при существующих task paths или
   неизвестных overrides. Восемь task paths и точные stable active/enabled состояния
   четырёх служб сохраняются перед изменениями в новом root-only backup. Неизвестные,
   masked, failed или transitional состояния требуют ручного разбора parent.
   Действующие nginx config и LE certificate не изменяются. Candidate Caddy и
   sing-box проверяются до остановки nginx. Собственный Caddyfile публикуется
   атомарным rename защищённого файла с managed marker.
5. Скрипт останавливает только nginx и certbot timer, запускает Caddy и новый
   `moscow1-vless`. До 180 попыток curl (каждая максимум 5 секунд, пауза 2 секунды)
   проверяют доверенный TLS, hostname и `/healthz` по loopback; `-k` не используется.
   Это ограниченное окно для cold ACME: регистрация первого ACME account может
   предшествовать challenge. На второй попытке регистрации потребовалась 61 секунда,
   и challenge начался уже при исчерпании прежних 30 попыток; ACME error пока не было.
   На первой попытке сертификат был выдан за 8 секунд и затем удалён корректным
   rollback. Новый предел ожидания curl/пауз — не более 21 минуты
   (`180 × (5 + 2) = 1260` секунд, без накладных расходов shell/systemctl);
   при быстрых отказах TLS окно около 6 минут (`180 × 2 = 360` секунд плюс
   фактическое время запросов). Это не означает, что каждый запрос занимает 5 секунд.
   Не обходить TLS и не переиспользовать токен. Перед третьей попыткой parent
   независимо проверяет и проводит Standards/Spec review окончательных байтов.
   Только после успеха nginx/timer disable, Caddy/Moscow enable. ERR/INT/TERM вызывают
   откат файлов и прежних stable service states. SIGKILL/потеря питания требуют
   ручного rollback из сохранённого backup. Ошибки rollback не прячутся.
   Обе новые службы проверяются по отдельности; после enable/disable выполняется
   повторное чтение active/enabled. ERR/INT/TERM также удаляют принадлежащий
   транзакции временный Caddyfile до rename; посторонние файлы не затрагиваются.
6. До принятия parent выполняет native gates ниже. Успех health не доказывает VLESS.

Откат из сохранённого снимка, локально на Москве (прерывает pilot-соединения):

```bash
bash hosts/moscow1/ubuntu/vless/deploy.sh rollback /var/backups/moscow1/caddy-pilot-01
```

Откат останавливает только task Caddy/Moscow, восстанавливает task paths и прежние
active/enabled состояния nginx, timer, Caddy, Moscow. Продолжает восстановление
остальных элементов при отдельной ошибке. Созданные этой транзакцией Moscow
account/group удаляются. nginx запускается с исходным конфигом и сохранённым
сертификатом; никакого package purge и глобального service restart нет. После
отката parent проверяет исходный nginx TLS и состояние timer. Backup хранить
приватно до принятия. Не повторять rollback после дальнейших несвязанных изменений
этих служб: сначала сравнить текущее состояние с снимком.

## Проверки и последующие изменения

Offline, без реальных credentials/конфигов и без установки зависимостей:

```bash
MOSCOW1_SING_BOX=/path/to/pinned/sing-box python3 -m unittest discover -s tests -p test_moscow1_vless.py -v
python3 -m py_compile hosts/moscow1/ubuntu/vless/build.py tests/test_moscow1_vless.py
bash -n hosts/moscow1/ubuntu/vless/deploy.sh
```

Если Caddy есть, тест адаптирует синтетическую конфигурацию и проверяет JSON,
не запускает listener/ACME и не provision-ит серверные пути. Если Xray есть,
проверяет оба полных профиля `run -test`. Отсутствие Caddy/Xray — **не PASS** этих
проверок; это parent gate. Exact sing-box check — проверка парсера, не сети.

Parent gates перед признанием pilot рабочим:

- Две независимые review окончательных байтов; native Caddy adapt/validate, затем
  TLS с автоматическим сертификатом, ACME HTTP exception и catchall HTTP 404.
- HTTPS GET/HEAD токена дают ровно JSON нужного устройства; другой токен, query,
  encoding, traversal (`curl --path-as-is`), лишние slash, POST и directory paths
  дают 404/no-store. Отсутствующий файл тоже даёт 404/no-store. Для токенов использовать
  приватный curl config и root-only output, чтобы URL не попал в argv/history/log.
- Проверить отсутствие тестового токена/полного URI в runtime/access/error logs;
  сохранность TLS operational messages и правильные owner/mode всех файлов.
- VLESS по Москве и прямому резерву, неверный UUID, специальные London routes,
  отключение выбранного outbound без прямого выхода из Москвы. Существующие
  Frankfurt engine, zenbook tunnel, London/Goar не перезапускать и не менять.
- Реальный импорт/обновление Incy и ручной резерв при недоступности Москвы;
  домашние 500 Мбит/с по всей цепочке и параллельная нагрузка.

Ручная смена московского outbound после отдельного review: сохранить приватный
`server.json`, подготовить candidate только с разрешённым outbound, выполнить
pinned `sing-box check` с приватной диагностикой, установить `root:moscow1 0640`
атомарным rename и перезапустить **только** `moscow1-vless.service`. Это разрывает
текущие pilot-соединения. При неуспехе вернуть старые байты и перезапустить только
эту службу. Нет автоматического failover, панели или API.

Отзыв токена останавливает обновление подписки, но не отзывает уже импортированные
UUID. Отзыв устройства требует удаления его московского UUID и отдельного
разрешённого отзыва персонального прямого резерва во Frankfurt. Резервную копию
московской идентичности хранить отдельно: DNS не переносит ключи/short ID/UUID.
