# Доступ с macOS через VLESS к zenbook и m1max: варианты

**Дата:** 2026-09-25
**Статус:** историческое исследование вариантов; выбранный CLI Tailscale вариант реализован на m3max (итог ниже).

## Что уже есть

На `m3max` SSH-алиасы в [Home Manager](../../../hosts/m3max/home-manager/home.nix) задают путь к `m1max`: `m3max → frankfurt → um790pro` по WireGuard overlay `198.18.77.6` `→ m1max` по LAN `192.168.1.174`. Алиас `zenbook-frankfurt` идёт через те же два jump host к Tailscale-адресу `zenbook` `100.114.155.30`. Путь и роль WireGuard описаны в [proxy-setup.md](../../proxy-setup.md). На остальных исходных Mac такие алиасы ещё нужно подтвердить. Сам VLESS на Mac работает через sing-box GUI Network Extension; в репозитории зафиксирован конфликт с Tailscale.app и неудачный canary WireGuard outbound в этой версии GUI. [Текущая схема](../../proxy-setup.md)

Vault Dashboard — это **Indexary**, который читает `~/vault`. Проверка действующего `indexary.service` на `zenbook` 2026-09-25 показала listener `127.0.0.1:4176`; открытый в [конфигурации zenbook](../../../hosts/zenbook/nixos/configuration.nix) порт `4096` к этому сервису не относится. С `m3max` SSH alias `zenbook-frankfurt` подключился, а с него alias `m1max` подключился и проверка TCP `127.0.0.1:5900` на `m1max` прошла. Это проверка из текущей сети, не внешнесетевой canary с включённым VLESS.

