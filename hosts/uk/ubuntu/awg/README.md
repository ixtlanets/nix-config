# UK AWG — partial, только offline acceptance

Небольшая адаптация owner-accepted Frankfurt userspace lifecycle, **не production
claim** и не приёмка семи узлов. В этой работе bundle не запускался, ключи не
создавались, SSH/network/systemd/firewall/TUN/Docker не использовались. Scope только
свободный UK `91.108.225.14`; France/Italy не затронуты, Frankfurt/Goar/London,
действующие VPN, клиенты и общая документация не меняются.

## Фиксированные собственные ресурсы

| Ресурс | Значение |
|---|---|
| Unit / private install directory | `awg-uk.service` / `/etc/awg-uk`, root `0700` |
| Interface / UAPI | `awguk` / `/run/amneziawg/awguk.sock` |
| Endpoint | `91.108.225.14:49381/UDP` в клиентских профилях |
| Tunnel | `10.214.91.0/24`, server `.1/24`, отдельные пользователи `.2`–`.254/32` |
| MTU | `1280` |
| Runtime ownership | `/run/awg-uk/owned.json`, invocation + ifindex + exact rule snapshot |

Внешние interface, prefix и gateway **неизвестны**, не подставлять Frankfurt
`eth0/32/10.0.0.1` по аналогии. Публичный пример намеренно невалиден до заполнения
проверенными фактами. Все четыре внешних параметра обязательны; адрес разрешён
только UK. Preflight сравнивает фактические address/interface/prefix и gateway
read-only route lookups, а после link-up — forward/return пути каждого peer.
Это sample policy checks к `1.1.1.1/8.8.8.8/9.9.9.9`, не доказательство всех маршрутов.

## Binary/compatibility contract

