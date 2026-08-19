# `um790pro` как Tailscale subnet router для `m1max` и `m3max`

**Дата проверки:** 2026-08-19
**Статус:** brainstorming / feasibility study; конфигурация не изменялась

## Краткий вывод

Схема технически штатная: `um790pro` может быть Linux subnet router, рекламировать LAN-адреса Mac в tailnet и пересылать к ним трафик от `zenbook`. Tailscale прямо предназначает subnet routers для устройств, на которых клиент не установлен. Для этой задачи нужен **subnet router**, не exit node: первый публикует конкретные частные маршруты, второй уводит через себя интернет-трафик клиента. [Tailscale: Subnet routers](https://tailscale.com/docs/features/subnet-routers)

Для текущей узкой цели — только `ssh` — в репозитории уже есть более простая и безопасная схема: сгенерированный SSH config на `zenbook` содержит `m1max` с `HostName 192.168.1.174` и `ProxyJump um790pro`, а `um790pro` имеет Tailscale IP `100.95.213.117`. Получается:

```text
zenbook --Tailscale/SSH--> um790pro --LAN/SSH forwarding--> m1max:22
```

OpenSSH определяет `ProxyJump` именно как SSH-соединение к jump host с последующим TCP forwarding к конечному хосту. [OpenSSH `ssh_config(5)`](https://man.openbsd.org/ssh_config#ProxyJump)

Поэтому практический выбор такой:

1. Если нужны только SSH-сессии — оставить `ProxyJump`, проверить существующий `ssh m1max` и добавить аналогичный fixed LAN IP/SSH alias для `m3max`.
2. Если нужен прямой доступ с `zenbook` к LAN IP, несколько портов или другие сервисы — включать subnet router на `um790pro`.

## Живая проверка текущего пути

Read-only диагностика 2026-08-19 показала:

- активная ОС `um790pro` сейчас CachyOS, а не NixOS: `wlan0 = 192.168.1.241/24`,
  Tailscale IP `100.95.213.117`;
- `m1max.local = 192.168.1.174`, `m3max.local = 192.168.1.144`;
- TCP/22 открыт на обоих Mac, а SSH через `um790pro` успешно вернул hostname
  `m1max` и `m3max`;
- на `um790pro` IPv4 forwarding уже включён и SNAT не отключён, но subnet routes
  пока не рекламируются;
- на `zenbook` принятие subnet routes выключено (`RouteAll = false`);
- у `um790pro` CLI Tailscale `1.102.2`, а daemon `1.98.10`. Для feasibility это не
  препятствие, но перед pilot версии лучше выровнять.

Проверка выполнялась из домашней сети, не через LTE. Она отдельно подтвердила
Tailscale-доступ до `um790pro` и LAN-доступ от него до обоих Mac; завершающий canary
всё равно нужно провести с `zenbook` через LTE.

## Что уже есть в репозитории

Проверка вычисленной Nix-конфигурации дала:

| Узел | Текущее состояние |
|---|---|
| NixOS-конфигурация `um790pro` | Tailscale включён, пакет `1.102.1`; `useRoutingFeatures = "none"`; рекламируемых subnet routes нет; UDP `41641` локальным firewall специально не открыт |
| `zenbook` | Tailscale включён, пакет `1.102.1`; `--accept-routes` не задан, а Linux по умолчанию subnet routes не принимает |
| оба NixOS-узла | из-за VLESS задано `--accept-dns=false`, поэтому tailnet DNS и split DNS сейчас не будут применяться |
| SSH на `zenbook` | `m1max -> 192.168.1.174`, `ProxyJump = um790pro`; `um790pro -> 100.95.213.117` |

NixOS-модуль из закреплённого nixpkgs предлагает для router-side `services.tailscale.useRoutingFeatures = "server"`, что включает IPv4/IPv6 forwarding. `extraSetFlags` декларативно запускаются через `tailscale set`; `openFirewall` открывает настроенный UDP-порт для более вероятного прямого Tailscale-соединения. [NixOS `tailscale.nix` на закреплённом commit](https://github.com/NixOS/nixpkgs/blob/9bc02893134c733dd85de46ee4fb2fac696b5529/nixos/modules/services/networking/tailscale.nix)

В живой CachyOS-системе IPv4 forwarding уже включён; NixOS-конфигурация отдельно
отключает strict reverse-path filtering общим модулем. Правильная будущая декларация
NixOS-роли — всё равно `useRoutingFeatures = "server"`. Поскольку primary OS сейчас
CachyOS, воспроизводимую настройку нужно синхронно добавить и в `install.sh`, как
требуют правила репозитория.

## Как будет идти пакет через subnet router

Предпочтительный pilot — рекламировать не весь домашний `/24`, а только два стабильных host route:

```text
192.168.1.174/32,192.168.1.144/32
```

Для `m1max` текущий адрес — `192.168.1.174`, для `m3max` — `192.168.1.144`.
В репозитории зафиксирован только первый; обоим нужны DHCP reservations, иначе
переиспользованный адрес может привести к соединению уже с другим LAN-устройством.

Путь пакета при стандартном SNAT:

```text
zenbook (Tailscale 100.x)
  -> зашифрованный tunnel до um790pro
  -> Tailscale policy/filter на um790pro
  -> forwarding + SNAT в LAN-адрес um790pro
  -> m1max/m3max:22
  -> обычный ответ Mac к um790pro в той же LAN
  -> обратная трансляция и tunnel к zenbook
```

Tailscale включает SNAT на subnet routers по умолчанию. Именно поэтому на Mac **не нужен** ни Tailscale, ни static return route: Mac видит источником LAN IP `um790pro` и отвечает ему напрямую. Если задать `--snat-subnet-routes=false`, Mac увидит Tailscale source IP и без обратного маршрута `100.64.0.0/10 via <LAN-IP-um790pro>` отправит ответ обычному default gateway. Официальная документация прямо требует такой return route при отключённом SNAT. Для этого сценария SNAT отключать не следует. [Tailscale: SNAT и return route](https://tailscale.com/docs/features/subnet-routers?tab=linux#disable-snat)

Следствие SNAT: в macOS SSH logs все такие подключения будут выглядеть как пришедшие с LAN IP `um790pro`, а не с IP `zenbook`. Разграничение tailnet-источников выполняет Tailscale policy на router; сам Mac продолжает полагаться на обычные SSH keys/users.

## Минимальная форма будущей NixOS-конфигурации

Это эскиз, не применённое изменение:

```nix
# um790pro
services.tailscale = {
  useRoutingFeatures = "server";
  openFirewall = true; # необязательно для корректности; помогает direct вместо DERP
  extraSetFlags = [
    "--advertise-routes=192.168.1.174/32,192.168.1.144/32"
  ];
};

# zenbook
services.tailscale.extraSetFlags = [
  "--accept-routes=true"
];
```

Официальная Linux-процедура состоит из IP forwarding и `tailscale set --advertise-routes=...`; затем route нужно одобрить. Linux-клиенты, в отличие от macOS/Windows, требуют `--accept-routes=true`. [Tailscale setup](https://tailscale.com/docs/features/subnet-routers/how-to/setup), [client preferences](https://tailscale.com/docs/features/client/manage-preferences#use-tailscale-subnets)

`openFirewall = true` не является обязательным условием: Tailscale обычно работает без входящих firewall openings и при невозможности direct connection использует end-to-end encrypted DERP relay. Открытый UDP `41641` лишь повышает вероятность direct path и снижает задержку. [Tailscale firewall ports](https://tailscale.com/docs/reference/faq/firewall-ports)

## Route approval и доступ

Реклама route, её approval и разрешение трафика — три разные вещи:

1. `um790pro` рекламирует `/32` через `--advertise-routes`.
2. Admin вручную включает routes в Machines, либо policy `autoApprovers` одобряет их автоматически.
3. Grant разрешает нужному источнику TCP/22 к двум LAN IP.
4. Linux-клиент `zenbook` принимает subnet routes.

Tailscale подчёркивает, что route injection и access controls независимы; для работающего соединения нужны оба. Routes не проверяются ping-ом перед установкой. [Tailscale: Route injection](https://tailscale.com/docs/reference/route-injection)

Для одного стабильного pilot ручная approval проще `autoApprovers`. Если позднее понадобится декларативная замена router, форма policy может быть такой:

```jsonc
{
  "tagOwners": {
    "tag:home-subnet-router": ["autogroup:admin"]
  },
  "autoApprovers": {
    "routes": {
      "192.168.1.174/32": ["tag:home-subnet-router"],
      "192.168.1.144/32": ["tag:home-subnet-router"]
    }
  }
}
```

`autoApprovers` только одобряет route advertisement; доступ он не выдаёт. Для нового policy Tailscale рекомендует Grants, а не legacy ACLs. Например:

```jsonc
{
  "hosts": {
    "m1max-lan": "192.168.1.174",
    "m3max-lan": "192.168.1.144"
  },
  "grants": [
    {
      "src": ["<ZENBOOK_SELECTOR>"],
      "dst": ["m1max-lan", "m3max-lan"],
      "ip": ["tcp:22"]
    }
  ]
}
```

`<ZENBOOK_SELECTOR>` стоит выбрать после просмотра текущей policy: конкретный Tailscale IP/host alias ограничит правило одним узлом, user/group — всеми устройствами пользователя/группы, tag — всеми узлами с этим tag. Grants складываются как union, поэтому узкий grant не отменит уже существующий широкий allow. [Tailscale Grants syntax](https://tailscale.com/docs/reference/syntax/grants), [route auto-approvers](https://tailscale.com/docs/reference/syntax/policy-file#auto-approvers)

## Имена и `ssh m1max`

MagicDNS автоматически создаёт имена только для устройств, вошедших в tailnet; произвольные записи в MagicDNS добавить нельзя. Поэтому LAN-only Macs не получат обычные MagicDNS-имена `m1max`/`m3max`. Варианты:

- оставить SSH aliases с `HostName` равным reserved LAN IP — это уже сделано для `m1max`;
- использовать обычный внутренний DNS и настроить его как split DNS в tailnet;
- использовать Tailscale 4via6 для пересекающихся IPv4-сетей, где появляются специальные имена вида `192-168-1-174-via-N`.

Split DNS сейчас конфликтует с репозиторием: `zenbook` явно использует `--accept-dns=false`, тогда как tailnet DNS применяется только при `--accept-dns=true`. Для SSH aliases менять DNS policy не требуется. [Tailscale DNS](https://tailscale.com/docs/reference/dns-in-tailscale), [MagicDNS](https://tailscale.com/docs/features/magicdns)

На `m1max.local`/`m3max.local` с удалённого `zenbook` полагаться не стоит: `.local` использует link-local multicast `224.0.0.251`/`FF02::FB`, а обычная unicast subnet route не переносит этот link-local discovery между links. [RFC 6762, section 3](https://www.rfc-editor.org/rfc/rfc6762.html#section-3)

## «Только когда Macs в одной LAN»

У Tailscale нет встроенной conditional advertisement, привязанной к наличию конкретного downstream host. Пока `um790pro` онлайн и рекламирует одобренный `/32`, route остаётся у клиентов. Control plane не проверяет, находится ли Mac за router; если Mac ушёл, спит или недоступен, `ssh` просто завершится timeout. Даже при истёкшем ключе connector routes намеренно остаются и fail closed, чтобы не допустить утечку трафика в другую сеть. [Tailscale subnet-router caveats](https://tailscale.com/docs/features/subnet-routers#caveats), [route injection](https://tailscale.com/docs/reference/route-injection#when-routes-are-injected)

Это уже даёт требуемую **фактическую** условность: соединение работает только при LAN reachability. Автоматически включать/выключать advertisement по ARP/ping можно отдельным NetworkManager/systemd script, но для pilot это лишняя, склонная к гонкам автоматика: сон Mac, Wi-Fi power saving и временная потеря ARP будут дёргать route без реальной пользы.

Нужно также учитывать:

- «одна сеть» должна означать реальную IP-доступность: guest Wi-Fi/client isolation или разные VLAN могут блокировать `um790pro -> Mac`;
- если `um790pro` остаётся в tailnet, но теряет домашний LAN-интерфейс, route не станет автоматически здоровым;
- fixed `/32` уменьшает доступную поверхность по сравнению со всем `/24`, но на roaming Linux laptop может перехватить совпавший адрес в другой локальной сети; Tailscale отдельно предупреждает о route conflicts на non-fixed interfaces;
- для типичных пересекающихся `192.168.x.x` Tailscale предлагает 4via6, который даёт LAN-ресурсу уникальный Tailscale IPv6-псевдоадрес. [LAN route conflicts](https://tailscale.com/docs/reference/troubleshooting/network-configuration/lan-traffic-overlapping-subnets), [4via6](https://tailscale.com/docs/features/subnet-routers/4via6-subnets)

При исходном условии «`zenbook` через LTE» локального Wi-Fi route conflict обычно нет, поэтому `/32` — разумный первый subnet-router pilot.

## Требования на macOS

На каждом Mac нужно:

1. Включить **System Settings → General → Sharing → Remote Login**.
2. Разрешить доступ только нужному пользователю и использовать SSH public key; full disk access для обычного shell-доступа не обязателен.
3. Убедиться, что macOS firewall не блокирует Remote Login. Apple указывает, что включение sharing service открывает нужный service port, но режим блокировки входящих соединений/ручное deny могут это переопределить.
4. Сделать DHCP reservation и проверить доступ к TCP/22 непосредственно с `um790pro`.
5. Решить вопрос сна: включить **Wake for network access**, а для надёжного удалённого администрирования на питании лучше запретить automatic sleep. Возможность wake зависит от модели/режима сети и должна быть проверена практически.

Источники: [Apple: Remote Login/SSH](https://support.apple.com/guide/mac-help/mchlp1066/mac), [Apple: firewall](https://support.apple.com/guide/mac-help/mh34041/mac), [Apple: sleep and Wake for network access](https://support.apple.com/guide/mac-help/mchle41a6ccd/mac).

Поскольку Tailscale на Mac не работает, это будет обычный OpenSSH, а не Tailscale SSH. Шифрование SSH остаётся end-to-end от `zenbook` до Mac, но Tailscale device identity/MagicDNS/audit на самом Mac отсутствуют.

## Рекомендуемый pilot

1. Сначала проверить уже существующий `ssh m1max` с `zenbook` через LTE. Это валидирует Tailscale reachability `zenbook -> um790pro`, SSH forwarding и доступность Mac без router changes.
2. Зарезервировать текущий LAN IP `m3max` (`192.168.1.144`) и добавить аналогичный
   `ProxyJump` alias — если SSH является единственной задачей, на этом остановиться.
3. Только если нужны прямые LAN IP/другие сервисы, рекламировать два `/32` с default SNAT, вручную approve routes, включить `--accept-routes=true` на `zenbook` и разрешить сначала только `tcp:22`.
4. Проверить по слоям: `tailscale ping um790pro`; с `um790pro` — TCP/22 обоих Macs; на `zenbook` — установленный route (`ip route show table 52`), затем SSH по IP/alias. [Tailscale: Linux route table 52](https://tailscale.com/docs/reference/troubleshooting/network-configuration/tailscale-ip-routes)
5. После успешного pilot решить отдельно: оставить `/32`, перейти на 4via6 для защиты от address overlap или расширить grant на другие конкретные порты.

Итог: **возможность подтверждена**, static route на Macs при default SNAT не нужен. Но для сформулированной SSH-задачи существующий `ProxyJump` проще subnet router и уже реализует нужный путь для `m1max`; subnet routing имеет смысл как следующий уровень общей LAN-доступности.
