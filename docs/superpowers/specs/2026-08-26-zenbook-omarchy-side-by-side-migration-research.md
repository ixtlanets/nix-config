# Миграция Zenbook с NixOS на Omarchy через установку рядом

**Дата проверки:** 2026-08-26

**Статус:** feasibility study; разделы и система не изменялись

**База проверки:** официальный Omarchy Manual и исходный код ветки Quattro;
ISO-инсталлятор проверен на коммите
[`268bac16`](https://github.com/omacom-io/omarchy-iso/commit/268bac16d351a21d867e37565738f458b11cb06c)
от 2026-08-23, Omarchy — на коммите
[`0ae16948`](https://github.com/basecamp/omarchy/commit/0ae1694830b6bd9511042fe1b89a0062d8c083cb)
от 2026-08-25. Это исследование относится к Omarchy 4/Quattro; перед реальной
операцией ISO и инсталлятор нужно перепроверить ещё раз, потому что код активно
меняется.

## Краткий вывод

**Схема технически реализуема, но не целиком в виде простого
«установить рядом → удалить NixOS → расширить Omarchy».**

Штатный ISO Omarchy умеет UEFI-установку в неразмеченное свободное место рядом
с другой ОС, сохраняет существующие разделы и по умолчанию создаёт зашифрованную
систему. Это прямо описано в
[Getting Started](https://omarchy.org/manual/getting-started/) и
[Dual Boot Install](https://omarchy.org/manual/dual-boot-install/).

Для Zenbook есть два осложнения:

1. Фактическая разметка занимает весь NVMe: `1 MiB EF02` → `1 GiB ESP` →
   `LUKS2(encrypted_root)` с `ext4` до конца диска; unallocated space сейчас
   нет. Это совпадает с repository intent в
   [`hosts/zenbook/nixos/disko-config.nix`](../../../hosts/zenbook/nixos/disko-config.nix).
   Чтобы появилось место для Omarchy, придётся **offline** уменьшить сначала
   ext4, затем LUKS-backed раздел. Инсталлятор Omarchy этого не делает.
2. Свободное место после такого shrink будет в конце диска. Omarchy разместит
   в нём собственный `2 GiB` ESP, а затем LUKS2/Btrfs root. После удаления
   старых разделов NixOS освободившееся место окажется **перед** Omarchy ESP и
   root, а не после root. Обычное расширение раздела меняет его конец и не может
   поглотить пространство слева через промежуточный ESP.

Следовательно:

- **side-by-side install и выборочный перенос home — нормальный штатный путь;**
- **простое финальное grow — нет;**
- собрать в итоге один большой Omarchy root можно только через дополнительную
  offline-операцию перемещения разделов и восстановления загрузчика либо через
  повторную full-disk установку/restore;
- самый надёжный вариант остаётся: проверенная внешняя резервная копия данных →
  full-disk Omarchy → выборочное восстановление. Однодисковая схема полезна как
  промежуточный bootable migration path, но не отменяет backup.

## Подтверждённое состояние Zenbook

Read-only инвентаризация на 2026-08-26 подтвердила:

| Объект | Фактическое состояние |
|---|---|
| Диск | `/dev/nvme0n1`, 953.9 GiB, GPT |
| `p1` | 1 MiB, EF02 |
| `p2` | 1 GiB, VFAT, `/boot`, NixOS GRUB |
| `p3` | 952.9 GiB, LUKS2 → ext4 `/` |
| Unallocated | отсутствует |
| ext4 | 937 GiB total, 717 GiB used, 173 GiB available |
| User home | около 223 GiB; точный публичный inventory намеренно не сохраняется |

Крупнейшие категории — рабочие каталоги, локальные application data, модели,
кэши и Docker state. Точный path-by-path inventory остаётся вне публичного
репозитория; для планирования достаточно агрегированных объёмов ниже.

Docker занимает ещё значительную часть root: images 105.8 GB, из них
84.66 GB помечено reclaimable; volumes 20.73 GB, reclaimable 20.43 GB;
build cache 23.81 GB. Это не разрешение автоматически делать prune: особенно
volumes нужно сначала сопоставить с нужными сервисами и данными.

Практический вывод из размеров:

- штатный минимум Omarchy в 32 GiB достижим после shrink, но совершенно
  недостаточен для переноса выбранного home;
- без предварительного удаления заведомо воспроизводимых данных текущие
  173 GiB available ограничивают размер нового Omarchy и оставляют мало
  operational headroom;
- только очевидные кандидаты `.cache` + Trash + `tmp` составляют около
  38.4 GB, а Docker сообщает ещё около 128.9 GB reclaimable; после отдельного
  review это может сделать side-by-side root разумного размера;
- минимальный размер ext4 нельзя выводить простым `total - available`:
  перед планом shrink нужны filesystem check, фактическая оценка minimum size
  и запас. Целевой размер Omarchy следует выбирать только после утверждения
  allowlist и cleanup list.

## Что именно умеет текущий ISO-инсталлятор

| Область | Текущее поведение |
|---|---|
| Install alongside | Да: `Free space install (alongside existing data)` |
| Сохранение существующих разделов | Да: создаются только новые разделы в крупнейшем свободном extent; helper сверяет номера до/после и rollback удаляет только созданные этой попыткой разделы |
| Полностью ручная разметка | Нет штатного arbitrary layout: встроенный `cfdisk` нужен лишь для получения **unallocated free space**; затем фиксированную схему строит сам installer |
| Минимальное место | Один крупнейший свободный extent не меньше 32 GiB; installer использует его целиком |
| Firmware | Free-space path предлагается только при UEFI boot; Secure Boot/TPM по официальному manual должны быть отключены |
| ESP | Создаётся новый отдельный FAT32 ESP размером 2 GiB, даже если ESP уже есть |
| Шифрование | По умолчанию LUKS2 для root; `Ctrl+C` на confirmation переключает в unencrypted mode |
| Файловая система | Btrfs с subvolumes `@`, `@home`, `@log`, `@pkg`, `compress=zstd`, `noatime` |
| LVM | Не используется |
| Bootloader | Limine; новый UEFI entry ставится первым, прежние UEFI entries сохраняются |
| Выбор свободного extent | Автоматически выбирается самый большой; выбрать произвольный готовый раздел или один из нескольких holes нельзя |

Эти детали следуют не только из краткого manual, но и из фактического
[`configurator`](https://github.com/omacom-io/omarchy-iso/blob/268bac16d351a21d867e37565738f458b11cb06c/configs/airootfs/root/configurator):
он проверяет UEFI, ищет крупнейший free extent, резервирует 2 GiB под ESP,
создаёт LUKS2 и Btrfs subvolumes и формирует `pre_mounted_config`. Защита от
ошибки в номере GPT-раздела и scoped rollback реализованы в
[`disk-partitioning.sh`](https://github.com/omacom-io/omarchy-iso/blob/268bac16d351a21d867e37565738f458b11cb06c/configs/airootfs/usr/share/omarchy-iso/disk-partitioning.sh).

Текст manual говорит об установке «в один раздел», но текущая реализация
фактически создаёт **два**: dedicated ESP и root. Для планирования геометрии
диска код инсталлятора является более точным источником.

### ESP и Limine

Free-space path намеренно не переиспользует существующий ESP. Комментарий и
код в `configurator` объясняют это размером UKI и изоляцией другой ОС. Limine
копируется на новый ESP, регистрируется через `efibootmgr`, ставится первым в
BootOrder, а остальные прежние записи остаются в порядке после него. Реализация:
[`phases_impl.py`](https://github.com/omacom-io/omarchy-iso/blob/268bac16d351a21d867e37565738f458b11cb06c/configs/airootfs/usr/share/omarchy-iso/orchestrator/phases_impl.py).

До удаления NixOS следует сохранить его GRUB UEFI entry и проверить, что обе
системы загружаются. Официальный Omarchy manual предлагает добавить чужую ОС в
Limine через `limine-scan`, но отдельная firmware/GRUB entry тоже остаётся
полезным recovery path:
[Dual Boot Install](https://omarchy.org/manual/dual-boot-install/).

## Геометрия именно для текущего Zenbook

Repository intent сейчас выглядит так:

```text
начало диска
├─ p1  1 MiB  EF02 / GRUB BIOS boot
├─ p2  1 GiB  NixOS ESP (/boot)
└─ p3  остальное  LUKS → ext4 NixOS root + /home
конец диска
```

После безопасного shrink `p3` и установки в освободившийся хвост ожидаемая
геометрия будет примерно такой:

```text
начало диска
├─ p1  NixOS EF02
├─ p2  NixOS ESP
├─ p3  уменьшенный NixOS LUKS/ext4
├─ p4  Omarchy ESP, 2 GiB
└─ p5  Omarchy LUKS2 → Btrfs (@, @home, @log, @pkg)
конец диска
```

После удаления `p1..p3`:

```text
[ free space ][ Omarchy ESP ][ Omarchy LUKS2/Btrfs root ]
```

Это и есть барьер: свободное место не смежно с **концом** root. Официальная
документация Btrfs подчёркивает, что `btrfs filesystem resize` не меняет
границы underlying partition; для grow сначала должен быть расширен сам
раздел, причём его старт сохраняется:
[`btrfs-filesystem(8)`](https://btrfs.readthedocs.io/en/latest/btrfs-filesystem.html#subcommand).

## Какие финальные варианты реально доступны

### A. Рекомендуемый: внешний backup и full-disk install

1. Сделать и проверить внешнюю копию выбранных данных.
2. Установить Omarchy full-disk.
3. Восстановить данные поверх свежего home по allowlist.

Плюсы: штатная разметка, один ESP, один LUKS/Btrfs root, минимальный boot risk.
Минус: нужен внешний носитель/сетевое хранилище, способное вместить данные.

### B. Однодисковая side-by-side миграция без последующего объединения

1. Offline уменьшить NixOS LUKS/ext4 настолько, чтобы Omarchy сразу получил
   достаточно большой постоянный root.
2. Установить Omarchy в хвост, перенести данные, проверить несколько boot.
3. После удаления NixOS использовать начало диска как отдельный encrypted data
   volume либо оставить до следующей переустановки.

Плюсы: обе ОС и исходные данные некоторое время доступны на одном диске.
Минусы: пространство не станет частью единого Omarchy Btrfs root; отдельный
volume добавляет собственные mount/encryption decisions.

### C. Однодисковая миграция с последующим move + grow

После удаления NixOS offline переместить Omarchy ESP и закрытый LUKS root
влево, затем расширить root partition вправо, открыть LUKS и увеличить Btrfs до
`max`; после перемещения перепроверить/восстановить Limine UEFI entry.

Это технически возможно: официальный GParted умеет move partitions, отдельно
указывает, что LUKS partition перемещается только при закрытом mapping, а grow
или move требует adjacent unallocated space:
[GParted Manual](https://gparted.org/display-doc.php?name=help-manual).
Он также предупреждает, что перемещение boot partition может сделать систему
незагружаемой, а его man page прямо требует backup из-за риска потери данных:
[`gparted(8)`](https://gparted.org/display-doc.php?name=man-page).

Это **не штатный Omarchy workflow** и наиболее рискованный вариант: move
большого encrypted root — длительное полное перемещение данных, чувствительное
к сбою питания/носителя. Не следует делать его без внешней проверенной копии,
live media и заранее подготовленной chroot/boot-repair процедуры.

### D. Повторная full-disk установка после временной side-by-side стадии

Side-by-side Omarchy используется для проверки железа и подготовки allowlist,
затем данные временно уходят на внешний/сетевой storage, выполняется full-disk
install и restore. Это две установки, зато финальная разметка остаётся штатной.

## Первое опасное действие: уменьшение нынешнего NixOS

Текущий NixOS root — ext4 внутри LUKS, без LVM. Для shrink порядок слоёв должен
идти изнутри наружу: clean unmount/check → shrink ext4 → shrink внешней границы
LUKS-backed partition. Раздел уменьшается последним. ArchWiki отдельно
предупреждает сделать backup и не монтировать filesystem при resize:
[dm-crypt / Resizing encrypted devices](https://wiki.archlinux.org/title/Dm-crypt/Device_encryption#Resizing_encrypted_devices).
Тот же порядок и требование не сделать раздел меньше уже уменьшенной ext4
зафиксированы в официальной для Arch man page
[`resize2fs(8)`](https://man.archlinux.org/man/resize2fs.8.en).

`cryptsetup resize` меняет размер активного mapping, но не raw partition
geometry — это прямо сказано в поставляемой Arch
[`cryptsetup-resize(8)`](https://man.archlinux.org/man/cryptsetup-resize.8.en).
Следовательно, встроенный `cfdisk` Omarchy не заменяет filesystem/LUKS shrink.
Эту фазу нужно выполнять из отдельного live environment с заранее вычисленными
границами и запасом, а не импровизировать во время установки.

## Выборочный перенос home

Копировать всё дерево home поверх свежего Omarchy home не следует.
Omarchy специально создаёт свои desktop defaults через `/etc/skel`, а
пользовательские desktop overrides живут в `~/.config`; официальный список
ключевых Omarchy/Hyprland/terminal файлов приведён в
[Dotfiles](https://github.com/basecamp/omarchy/blob/0ae1694830b6bd9511042fe1b89a0062d8c083cb/manual/31-dotfiles.md).

Начальная policy должна быть allowlist-first.

**Сохранять по умолчанию:**

- документы, фото, видео, музыку и прочие реальные пользовательские данные;
- рабочие каталоги и git repositories, включая этот `nix-config` как источник
  личных настроек;
- выборочные app data, если они не синхронизируются облаком;
- `~/.ssh`, `~/.gnupg`, password store и другие secrets — отдельной фазой с
  проверкой прав и обязательным защищённым backup;
- shell history и точечные dotfiles только после просмотра.

**Не переносить по умолчанию:**

- `~/.cache`, Trash, thumbnails, build outputs, language/package caches;
- `~/.config/hypr`, `~/.config/omarchy` и конфиги штатного terminal — сначала
  оставить свежие Omarchy defaults;
- `~/.local/state/omarchy` и другие generated Omarchy state;
- Nix profiles, channels, store references и сгенерированные Home Manager
  symlinks;
- всё `~/.config` или `~/.local` одним rsync без ревью.

Практическая схема: загрузиться в Omarchy, открыть старый NixOS LUKS read-only,
сначала построить manifest/dry-run, затем копировать allowlist с сохранением
timestamps/xattrs/ACL. Лучше создать в Omarchy того же пользователя `nik`, но
перед копированием всё равно сравнить UID/GID и после проверить ownership.

## Обязательный preflight перед планом с командами

Нужны факты с самого Zenbook, а не только repository intent:

```sh
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,FSUSED,FSAVAIL,MOUNTPOINTS,PARTTYPENAME,UUID
findmnt -no SOURCE,FSTYPE,OPTIONS /
findmnt -no SOURCE,FSTYPE,OPTIONS /boot
sudo parted -s /dev/nvme0n1 unit MiB print free
sudo cryptsetup status encrypted_root
sudo cryptsetup luksDump /dev/nvme0n1p3
sudo efibootmgr -v
df -hT / /home
sudo du -xhd1 "$HOME" | sort -h
test -d /sys/firmware/efi && echo UEFI || echo NOT-UEFI
```

Эти проверки read-only. По их выводу нужно определить:

- реальные номера и границы разделов;
- фактически занятое место ext4 и разумный shrink target с большим запасом;
- объём allowlist данных и место, нужное временному NixOS;
- сколько места сразу отдать постоянному Omarchy root;
- можно ли разместить проверенный backup вне этого же NVMe;
- поддерживает ли конкретная firmware Zenbook две ESP/две boot entries без
  сюрпризов.

## Go / no-go критерии

**Можно продолжать к пошаговому плану**, если одновременно есть:

- проверенная копия незаменимых данных вне изменяемого NVMe;
- UEFI boot и отключённый Secure Boot/TPM согласно Omarchy manual;
- исправный ext4 (`e2fsck`) и достаточно свободного места для offline shrink;
- минимум 32 GiB contiguous unallocated space, практически — заметно больше;
- Omarchy ISO, recovery/live media и возможность восстановить boot из chroot;
- явный выбор финала A/B/C/D выше.

**Не начинать shrink/install**, если единственная копия данных находится на
этом же LUKS-разделе, нет recovery media или ещё не выбран способ обращения со
свободным пространством слева от Omarchy после удаления NixOS.

## Рекомендация для Zenbook

Для минимального риска выбрать **A**: внешний backup → штатный full-disk
Omarchy → allowlist restore. Если важна возможность некоторое время вернуться
в NixOS, выбрать **B/D**: уменьшить NixOS, установить Omarchy в большой хвост,
перенести и проверить данные, а финальную чистую разметку сделать после
доказанной работоспособности Omarchy.

Вариант **C** реализуем, но не рекомендуется как основной: он добавляет самый
опасный шаг — перемещение уже заполненного LUKS/Btrfs root — именно после того,
как миграция почти завершена.
