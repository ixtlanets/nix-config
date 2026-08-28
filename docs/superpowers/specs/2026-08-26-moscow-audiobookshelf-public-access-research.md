# Публичный доступ к Moscow Audiobookshelf на `books.nikcode.xyz`

**Дата проверки:** 2026-08-26  
**Статус:** исследование завершено; схема развёрнута 2026-08-26, operational
handoff находится в
[`docs/handoffs/2026-08-26-audiobookshelf-public-ingress.md`](../../handoffs/2026-08-26-audiobookshelf-public-ingress.md)

## Краткий вывод

Для постоянного доступа к Audiobookshelf с медиастримингом рекомендуемая схема:

```text
client
  -> HTTPS books.nikcode.xyz
  -> Cloudflare authoritative DNS, DNS-only A record
  -> существующий public ingress/Caddy на london:443
  -> Tailscale direct path
  -> moscow:13378 / Audiobookshelf
```

Она сохраняет домен в Cloudflare DNS, не открывает домашний `moscow` в публичный
интернет и не пропускает аудиокниги через Cloudflare reverse proxy/CDN. Последнее
существенно: Cloudflare прямо пишет, что public-hostname routes Cloudflare Tunnel
на Free, Pro и Business подчиняются service-specific restrictions для video и
other large files. Audiobookshelf по определению регулярно передаёт большие
аудиофайлы, поэтому считать обычный Cloudflare Tunnel или orange-cloud proxy
безусловно допустимым production transport нельзя. [Cloudflare Tunnel FAQ:
large-file and streaming traffic](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/#large-file-and-streaming-traffic-through-tunnel)

Ubuntu 21.10 на `moscow` не получает обновления с 14 июля 2022 года. Это
существенный security risk, но не технический blocker: из-за отсутствия
физического доступа принят временный вариант через London ingress без домашних
port-forward. Риск остаётся до миграции на поддерживаемую LTS; удалённый
multi-release upgrade без console recovery выполнять не следует. [Ubuntu Release
Team: 21.10 EOL](https://lists.ubuntu.com/archives/ubuntu-announce/2022-July/000281.html)

## Что есть сейчас

### Репозиторий

- Audiobookshelf управляется отдельным Ubuntu/Docker bundle в
  [`hosts/moscow/ubuntu/audiobookshelf/`](../../../hosts/moscow/ubuntu/audiobookshelf/README.md),
  потому что весь `moscow` пока не является управляемым NixOS-хостом. Это решение
  закреплено в [ADR 0001](../../adr/0001-manage-moscow-audiobookshelf-from-repository.md).
- Production Compose публикует контейнер на host port `13378`; текущий
  документированный endpoint доступен через Tailscale. Конкретный адрес не
  хранится в публичном исследовании.
- На `london` уже работает public Caddy bundle для `vault.nikcode.xyz`; его DNS
  upsert намеренно создаёт `proxied: false`. Изменения существующих London
  `microsocks`, Tailscale Serve и proxy assets запрещены без отдельной явной
  задачи.

### Pre-deployment live-проверка 2026-08-26

| Проверка | Результат |
|---|---|
| Authoritative NS `nikcode.xyz` | `armfazh.ns.cloudflare.com`, `romina.ns.cloudflare.com` |
| `books.nikcode.xyz` | До deployment: `NXDOMAIN`; deployed state зафиксировано в operational handoff |
| `vault.nikcode.xyz` | прямой DNS-only A record; HTTP-ответ содержит `via: 1.1 Caddy`, но не Cloudflare edge headers |
| `moscow` | ARM64, Ubuntu 21.10, Tailscale 1.30.2 |
| Audiobookshelf | контейнер `2.36.0` запущен, bind `0.0.0.0:13378`; `/status` возвращает `serverVersion: 2.36.0`, только local auth |
| Сеть `moscow` | доступна через LAN и Tailscale; конкретные адреса намеренно не публикуются в исследовании |
| `london -> moscow` | `tailscale ping` подтвердил прямую peer-to-peer связность |
| Caddy container на `london` -> ABS | status endpoint успешно доступен через Tailscale |

Наличие egress IPv4 не доказывает, что провайдер даёт стабильный входящий IPv4:
для прямого home ingress ещё надо отдельно проверить CGNAT, port forwarding,
динамичность адреса и hairpin/split DNS.

Audiobookshelf сам не реализует remote-access transport и рекомендует VPN или
reverse proxy; сервер отдаёт HTTP без собственного TLS. Он также требует
WebSocket. [Audiobookshelf server FAQ](https://audiobookshelf.org/docs/faq/server/#why-do-i-need-to-set-up-my-own-remote-access),
[официальные reverse-proxy examples](https://github.com/advplyr/audiobookshelf#reverse-proxy-set-up)

## Сравнение вариантов

| Вариант | `books.nikcode.xyz` | Входящие порты дома | Moscow origin скрыт | ABS/WebSocket | Ограничения media | Оценка |
|---|---:|---:|---:|---:|---|---|
| **Cloudflare DNS-only -> London Caddy -> Tailscale -> Moscow** | Да | Нет | Да | Да | Нет Cloudflare media proxy | **Рекомендуется** |
| Cloudflare DNS-only -> домашний Caddy -> Moscow | Да | `443` (обычно также `80`) | Нет | Да | Нет Cloudflare media proxy | Рабочий fallback после OS upgrade и проверки public IP |
| Cloudflare Tunnel public hostname -> Moscow | Да | Нет | Да | Да | Cloudflare large-file terms; upload limit | Технически удобно, но не выбирать для постоянной audiobook delivery без подтверждения Cloudflare/подходящего paid product |
| Home Caddy + proxied/orange-cloud Cloudflare A/AAAA | Да | `443` | Частично; firewall должен принимать только Cloudflare | Да | Те же Cloudflare proxy/media ограничения | Не даёт преимуществ Tunnel для этой задачи и требует public origin |
| Tailscale Funnel -> Moscow | Нет, только `*.ts.net` | Нет | Да | HTTP/TCP proxy подходит | Нефиксированные bandwidth limits | Только временный/экспериментальный URL |
| Обычный Tailscale access | Не публичный endpoint | Нет | Да | Уже проверено | Нет публичного relay/CDN | Самый безопасный вариант, если публичность на самом деле не нужна |

### 1. DNS-only на `london` с Tailscale backhaul — основной вариант

Cloudflare остаётся authoritative DNS: DNS-only означает только, что HTTP media
traffic не проходит через Cloudflare edge. Cloudflare документирует authoritative
DNS и различие proxied/DNS-only records отдельно. [How Cloudflare DNS
works](https://developers.cloudflare.com/fundamentals/concepts/how-cloudflare-works/)

На `london` уже открыт `443`, Caddy обслуживает публичный hostname, а его текущий
container из live-проверки достигает `moscow:13378` через Tailscale. Caddy
поддерживает WebSocket upgrade и streaming без отдельного WebSocket location;
его automatic HTTPS выпускает и обновляет публичные сертификаты.
[Caddy `reverse_proxy`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)

Плюсы:

- не нужен port-forward на домашнем роутере и не важен CGNAT;
- публично виден только уже существующий VPS ingress;
- `moscow:13378` остаётся транспортно доступен только LAN/Tailscale;
- hostname полностью совместим с web, ABS API и нативными клиентами;
- нет Cloudflare upload/cacheable-object limits и large-file policy для HTTP
  traffic, поскольку Cloudflare обслуживает только DNS.

Минусы:

- playback зависит сразу от `london`, Tailscale и `moscow`;
- весь media egress проходит через VPS, поэтому надо проверить лимиты/стоимость
  трафика Oracle и фактическую скорость длительного playback/download;
- ABS увидит reverse proxy; корректный client IP и logging надо проверить на
  canary;
- это изменение существующего London Caddy bundle. Реализовывать его следует
  отдельной задачей, не меняя и не перезапуская `microsocks`, Tailscale Serve или
  связанный proxy setup.

### 2. Cloudflare Tunnel

С технической стороны Tunnel почти идеален: `cloudflared` создаёт outbound-only
connections к Cloudflare на TCP/UDP 7844, публичный hostname указывает CNAME на
`<UUID>.cfargotunnel.com`, public origin IP и входящие домашние порты не нужны.
Tunnel полностью поддерживает WebSocket. ARM64 binary и `.deb` официально
публикуются. [Tunnel overview](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/),
[Tunnel DNS records](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/),
[Tunnel WebSocket FAQ](https://developers.cloudflare.com/cloudflare-one/faq/cloudflare-tunnels-faq/#does-cloudflare-tunnel-support-websockets),
[`cloudflared` downloads](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/)

Для текущего Compose origin route был бы логически равен
`books.nikcode.xyz -> http://127.0.0.1:13378`; Access по умолчанию не обязателен,
и без него endpoint публичен до встроенного ABS login. Cloudflare это явно
описывает: после создания published application её может открыть любой, а Access
добавляется отдельно. [Create a Tunnel: publish an
application](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/#2a-publish-an-application)

Но для Audiobookshelf есть два blocker/trade-off:

1. Cloudflare Tunnel FAQ относит public hostname route к reverse proxy и для
   Free/Pro/Business требует специальный paid service для video и other large
   files. Cache bypass не отменяет это условие.
2. У Cloudflare proxy maximum upload size составляет 100 MB на Free/Pro, 200 MB
   на Business; cacheable object — 512 MB на Free/Pro/Business. ABS web/app upload
   книги большего размера не пройдёт одним request. Cloudflare также по умолчанию
   считает MP3/FLAC cacheable extensions, поэтому при сознательном выборе proxy
   следует задать cache bypass для всего hostname, а не кэшировать
   authenticated media. [Cloudflare cache/upload
   limits](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/#customization-options-and-limits)

Cloudflare proxy поддерживает byte-range responses при наличии `Content-Length`,
так что seeking само по себе не является blocker. [Cloudflare client-side range
requests](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/#client-side-range-requests)

#### Cloudflare Access и клиенты

Browser Access проверяет каждый request по `CF_Authorization` cookie. Для
non-browser client Cloudflare предлагает service token headers
`CF-Access-Client-Id` и `CF-Access-Client-Secret`. Одноheaderный режим через
`Authorization` здесь нельзя использовать: этот header уже нужен ABS для своего
Bearer token. [Access authorization
cookie](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/),
[Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)

Используемый в текущем operator flow клиент Absorb официально заявляет custom
HTTP headers и real-time sync через Socket.IO, поэтому service-token path
потенциально совместим. Но перед rollout надо проверить именно установленную
версию: login, socket reconnect, streaming, seek и offline download с обоими
CF headers. [Absorb upstream](https://github.com/pounat/absorb#features)

Service token — общий статический secret на устройстве, а не пользовательская
идентификация ABS. Его компрометация снимает только внешний Access layer; ABS
login всё ещё обязателен. Лучше отдельный token на устройство/пользователя и
готовая процедура revoke. `Bypass Everyone` не является эквивалентом защиты:
Cloudflare предупреждает, что Bypass отключает enforcement и Access logging.
[Cloudflare Access policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/#bypass)

Итог: Access улучшает authentication gate, но не устраняет media terms и upload
limits. Поэтому он не меняет основную рекомендацию.

### 3. Прямой домашний reverse proxy

Если домашний публичный IPv4 окажется действительно входящим и достаточно стабильным,
можно поставить Caddy перед ABS, пробросить `443` на Caddy и создать DNS-only A
record. Не следует пробрасывать наружу `13378`; после внедрения proxy лучше
ограничить ABS listener loopback/внутренней Docker network или firewall.

Для DNS-only Caddy получает публичный сертификат сам. Если использовать
orange-cloud proxy, нужен поддерживаемый Cloudflare origin port (`443`, но не
`13378`), TLS mode `Full (strict)` и валидный origin certificate. Origin firewall
следует ограничить актуальными Cloudflare IP ranges или использовать
Authenticated Origin Pulls; иначе найденный origin IP позволяет обойти WAF.
[Cloudflare supported proxy ports](https://developers.cloudflare.com/fundamentals/reference/network-ports/),
[Full strict](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/),
[protect the origin](https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/#configure-origin-server),
[Authenticated Origin Pulls](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/explanation/)

Orange-cloud снова пропускает media через Cloudflare и потому наследует тот же
terms/limits blocker, что Tunnel. DNS-only лишён этого blocker, но раскрывает
домашний IP, требует port-forward/dynamic DNS и оставляет DDoS/availability на
домашнем канале. На EOL Ubuntu этот вариант сейчас неприемлем.

### 4. Tailscale Funnel

Funnel публикует локальный HTTP/TCP service через Tailscale relay, скрывает IP
устройства и не требует входящего port-forward. Однако он:

- находится в beta;
- разрешает только hostname внутри tailnet domain `*.ts.net`, а не
  `books.nikcode.xyz`;
- работает только на `443`, `8443`, `10000`;
- имеет non-configurable bandwidth limits.

Это делает Funnel хорошим временным canary URL, но не постоянной реализацией
заданного hostname. CNAME `books.nikcode.xyz` не меняет TLS hostname, который
обслуживает Funnel, и не превращает custom domain в поддерживаемый сценарий.
Кроме того, Funnel требует Tailscale >= 1.38.3, а на `moscow` сейчас 1.30.2.
[Tailscale Funnel requirements and
limitations](https://tailscale.com/docs/features/tailscale-funnel/how-to/get-started/#requirements-and-limitations),
[How Funnel works](https://tailscale.com/docs/features/tailscale-funnel/)

## Статус implementation

1. **Deferred:** когда появится физический доступ, мигрировать `moscow` с Ubuntu 21.10 на
   поддерживаемую LTS, затем обновить Docker, Compose и Tailscale; провести
   backup/restore и ABS playback baseline. До этого использовать только
   ограниченный London-to-Tailscale ingress без домашнего port-forward.
2. **Done:** `13378` оставлен без router port-forward. По возможности сузить bind так,
   чтобы сервис принимал только localhost/LAN/Tailscale или соединения от
   выбранного reverse proxy.
3. **Done:** существующий reproducible London service bundle расширен отдельным
   `books.nikcode.xyz` site с Tailscale upstream. Не менять
   London proxy/VLESS/microsocks/Tailscale Serve.
4. **Done:** в Cloudflare DNS создан DNS-only A record `books.nikcode.xyz` с
   `proxied: false`, по аналогии с текущим `vault.nikcode.xyz`.
5. Оставить ABS authentication обязательной. Для повседневного клиента создать
   отдельного non-admin пользователя с минимальными library/tag/download
   permissions; admin/root использовать через Tailscale или только при
   необходимости. ABS поддерживает отдельные users, roles и library/tag access.
   [Audiobookshelf user management](https://audiobookshelf.org/docs/documentation/server-management/user-management/)
6. **Done:** отдельный London systemd timer проверяет публичный HTTPS,
   London-to-Moscow upstream и запас срока TLS. Проверка media path по-прежнему
   требует отдельного Range/playback canary, а не только HTTP 200.

Минимальная логика Caddy site выглядит так:

```caddyfile
books.nikcode.xyz {
  reverse_proxy <moscow-tailscale-endpoint>
}
```

Точная форма должна быть встроена в существующий London Docker/Caddy bundle и
проверена через `caddy validate`; это не предложение править live Caddy вручную.

## Validation plan

После реализации выполнить canary сначала отдельным обычным пользователем:

1. DNS: authoritative answer Cloudflare, A record равен London IP, record
   DNS-only; `books.nikcode.xyz` не содержит Cloudflare edge IP.
2. TLS: публично доверенная цепочка и hostname match. Клиенты используют прямой
   HTTPS на `443`; HTTP -> HTTPS redirect проверяется только если публичный TCP
   `80` включён. HSTS включается только после успешного client canary.
3. Origin isolation: домашний origin port недоступен с внешней сети; на Moscow
   доступен только ожидаемый LAN/Tailscale path.
4. Web: login/logout, каталог, covers, server settings только для разрешённой
   роли.
5. Absorb по LTE/5G: login, Socket.IO reconnect, старт playback, seek вперёд и
   назад, прогресс после kill/reopen, offline download целой большой книги.
6. HTTP semantics: `Range` request получает `206`, корректные `Accept-Ranges`,
   `Content-Range`, `Content-Length`; Caddy не буферизует файл целиком.
7. Long session: не менее часа playback с заблокированным экраном и сменой
   Wi-Fi/mobile network; прогресс синхронизируется после reconnect.
8. Failure drills: остановленный ABS даёт контролируемый `502`, отключённый
   Tailscale не переключает на публичный home origin, восстановление соединения
   не требует ручной правки DNS.
9. Regression: `vault.nikcode.xyz`, London `microsocks` и Tailscale Serve после
   Caddy reload работают без изменений.

## Operational follow-ups

- Тариф Cloudflare: enterprise contract может менять допустимый media scenario;
  на Free/Pro/Business официальный Tunnel FAQ уже даёт отрицательный сигнал.
- Oracle London egress quota/cost и реальная скорость до основных клиентов.
- Поддерживает ли домашний ISP inbound IPv4 и насколько он стабилен; это нужно
  только для direct-home fallback. Конкретный адрес не хранится в публичном
  исследовании.
- Версия Absorb на реальных Android/iOS устройствах и поведение custom headers
  на Socket.IO/download path, если всё же тестировать Access.
- Требуемая аудитория: если доступ нужен только владельцу/семье с Tailscale,
  текущий private endpoint безопаснее и проще любого публичного hostname.