Из [исходного owner-accepted README](../../../frankfurt/ubuntu/awg-s22-test/README.md#trusted-inputs-lead-responsibility), без скачивания и без локальной перепроверки
самих executables (они не включены):

| linux-amd64 binary | SHA-256, записанный в исходном README |
|---|---|
| `awg`, версия `v3.1.20260812` | `1ac92ba760092d805907a322f539c923673f5924666978612c3e85c0981bb005` |
| `amneziawg-go` | `b53961c848acdc18f36ebd60f7a3f900a0e195be8e582eb721c05fa9ec6b2273` |

Controller и issuer проверят соответствующие hashes на runtime; бинарники должен
отдельно предоставить Lead из доверенного набора, без обновления рабочих узлов.
Минимально известный owner-accepted путь: AWG 3.1+, AmneziaWG Android **3.1.4**,
Galaxy S22 Android 16/backend `v3.1.20260814`; это предыдущий Frankfurt результат,
**не UK E2E** и не обещание совместимости со всеми версиями AWG 3.1+.

Условия старого README сохранены: одинаковые `Jc/Jmin/Jmax`, `S1`–`S4`, `H1`–`H4`,
новый общий для этого сервера `HeaderProtectionKey`, `ContentPaddingAddition = 4-28`,
`RandomTrailers = on`; **AdvancedSecurity отсутствует** в обоих форматах. Native
server format без `Address/MTU/DNS/Table/FwMark/Endpoint` и quick-hooks. Каждый peer
имеет новый независимый keypair и PSK; ключи других сервисов не читаются и не
используются. Issuer вызывает `awg genkey/pubkey/genpsk` только по явной команде;
HPK также новый `genpsk` (32-byte base64). Формат/семантику расширений ещё необходимо
проверить pinned native daemon и Android import на UK — mock tests этого не доказывают.

**Блокер:** исходный публичный README не содержит чисел `J*/S*/H*`. Lead должен
получить/утвердить отдельный несекретный профиль параметров, удовлетворяющий контракту,
не читая приватные клиентские конфиги. Пример не содержит реальных значений или ключей.

## Offline issuer — будущие явные действия оператора, НЕ выполнены

Stdlib Python 3, без QR/UI/management platform. Запускать из проверенной копии bundle;
пути ниже условные, runtime directory обязательно **вне Git checkout**, родитель
выходного server config должен уже быть `0700`. Результаты не печатаются в stdout;
файлы создаются сразу `0600`, каталоги `0700`, symlink/overwrite отвергаются.
Публичный settings input содержит site/profile/client DNS, но **не ключи**.

```sh
# Только после утверждения settings и доверенных бинарников; сейчас НЕ запускать.
python3 issuer.py --directory /secure/uk-issuance init \
  --settings /secure/reviewed-uk-settings.json --awg /secure/trusted/awg --generate-new-keys
python3 issuer.py --directory /secure/uk-issuance add alice \
  --awg /secure/trusted/awg --generate-new-keys
python3 issuer.py --directory /secure/uk-issuance add bob \
  --awg /secure/trusted/awg --generate-new-keys
python3 issuer.py --directory /secure/uk-issuance render --output /secure/server-v1.conf
# Только новый OFFLINE кандидат; НЕ живой отзыв, никаких restart:
python3 issuer.py --directory /secure/uk-issuance render \
  --exclude alice --output /secure/server-without-alice.conf
```

Private state хранит server identity, HPK, пользовательские keypair/PSK, выделения
адресов и client files. Server candidate собирается заново из этого состояния;
существующий server config не читается/не переписывается. Excluded адреса не
переиспользуются; можно исключить всех. Ошибка после сохранения allocation может
оставить неполный выпуск: не удалять его вслепую и не запускать add с тем же именем.
`init/add` создают ключи только с `--generate-new-keys`; `render` не генерирует ключей.
Concurrent add/render сериализованы lock; не редактировать state параллельно.

Client profiles: отдельный `/32`, MTU1280, explicit public IPv4 DNS через tunnel,
`AllowedIPs = 0.0.0.0/0, ::/0`. Native IPv6 захватывается, но IPv6 egress намеренно
не предоставляется; DROP только на собственном inner interface. На внешнем IPv6
interface никаких DROP не добавляется, ограничение всего IPv6 public ingress не
заявляется. Kill-switch вне активного tunnel здесь не настраивается и не проверен.
Client files/identity/PSK/HPK нельзя публиковать, коммитить, отдавать в stdout/QR
логов; передача конкретному пользователю только отдельно согласованным приватным путём.

## Deployment preflight после восстановления SSH — Lead only, не автоматизация

1. Подтвердить именно свободный UK, Ubuntu x86_64, фактические external
   IPv4/prefix/interface/gateway, доступность approved UDP49381 у провайдера,
   отсутствие конфликтов порта/subnet/interface/socket/unit/runtime marker.
2. Снять service baseline действующих служб, firewall/routes/policy rules. Нужны
   Python3, systemd, iproute2 (`ip/ss`), оба iptables frontends с comment/conntrack/
   MASQUERADE, существующий `/dev/net/tun`, нормальный `/var/run -> /run`.
   IPv4 global `ip_forward`, `conf/default/forwarding`, external interface forwarding
   должны **уже** быть `1`; новая `awguk` forwarding тоже проверяется. Если нет —
   остановиться и отдельно согласовать изменение, controller ничего не включает.
3. Заполнить и утвердить settings, получить pinned executables, выпустить **новые**
   server/per-user keys/PSK/HPK явными командами, первым делом один пользователь.
   Проверить native parser и импорт Android, не публикуя config/daemon output.
4. Отдельным разрешённым deploy установить новую private directory, public controller
   и executable binaries `0700` root, runtime site/native server config `0600` root,
   unit `0644` root. Отказать, если install directory/unit уже существуют; никаких
   замен старых bundles. Только этот unit, не enable до живой приёмки. Операции
   установки/старта здесь намеренно не исполняются и installer не поставляется.

Preflight ничего не принимает во владение при конфликте. Сверяет hashes/modes,
проверяет overlap subnet со всеми IPv4 addresses и non-default routes всех таблиц,
отказывает при stale firewall references к собственному interface/comment.
Не модифицирует маршруты/DNS/sysctl/default policy. Единственный connected `/24`
route появляется неявно с адресом собственного interface; удаляется с ним.

Перед native setconf/interface-up ставятся отдельные exact startup DROP guards.
Permanent guards/permits собираются **позади** startup guards; только после полного
успеха startup guards снимаются. IPv4 INPUT с tunnel запрещён, outer UDP разрешён
только на approved interface/address. FORWARD/NAT отдельны для каждого peer `/32`,
только approved external interface; non-public destinations блокируются раньше
accept, return только ESTABLISHED,RELATED. IPv6 INPUT/FORWARD DROP только с/на `awguk`.
Никаких global flush, policy, chain recreation, firewall save/restore/reload.

Локальный lock сериализует lifecycle. Предположения: никто параллельно не создаёт
этот interface и не передвигает firewall rules; trusted daemon создаёт DOWN TUN;
site/native configs не меняются между preflight/up (hash drift отвергается).
Cleanup использует invocation + ifindex и сохранённый snapshot exact rules, а не
текущую конфигурацию; сначала down/delete с подтверждением отсутствия interface,
затем exact rules (включая дубликаты), затем marker. Чужой/recreated interface,
старый invocation и shared UAPI directory не удаляются. При любой cleanup failure
metadata сохраняется; `RuntimeDirectoryPreserve=yes`, автоматического restart нет.
Если daemon не успел зарегистрировать ifindex, существующий interface не удаляется
без доказательства ownership — нужен ручной scoped разбор Lead, не стирание marker.
Config/key-bearing ошибки скрыты, unit stdout/stderr null; failure виден по status
unit и оставшейся metadata, не включать raw tracing/config dumps.

Следующая узкая живая приёмка: один Android peer, свежий handshake, exit IPv4 UK,
public DNS/HTTPS, Wi-Fi + cellular, MTU1280, private-destination block и IPv6 negative
probe с native-IPv6 positive control; затем stop/start **только** этого unit и
сравнение baseline. После этого выдавать ещё отдельных пользователей, не ждать
полной приёмки семи узлов. Отзыв начинает действовать лишь после отдельно утверждённой
установки нового server candidate и scoped reload/restart; issuer этого не делает.

## Проверка сейчас

Из корня repository, без root/network и без исполнения bundle:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s hosts/uk/ubuntu/awg -p 'test_*.py' -v
```

Tests используют только tmpdir, предсказуемые **не-ключи**, fake runner/keygen;
любой случайный реальный subprocess запрещён mock. Проверяются параметры,
permissions/hash checks, per-peer выдача/отзыв, exact cleanup, failure injection
каждой startup mutation, сохранение metadata и staging DROP при частичном failure.
Результат: **33 tests passed**. Не проверены реальные native semantics, systemd
execution, firewall backend, provider network и конечное устройство: статус partial.
