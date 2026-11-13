# France AWG — рабочий минимальный контур

## Результат 2026-11-12

Владелец подтвердил France свободным и разрешил root reset, установку ключа и VPN.
На `194.87.166.59` (Ubuntu 24.04, x86_64) новый `awg-fr` запущен; после живой
приёмки включён автозапуск. Перезагрузка сервера и restart сервиса не выполнялись.
Действующие VPN на ноутбуке и старых VPS не переключались и не перезапускались.
London остаётся исключительно личным fallback владельца.

Выпущены **две независимые пользовательские конфигурации**, `user-001` и
`user-002`; обе уже активированы на сервере и каждая проверена реальным
подключением из домашней сети. Есть отдельный служебный peer `acceptance`.
Все identity, client keys, PSK и HPK новые; файлы с ключами находятся вне Git,
каталоги `0700`, файлы `0600`. Клиентские private keys на VPS не переносились.

Проверка выполнена pinned native AWG в одноразовых user/network/mount namespaces.
Подписанный Arch-пакет pasta распакован только во временный private state,
**без установки в систему**. Outbound UDP привязан к `wlo1`; сервер подтвердил
source IP домашнего positive control, а не выход действующего VPN.
Для каждой выдаваемой конфигурации прошли:

- свежий handshake, двусторонний transfer и HTTPS с выходом `194.87.166.59`;
- DNS-запрос к `1.1.1.1` через tunnel и HTTPS к `example.com` с проверкой сертификата;
- блокировка доступа к tunnel SSH и частному адресу домашнего шлюза;
- отрицательная IPv6-проба и отсутствие прямого fallback после остановки
  **изолированного** тестового клиента.

До/после всех проверок совпали три защищённые локальные службы (включая PID/start
metadata), маршруты, policy rules и firewall; `zenawg` продолжал работать.
Это не непрерывная сертификация отсутствия потерь пакетов.

**Ограничения:** новый импорт на Android, Wi-Fi/cellular switching и reboot ещё
не проверены. Для IPv6 negative probe не было native-IPv6 positive control.
Постоянный kill-switch на конечном устройстве этим bundle не устанавливается;
успех private namespace нельзя выдавать за такую гарантию.

## Собственные ресурсы и проверенные внешние факты

| Ресурс | Значение |
|---|---|
| Unit / install directory | `awg-fr.service` / `/etc/awg-fr`, root `0700` |
| Interface / UAPI | `awgfr` / `/run/amneziawg/awgfr.sock` |
| Endpoint | `194.87.166.59:49381/UDP` |
| External interface / prefix / gateway | `eth0` / `24` / `194.87.166.1` |
| Tunnel | `10.214.59.0/24`, server `.1/24`, peer allocations `.2`–`.254/32` |
| Current allocations | acceptance `.2`, user-001 `.3`, user-002 `.4` |
| MTU / client DNS | `1280` / `1.1.1.1, 9.9.9.9` |
| Ownership metadata | `/run/awg-fr/owned.json`: invocation, ifindex, exact rules |

Preflight сравнивает реальные address/interface/prefix/gateway и policy routes к
`1.1.1.1/8.8.8.8/9.9.9.9`, затем forward/return paths каждого peer. Это выборочные
проверки, не доказательство всех возможных маршрутов. На свободном France отдельно
включены и сохранены только `net.ipv4.ip_forward`,
`net.ipv4.conf.default.forwarding`, `net.ipv4.conf.eth0.forwarding`.
Controller сам sysctl не меняет; forwarding новой `awgfr` также обязан быть `1`.

## Binary/compatibility contract

Бинарники скопированы read-only из доверенного Frankfurt набора и проверены по
SHA-256 локально, при переносе и controller preflight; рабочий Frankfurt не менялся.

| linux-amd64 binary | SHA-256 |
|---|---|
| `awg`, `v3.1.20260812` | `1ac92ba760092d805907a322f539c923673f5924666978612c3e85c0981bb005` |
| `amneziawg-go` | `b53961c848acdc18f36ebd60f7a3f900a0e195be8e582eb721c05fa9ec6b2273` |