Фраза «macOS не умеет больше одного активного VPN» здесь описывает наблюдавшийся конфликт двух **Network Extension VPN-приложений**, а не запрет на всякую дополнительную сетевую программу. Tailscale прямо называет userspace networking обходом конфликтов с другими VPN. В этом режиме локальный SOCKS5/HTTP proxy не создаёт обычный VPN-интерфейс. Совместимость с конкретной sing-box GUI конфигурацией всё равно требует пробы. [Tailscale: other VPNs](https://tailscale.com/docs/reference/faq/other-vpns), [userspace networking](https://tailscale.com/docs/concepts/userspace-networking), [macOS variants](https://tailscale.com/docs/concepts/macos-variants)

## Ограничение Screen Sharing

Apple Screen Sharing допускает **Standard** и **High Performance**. Стандартное подключение начинается на TCP `5900`; в приложении можно задать иной TCP-порт сервера. Для High Performance Apple требует, чтобы оба Mac обменивались пакетами по UDP `5900`, `5901` и `5902`, а также рекомендует 75 Мбит/с для одного 4K-дисплея. Значит, локальный SSH `-L`, SOCKS5 proxy и Cloudflare `access tcp` дают только путь для **Standard**; работоспособность конкретного клиента через туннель надо проверить. Если нужен именно High Performance, нужен способ доставить и UDP, и TCP, либо другой протокол удалённого рабочего стола. [Apple: настройки подключения](https://support.apple.com/en-ke/guide/mac-help/mchl67d5398b/mac), [Apple: режимы и UDP](https://support.apple.com/en-tm/guide/mac-help/mchl1883115d/mac), [Apple: порты Remote Desktop](https://support.apple.com/zh-hans/guide/remote-desktop/apd0c903fec/mac)

## Вариант A — расширить существующий SSH jump локальными TCP-портами

OpenSSH `ProxyJump` строит TCP-путь к конечному SSH-серверу через jump host; `-L` открывает локальный порт и передаёт его к `host:port` **с конечного SSH-сервера**. Это применимо к HTTP и стандартному Screen Sharing, хотя пользовательские приложения не говорят по SSH. `-N` запускает только forward без shell. [OpenSSH ssh(1)](https://man.openbsd.org/ssh)

Пример **для обсуждения, не команда к применению**, если финальные алиасы доступны на исходном Mac:

```text
Mac browser → 127.0.0.1:14176 → SSH zenbook-frankfurt → zenbook:127.0.0.1:4176
Mac Screen Sharing Standard → 127.0.0.1:15900 → SSH m1max → m1max:127.0.0.1:5900
```

Для `m3max` это использует уже описанные в репозитории jump-пути. Сильные стороны: без новой публичной службы, стороннего аккаунта или отдельного VPN; доступ к конечному SSH-серверу по существующим ключам; локальные слушатели можно ограничить `127.0.0.1`. Ограничения: TCP-only, каждый сервис требует локального порта или отдельного SOCKS-пути; доступ пропадает при отказе любого из текущих промежуточных узлов. `ServerAliveInterval` помогает вовремя выявлять разрыв, но автоматическое восстановление процесса нужно проектировать отдельно. `ExitOnForwardFailure` проверяет создание listener, **не** доступность конечного dashboard/VNC сервиса. [OpenSSH ssh(1)](https://man.openbsd.org/ssh), [ssh_config(5)](https://man.openbsd.org/ssh_config)

Проверить до выбора: живой `ssh zenbook-frankfurt` и `ssh m1max` с каждого исходного Mac через активный VLESS; разрешено ли локальное TCP forwarding на конечных sshd (`AllowTcpForwarding`, `PermitOpen`, `DisableForwarding`). Listener Indexary и доступный TCP `5900` на `m1max` подтверждены с текущего `m3max`, но сам экранный сеанс и внешний сетевой путь ещё не проверены. [Apple: включение Screen Sharing](https://support.apple.com/en-md/guide/mac-help/mh11848/mac), [OpenSSH sshd_config(5)](https://man.openbsd.org/sshd_config)

## Вариант B — Tailscale userspace proxy на исходном Mac

Отдельный `tailscaled --tun=userspace-networking` может открыть локальный SOCKS5 и HTTP proxy без Tailscale VPN-интерфейса. Приложения, умеющие proxy, обращаются к tailnet через него. Однако Indexary сейчас слушает **только loopback** `127.0.0.1:4176`, поэтому один userspace proxy не откроет его по Tailscale-адресу `zenbook`: потребуется `tailscale serve` для публикации этого локального HTTP-сервиса внутри tailnet либо изменение bind адреса и firewall. Для Screen Sharing прямой настройки SOCKS5 в документации Apple не найдено: потребуется локальный TCP forwarder или SSH поверх Tailscale proxy. Обычный `ping` tailnet-узлов в userspace mode не работает. [Tailscale: userspace networking](https://tailscale.com/docs/concepts/userspace-networking), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), [other VPNs](https://tailscale.com/docs/reference/faq/other-vpns), [Apple: настройки Screen Sharing](https://support.apple.com/en-ke/guide/mac-help/mchl67d5398b/mac)

На macOS нужен именно open-source `tailscaled`, а не CLI, встроенный в Tailscale.app: GUI-варианты совмещают GUI/daemon/CLI, и Tailscale описывает отдельный open-source daemon как вариант для опытных администраторов. CLI поддерживает отдельный `--socket` для daemon. Для `m1max`, который сейчас не является tailnet-узлом, userspace proxy на исходном Mac сам по себе недостаточен: нужен путь до него через `um790pro` как subnet router или другой TCP-relay. В отличие от [исследования от августа](./2026-08-19-um790pro-tailscale-subnet-router-research.md), **текущая конфигурация уже рекламирует** `192.168.1.174/32` и `192.168.1.144/32` на `um790pro`, в том числе в `install.sh`; фактическое одобрение маршрутов в tailnet и работоспособность с удалённого Mac нужно проверить. [Конфигурация um790pro](../../../hosts/um790pro/nixos/configuration.nix), [Tailscale: macOS variants](https://tailscale.com/docs/concepts/macos-variants), [tailscaled flags](https://tailscale.com/docs/reference/tailscaled), [subnet routers](https://tailscale.com/docs/features/subnet-routers)

Плюс этого варианта — прямой tailnet-доступ для приложений с поддержкой proxy и потенциально меньше SSH-hop для zenbook. Цена — второй Tailscale node/state и lifecycle на каждом исходном Mac, интеграция приложений с proxy, отдельно решаемый m1max. Не следует считать совместимость со включённым sing-box GUI доказанной без canary на нужной версии/macOS и внешней сети. [Tailscale: other VPNs](https://tailscale.com/docs/reference/faq/other-vpns), [userspace networking](https://tailscale.com/docs/concepts/userspace-networking)

## Вариант C — Cloudflare Tunnel + Access

`cloudflared` на каждом целевом хосте устанавливает исходящее соединение с Cloudflare, так что входящий порт/публичный IP цели не нужен. HTTP dashboard можно публиковать по HTTPS и закрыть Access-политикой. Для произвольного TCP, включая стандартный VNC, Cloudflare требует `cloudflared` **и на клиентском Mac**: `cloudflared access tcp` даёт локальный порт, к которому подключается Screen Sharing. Нужны Cloudflare account, домен в Cloudflare и политика Access до публикации. [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/), [arbitrary TCP](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/non-http/cloudflared-authentication/arbitrary-tcp/), [routing](https://developers.cloudflare.com/tunnel/concepts/routing/)

Это снимает зависимость от существующей цепочки Frankfurt/WireGuard/um790pro, но добавляет Cloudflare, управление доменом/политиками и daemon на целях и клиентах. Cloudflare TCP route передаёт поток через WebSocket и прямо рекомендует другой режим **Client-to-Tunnel** для долгих соединений. Cloudflare указывает, что длительные соединения могут прерываться при обслуживании сети; для Screen Sharing это существенный риск. High Performance из-за UDP не покрывается. [Cloudflare: routing](https://developers.cloudflare.com/tunnel/concepts/routing/), [disconnects](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/troubleshoot-tunnels/common-errors/), [Apple: High Performance](https://support.apple.com/en-tm/guide/mac-help/mchl1883115d/mac)

## Вариант D — обратный SSH forward от целей к Frankfurt

`ssh -R` может открыть **только loopback**-порт на Frankfurt и передавать его к dashboard/VNC на целевом хосте. Исходный Mac подключается к Frankfurt и забирает сервис локальным `ssh -L`. Это использует уже доступный публичный сервер и не зависит от `um790pro`, но требует постоянной исходящей SSH-сессии **с каждого целевого хоста**, управления портами, автоперезапуска и мониторинга. Loopback bind на Frankfurt обязателен, если сервис не предполагается публиковать напрямую; `GatewayPorts` управляет возможностью нелокального bind. Как и вариант A, этот путь TCP-only и подходит для Standard Screen Sharing. [OpenSSH ssh(1): -R/-L](https://man.openbsd.org/ssh), [sshd_config(5): GatewayPorts](https://man.openbsd.org/sshd_config), [Apple: режимы](https://support.apple.com/en-tm/guide/mac-help/mchl1883115d/mac)

## Вариант E — отдельная router VM на исходном Mac

В репозитории уже есть [эскиз Lima/NixOS router VM](./2026-06-02-macos-lima-router-vm-design.md): VLESS и Tailscale работают внутри VM, а macOS отправляет нужные маршруты через неё. В принципе такой сетевой путь может переносить и TCP, и UDP для Screen Sharing High Performance, если настроены маршруты в обе стороны до `m1max` через `um790pro` и измеренные скорость/задержка подходят. Это **проект, а не подтверждённая работающая схема**: требует управления default route, DNS, жизненным циклом VM и надёжного отката при сбое. Для двух TCP-сервисов сложность несоразмерна, но при требовании High Performance это кандидат для отдельного canary. [Существующий дизайн](./2026-06-02-macos-lima-router-vm-design.md), [Apple: режимы и UDP](https://support.apple.com/en-tm/guide/mac-help/mchl1883115d/mac)

## Сравнение для выбора

| Подход | zenbook HTTP | m1max Screen Sharing | Новые постоянно работающие компоненты | Основная зависимость |
|---|---|---|---|---|
| A. SSH `-L` через текущий jump | да, TCP | Standard, TCP | нет на целях; постоянный локальный SSH-сеанс на клиенте | Frankfurt + um790pro + конечный SSH |
| B. Tailscale userspace на клиенте | после `tailscale serve` или изменения bind | Standard через отдельный TCP forward; нужен маршрут к m1max | `tailscaled` на каждом исходном Mac; публикация Indexary внутри tailnet | Tailscale; subnet router/relay для m1max |
| C. Cloudflare Tunnel/Access | браузер через Access | Standard через клиентский `cloudflared access tcp` | `cloudflared` на целях и клиентах | Cloudflare account/domain/edge |
| D. Обратный SSH через Frankfurt | да, TCP | Standard, TCP | постоянный SSH-сеанс на обеих целях | Frankfurt и исходящие SSH-сеансы целей |
| E. Router VM | маршрутизация IP | потенциально High Performance, после проверки UDP | VM на каждом исходном Mac | VM, Tailscale и маршрутизация |

**Рекомендация для обсуждения с учётом уточнений пользователя:** исходный Mac сейчас только `m3max`, нужен Screen Sharing Standard и постоянный доступ по общим именам сервисов. Вариант A можно дополнить `launchd` jobs на `m3max` для автоматического восстановления двух SSH forward и локальными именами, направленными на эти forward. Для HTTP без указания порта потребуется локальный reverse proxy; для VNC стандартный локальный TCP `5900` на `m3max` уже занят, поэтому нужен другой порт в сохранённом адресе Screen Sharing либо более сложный локальный сетевой посредник. Такие имена будут работать после настройки каждого исходного Mac, а не автоматически на любом новом устройстве. Это эскиз, а не настроенный сервис; внешний сетевой canary, переподключение и поведение во время сна ещё не проверены.

Отдельная проверка с Frankfurt 2026-09-25: TCP `22` на WireGuard адресе `zenbook` `198.18.77.3` дал timeout. По подсказке пользователя также проверен **именно Tailscale путь**: на Frankfurt `tailscale status --json --peers=false` вернул `BackendState=NeedsLogin`, а TCP `22` на Tailscale адресе `zenbook` `100.114.155.30` дал timeout. Значит, прямой Tailscale маршрут `Frankfurt → zenbook` сейчас не работает; он может стать вариантом сокращения SSH цепочки после отдельного подключения Frankfurt к tailnet и проверки policy. Текущий алиас `zenbook-frankfurt` обходит этот пробел через `um790pro`, у которого Tailscale активен. Если нужны настоящие общие DNS-имена без клиентских локальных посредников, сравнить C и E; для m1max Cloudflare TCP всё равно требует клиентский `cloudflared`, а E требует гораздо более серьёзного изменения маршрутизации. Это оценка по найденным источникам и текущей конфигурации, не результат испытаний.

При любом варианте доступность конечных устройств остаётся отдельным условием. Для `zenbook` уже [задокументировано](../../zenbook-headless-power.md), что после полного выключения от разряда он может потребовать физического включения и LUKS unlock; сетевой туннель это не исправит. Для `m1max` нужно проверить поведение сна и Wake for network access. [Apple: Wake for network access](https://support.apple.com/guide/mac-help/mchle41a6ccd/mac)

## Вопросы, влияющие на выбор

1. Означает ли требование общих имён, что они должны разрешаться без установки локального DNS/forward на каждом будущем Mac? Пока источник только `m3max`, но это изменит выбор архитектуры на будущее.
2. Какая схема аутентификации включена у Indexary на `zenbook`? Сам TCP listener `127.0.0.1:4176` известен.
3. Приемлема ли зависимость от Cloudflare для Indexary и удалённого рабочего стола?

## Дополнение: одно имя дома и вне дома для всех четырёх клиентов

Пользователь уточнил 2026-09-25: источник сейчас только `m3max`; `zenbook` и `m1max` всегда дома; на `m3max` VLESS должен оставаться активным; вне дома допустимо всегда подключать `m3max` через отдельный дорожный роутер. Одни и те же имена нужны для `https://indexary.something`, Screen Sharing `m1max.something`, Codex Desktop Remote и `herdr --remote` к `zenbook.something`/`m1max.something`.

Для этих требований локальные SSH `-L` дают слишком много различий между приложениями. Более цельная **кандидатная схема** — оставить sing-box GUI/VLESS на `m3max`, а Tailscale запустить на дорожном роутере. В домашней сети Mac обращается к фиксированным LAN IP целей напрямую. Вне дома Mac подключён к роутеру с собственной LAN подсетью, отличной от `192.168.1.0/24`; тот принимает два узких маршрута `/32` от `um790pro` и отправляет их через Tailscale. На `um790pro` маршрут к `m1max` `192.168.1.174/32` уже рекламируется, но к текущему LAN IP `zenbook` `192.168.1.249/32` — ещё нет. `192.168.1.249` получен при живой проверке `ip route get` на zenbook, но DHCP reservation не подтверждена. При включённом default SNAT на `um790pro` цели отвечают ему по домашней LAN. [Конфигурация um790pro](../../../hosts/um790pro/nixos/configuration.nix), [Tailscale subnet routers](https://tailscale.com/docs/features/subnet-routers), [Tailscale SNAT](https://tailscale.com/docs/features/subnet-routers#disable-snat)

```text
дома:    m3max + sing-box/VLESS → домашняя LAN → zenbook .249 / m1max .174
вне дома: m3max + sing-box/VLESS → дорожный router → Tailscale
                                                → um790pro → домашняя LAN → те же IP
```

Это возможно без второго VPN на Mac, потому что текущий `m3max-gui.json` уже исключает `192.168.0.0/16` из sing-box TUN; после разрешения имени в домашний IP пакет идёт через обычную сеть. Официальная документация sing-box определяет `route_exclude_address` именно как исключение из маршрутов TUN. На внешнем роутере должны быть `accept-routes`, разрешённый LAN→Tailscale forwarding и защищённая Wi-Fi сеть: tailnet будет видеть identity роутера, а не самого Mac. [sing-box TUN](https://sing-box.sagernet.org/configuration/inbound/tun/), [Tailscale client routes](https://tailscale.com/docs/features/client/manage-preferences#use-tailscale-subnets)

Имена `zenbook.something` и `indexary.something` должны возвращать один и тот же зарезервированный домашний IP zenbook; `m1max.something` — зарезервированный домашний IP m1max. Для одного m3max это можно сделать локальными host entries либо управляемым DNS, но фактическую резолюцию во всех четырёх приложениях надо проверить. Текущий sing-box GUI перехватывает DNS, имеет пустой `dns.rules` и отправляет запросы по умолчанию удалённому DNS через VLESS; DHCP DNS дорожного роутера сам по себе не станет источником этих имён. Для отдельного домена понадобятся правила split DNS или иной управляемый механизм. [sing-box DNS](https://sing-box.sagernet.org/configuration/dns/), [DNS rules](https://sing-box.sagernet.org/configuration/dns/rule/)

Indexary сейчас слушает только `127.0.0.1:4176`, поэтому `https://indexary.something` требует HTTPS reverse proxy на zenbook, доступного по его домашнему IP, с аутентификацией и сертификатом. Сертификат для собственного домена можно выпускать через ACME DNS-01 без публичного входящего порта. [Let's Encrypt DNS-01](https://letsencrypt.org/docs/challenge-types/)

Если дорожный роутер потеряет Tailscale route, совпадающий IP в чужой сети может получить пакет. Маршруты к домашним `/32` должны **fail closed** на дорожном роутере; его LAN нельзя делать `192.168.1.0/24`, чтобы Mac не считал домашние адреса локальными и не ARP-ил их. Нужна проверка не только доступности, но и отказа Tailscale. Дома путь прямой и не зависит от дорожного роутера.

### Устройство из объявления

Авито-страница по переданной ссылке не открылась для автоматического чтения, поэтому цена, ревизия платы и комплектный модем конкретного лота не подтверждены. [Производитель WH3000 Pro](https://www.huasifei.com/product/wh3000-pro/) описывает модель с Wi-Fi 6, 1 ГБ RAM, WAN 1 Гбит/с, LAN 2,5 Гбит/с и USB-C 5 В/3 А, но на странице указаны eMMC и другой модем. [OpenWrt source](https://git.openwrt.org/openwrt/openwrt/tree/target/linux/mediatek/image/filogic.mk) содержит разные образы для WH3000 Pro с NAND и eMMC; тип памяти надо подтвердить до прошивки. Сотовый FM350-GL не обязателен для рассматриваемой схемы, если интернет на дорожный роутер поступает по Ethernet или Wi-Fi; если нужен сотовый резерв, работу этого конкретного модема в данном устройстве нужно отдельно подтвердить.

### Вариант без покупки

Tailscale [документирует](https://tailscale.com/docs/concepts/macos-variants) macOS open-source `tailscaled`, который использует `utun`, а не Network Extension. [Tailscale предупреждает](https://tailscale.com/docs/reference/faq/other-vpns), что совместная работа VPN может упираться в конфликт маршрутов. Userspace SOCKS5 режим избегает конфликта интерфейсов, но не даёт Screen Sharing и Codex обычной системной маршрутизации без дополнительных посредников.

**Canary 2026-09-25 на m3max.** Временный `tailscaled` 1.102.1 из Nix store был запущен от root с отдельным состоянием и сокетом; sing-box GUI/VLESS оставался подключённым. Узел `m3max-vless-canary` вошёл в tailnet, `tailscale ping zenbook` работал. Но обычный TCP к `100.114.155.30:22` сначала не проходил: действующее исключение sing-box `100.64.0.0/10` направляло этот адрес через физический шлюз, а CLI не установил более точный маршрут к peer. Временный host route `100.114.155.30/32 → utun10` исправил TCP SSH. После включения `accept-routes` CLI установил `192.168.1.174/32 → utun10` от `um790pro`; TCP SSH и Screen Sharing `5900` к m1max стали доступны. Успех TCP `5900` подтверждает сетевой путь, но полноценный сеанс Screen Sharing не запускался.

После переключения m3max с домашнего Wi-Fi на LTE с работающим VLESS оба CLI peer ping и TCP к `zenbook:22`, `m1max:22`, `m1max:5900` продолжили работать. Проверка HTTP через Indexary не могла пройти: сервис слушает только `127.0.0.1:4176`. Проверка приложений по постоянным именам также ждёт DNS и HTTPS настройку. Временный маршрут, CLI демон и его локальное состояние после теста удалены; VLESS остался подключённым. Авторизованный временный узел может ещё отображаться в админ-панели tailnet как offline.

**Вывод для выбора.** Схема технически возможна без покупки роутера, но надёжный вариант требует постоянного запуска CLI демона и восстановления маршрутов после старта и изменений сети. Из-за конфликта маршрутов нельзя просто установить `tailscaled` и считать задачу решённой. Собственный CLI Tailscale на `m1max` может дать прямой tailnet IP для Screen Sharing и SSH вместо подсетевого маршрута через `um790pro`; совместимость с его VLESS и маршруты на m1max отдельно не проверялись.

## Итог реализации 2026-09-25

Постоянный узел `m3max-vless-cli` авторизован в tailnet. На m3max запущен CLI-only `tailscaled --tun=utun` через launchd, отдельный watcher восстанавливает маршрут `100.114.155.30/32` к zenbook через его `utun`. DNS для `tailf108.ts.net` направляется в Tailscale MagicDNS через `/etc/resolver`, остальные DNS-настройки sing-box не менялись. `m1max.nikcode.xyz` на m3max локально сопоставлен с `192.168.1.174`; этот адрес доступен через `/32` маршрут, который объявляет `um790pro`. Конфигурация хранится в `hosts/m3max/nixos/tailscale-cli.nix` и SSH-конфигурации Home Manager. На m1max ничего не меняли, перезагрузка не потребовалась.

Проверка m3max через LTE при включённом VLESS: `https://zenbook.tailf108.ts.net` отвечает HTTP 200 и показывает Indexary; `ssh zenbook` и `ssh m1max` работают; Standard Screen Sharing по `m1max.nikcode.xyz` показал экран m1max. Сохранённое подключение Codex Desktop к zenbook использует `192.168.1.249`; SSH-конфигурация m3max направляет его через tailnet-имя zenbook, и SSH с этим буквальным адресом прошёл. Codex Desktop после переподключения в UI отдельно не проверялся. `herdr --remote m1max` открыл интерфейс; `herdr --remote zenbook` дошёл до сервера, но локальный Herdr 0.9.1 предложил заменить удалённый сервер 0.8.2 с предупреждением об остановке активных процессов. Замена не выполнялась.

Развёртывание launchd и системных файлов выполнено напрямую из успешно собранного nix-darwin closure, без полного `darwin-rebuild switch`, поскольку обычная активация также запускает несвязанные обновления Homebrew. Локальный GC root `/Users/nik/.local/state/nix/gcroots/m3max-tailnet-system` защищает closure до следующего штатного switch, который должен принять декларативную конфигурацию. После перезагрузки m3max автоматический старт ещё не проверялся.