Перенесены только 13 whitelisted несекретных параметров совместимости:
`Jc/Jmin/Jmax`, `S1`–`S4`, `H1`–`H4`, `ContentPaddingAddition`, `RandomTrailers`.
HPK сгенерирован заново (`genpsk`, 32-byte base64). Native backend принял новые
конфигурации и прошёл реальный E2E. `AdvancedSecurity` в файлах отсутствует.
Предыдущий owner-accepted Android путь — AmneziaWG **3.1.4**, S22 Android 16,
backend `v3.1.20260814` на Frankfurt; это не новая приёмка France на телефоне
и не обещание поддержки старых клиентов либо всех версий AWG.

## Компоненты и выдача

- [Controller](control.py): preflight, запуск и ownership-safe cleanup.
- [Unit](awg-fr.service): foreground daemon, private runtime, ограниченные права;
  stdout/stderr отключены, `Restart=no`, core dumps запрещены.
- [Offline issuer](issuer.py): новые server/per-user keys, уникальные `/32` и PSK;
  без stdout, symlink/overwrite и runtime внутри Git.
- [Публичный шаблон](settings.example.json) намеренно содержит placeholders;
  его нельзя устанавливать вместо проверенных runtime settings.
- [Offline tests](test_bundle.py): 33 проверки без сети и реальных ключей.

Пример будущей **offline** выдачи из проверенной копии bundle, не инструкция
повторной инициализации текущего состояния:

```sh
python3 issuer.py --directory /secure/fr-issuance init \
  --settings /secure/reviewed-fr-settings.json --awg /secure/trusted/awg --generate-new-keys
python3 issuer.py --directory /secure/fr-issuance add alice \
  --awg /secure/trusted/awg --generate-new-keys
python3 issuer.py --directory /secure/fr-issuance render --output /secure/server-v1.conf
python3 issuer.py --directory /secure/fr-issuance render \
  --exclude alice --output /secure/server-without-alice.conf
```

`add/render` сериализованы lock; `init/add` требуют явного `--generate-new-keys`.
Ошибка после allocation не разрешает удалять state или переиспользовать имя вслепую.
`render --exclude` создаёт только новый кандидат, **не живой отзыв**. Автоматизация
live-add/revoke не реализована: новые peer и соответствующие scoped firewall rules
нужно отдельно активировать согласованным способом, не перезапуская рабочие VPN.
Две текущие пользовательские конфигурации уже установлены и реально проверены.

Клиенты используют MTU1280, public DNS и `AllowedIPs = 0.0.0.0/0, ::/0`.
IPv6 egress намеренно не предоставляется. Файлы с ключами передаются только
адресату приватно; не публиковать, не коммитить и не выводить в логи/QR-транскрипты.

## Lifecycle safety

При конфликте interface/subnet/socket/port/unit/stale rules preflight ничего не
принимает во владение. Проверяет pins, owner/modes, config hashes и policy paths.
Перед native setconf/link-up ставятся exact startup DROP guards; разрешающие
правила остаются за ними до полного успеха. Outer UDP разрешён только на
проверенных external interface/address. FORWARD и MASQUERADE отдельны для каждого
peer; non-public destinations блокируются до permits, return только
ESTABLISHED,RELATED. IPv4 tunnel INPUT запрещён; IPv6 INPUT/FORWARD DROP касается
только `awgfr`. Нет global flush, policy change, chain recreation или общего reload.

Cleanup использует invocation + ifindex и snapshot exact rules, а не текущую
конфигурацию. Сначала подтверждает удаление своего interface, затем удаляет свои
правила и marker. Чужой/recreated interface и общий UAPI directory не удаляются.
При cleanup failure metadata сохраняется; нельзя вслепую стирать marker.
Не включать raw tracing и config dumps для диагностики ошибок, содержащих ключи.

## Локальные тесты

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s hosts/france/ubuntu/awg -p 'test_*.py' -v
```

**33 tests passed**; дополнительно выполнены описанные выше живые native/backend,
systemd/firewall и прямые домашние проверки обеих выдаваемых конфигураций.
Подробный статус остальных узлов и сроки оплаты — в
[реестре приёмки](../../../../docs/vpn-node-acceptance-2026-11.md).
