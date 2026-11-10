# Chromium, SIGKILL и нулевой RLIMIT_RTTIME

Проверено: **2026-11-10**. Только публичные первичные источники. Состояние конкретной машины и происхождение её настроек здесь не фиксируются.

## Вывод

**RLIMIT_RTTIME=0/0 — не исходный default Linux и не «без ограничений».** В ядре исходный лимит — infinity/infinity. В Omarchy публично разобран механизм, который превращал отсутствие rtkit в нулевой hard limit у PipeWire-клиентов и потомков оболочки. Есть сообщения именно о Chromium/Electron, kernel SIGKILL, отсутствии OOM и воспроизведении на обычном SCHED_OTHER с thread CPU timer. Это сильнее совпадения «браузер закрылся», но само по себе не устанавливает источник лимита или ветку убийства в отдельном локальном инциденте.

Источники: [Linux defaults](https://github.com/gregkh/linux/blob/v7.2.15/include/asm-generic/resource.h#L9-L28), [Omarchy #16348](https://github.com/omacom/omarchy/issues/16348), [Chromium reproduction в #12443](https://github.com/omacom/omarchy/issues/12443#issuecomment-5919484768).

## Что ограничивает RTTIME

По [Linux man-pages, getrlimit(2): DESCRIPTION](https://man7.org/linux/man-pages/man2/getrlimit.2.html#DESCRIPTION):

- Единица RLIMIT_RTTIME — **микросекунда**: 200000 µs = 200 ms = 0,2 s.
- Назначение — ограничить CPU-время realtime-процесса между блокирующими системными вызовами, чтобы зациклившийся realtime-код не повесил систему.
- Блокирующий системный вызов сбрасывает счётчик. Вытеснение, истечение кванта и sched_yield() **не** сбрасывают его. Это не просто «один непрерывный участок исполнения на CPU».
- Soft limit ведёт к SIGXCPU; при продолжении расходования CPU сигнал повторяется раз в секунду, пока hard limit не приведёт к SIGKILL. Отдельное раннее предупреждение не гарантировано, если сразу достигнут hard limit.
- 0/0 означает soft=0, hard=0. Отсутствие ограничения обозначается RLIM_INFINITY, не нулём.

RTTIME не равен RLIMIT_CPU: последний ограничивает суммарное CPU-время процесса в **секундах**. RTTIME — не квота браузера на весь срок жизни, не лимит 200 ms на загрузку страницы и не ограничение памяти. Установка 200 ms сама по себе не ускоряет браузер и не даёт realtime-приоритет.

По [getrlimit(2): NOTES](https://man7.org/linux/man-pages/man2/getrlimit.2.html#NOTES), лимиты наследуются через fork(), сохраняются через execve() и общие для потоков процесса. Поэтому лимит оболочки может попасть в приложение, zygote, renderer и GPU-процессы. Непривилегированный процесс не может поднять собственный hard limit ([DESCRIPTION](https://man7.org/linux/man-pages/man2/getrlimit.2.html#DESCRIPTION)).

## Почему ноль опасен даже при SCHED_OTHER

В проверенном [Linux v7.2.15, posix-cpu-timers.c:914–968](https://github.com/gregkh/linux/blob/v7.2.15/kernel/time/posix-cpu-timers.c#L914-L968):

1. check_thread_timers() возвращается раньше, если per-thread expiry cache неактивен (943–944).
2. Иначе проверяется RLIMIT_RTTIME; отдельного условия «поток обязан быть realtime» перед этой проверкой нет.
3. rttime = tsk->rt.timeout * (USEC_PER_SEC / HZ).
4. Hard проверяется **до** soft: check_rlimit(rttime, hard, SIGKILL, ...).
5. check_rlimit() не посылает сигнал только при time < limit. При нулевых счётчике и hard limit: **0 >= 0**, отправляется SIGKILL всей thread group.

Активный thread CPU timer тем самым открывает путь к проверке и для потока, который не работал с realtime-политикой. Не требуется реальное расходование 200 ms realtime-времени. Публичные воспроизведения используют timer_create(CLOCK_THREAD_CPUTIME_ID, ...); переносить вывод на любой настенный или process CPU timer нельзя. Название «RT Watchdog» не доказывает realtime-планирование жертвы.

Источник устанавливает механизм для этого тега, но не дату появления или номер kernel regression. Один стек с posix_cpu_timers_work недостаточен для выбора ветки: этот путь обслуживает и другие CPU-таймеры/лимиты.

## Откуда ноль брался в публичных Omarchy-случаях

[Issue #16348](https://github.com/omacom/omarchy/issues/16348) и [merged PR #16824](https://github.com/omacom/omarchy/pull/16824) описывают цепь:

    rtkit отсутствует / portal запущен до его появления
      → portal сообщает RTTimeUSecMax=0
      → PipeWire client module-rt применяет 0 как RLIMIT_RTTIME
      → omarchy-shell/Quickshell — PipeWire-клиент
      → запущенные им приложения наследуют hard=0

Это не означает, что Hyprland намеренно выставлял всем приложениям нулевой RTTIME. Лимит мог меняться внутри самого приложения при загрузке libpipewire; важен не только родитель.

Исходники подтверждают ключевые звенья:

- [PipeWire 1.6.9:635–642](https://github.com/PipeWire/pipewire/blob/1.6.9/src/modules/module-rt.c#L635-L642): setrlimit(RLIMIT_RTTIME, ...) применяется к процессу.
- [PipeWire:985–1023](https://github.com/PipeWire/pipewire/blob/1.6.9/src/modules/module-rt.c#L985-L1023): читается RTTimeUSecMax, soft/hard ограничиваются через SPA_MIN(..., rttime_max), затем результат применяется; ноль здесь не отбрасывается.
- [xdg-desktop-portal 1.22.1:254–330](https://github.com/flatpak/xdg-desktop-portal/blob/1.22.1/src/realtime.c#L254-L330): realtime-свойства загружаются при создании объекта; ошибка чтения логируется, интерфейс продолжает существовать. Согласуется с репортами о закешированном нуле и необходимости обновить portal после появления rtkit.
- [rtkit-daemon:106–107](https://github.com/heftig/rtkit/blob/master/rtkit-daemon.c#L106-L107): исходное максимальное RTTIME — 200000ULL, то есть 200 ms. Это источник типичного desktop-бюджета, **не default ядра**. Ссылка master подвижная; значение проверено в указанную дату.

Публичная цепь — обоснованная гипотеза для другой машины, не замена проверке её версий и цепочки наследования.

## Репорты и исправления

Статусы проверены через GitHub API; даты UTC.

### 1. Omarchy #16348

[Without rtkit, apps started from omarchy-shell inherit RLIMIT_RTTIME=0 and the kernel RT watchdog SIGKILLs them (Electron/Chromium, claude-desktop)](https://github.com/omacom/omarchy/issues/16348). Открыт **2026-10-22**, закрыт **2026-10-28**.

Body содержит kernel SIGKILL trace, дерево процессов с hard=0, thread CPU timer repro без realtime-планирования, тесты PipeWire-настроек и проверенное исправление. Это подтверждённый механизм в описанном репорте, не только жалоба на падение. [Комментарий](https://github.com/omacom/omarchy/issues/16348#issuecomment-6399605171) добавляет Chrome tab error 9, VS Code killed/code9, отсутствие OOM и смену нуля на unlimited после отключения client module-rt. Один error 9 сам по себе убийцу не определяет.

### 2. Omarchy #12443

[Apps started from the Super+Space menu inherit RLIMIT_RTTIME=0 …; since 4.0.4 this kills SteamVR](https://github.com/omacom/omarchy/issues/12443). Открыт **2026-09-18**, закрыт **2026-10-28**.

Исходный body про realtime SteamVR. [Комментарий от 2026-09-30](https://github.com/omacom/omarchy/issues/12443#issuecomment-5919484768) расширяет триггер до SCHED_OTHER + thread CPU timer и headless Chromium/Playwright: sig=9, code=128, grp=1. [Следующий комментарий](https://github.com/omacom/omarchy/issues/12443#issuecomment-5920036712) подтверждает 200000/200000, выживание repro и два проходящих Playwright-набора после rtkit + reboot.

### 3. Omarchy PR #16824

[Give PipeWire realtime with rtkit and stop the silent app kills](https://github.com/omacom/omarchy/pull/16824). Открыт **2026-10-27**, **merged 2026-10-28**.

Добавляет rtkit в общую базу, у host PipeWire/JACK-клиентов отключает portal realtime path (rtportal.enabled=false), ремонтирует существующие нулевые лимиты и portal. Важен порядок: hard=0 поднимается **до** разрешения клиентам получить realtime. Прочитаны body, комментарий и патчи. Мерж не доказывает, что установленная версия уже содержит/выполнила migration.

### 4. Omarchy PR #17103 — другой сценарий

[Keep Hyprland off rtkit realtime until its RT watchdog kills are fixed](https://github.com/omacom/omarchy/pull/17103). Открыт и **merged 2026-10-30**.

После появления rtkit сам Hyprland получает realtime и может превысить уже **ненулевые** 200 ms. Обход — HYPRLAND_NO_RT=1; PipeWire realtime остаётся. Это не нулевой лимит Chromium.

### 5. Hyprland discussion #16648 — не путать с нулевым лимитом

[Real-time scheduling. Hyprland dies by SIGKILL when reconnecting HDMI](https://github.com/hyprwm/Hyprland/discussions/16648). Создана **2026-10-24**.

Body и комментарии описывают SCHED_RR, HDMI/DPMS, soft=150 ms/hard=200 ms; один вызов драйвера расходовал около 242 ms CPU. Та же семья watchdog, но другой процесс, триггер и ненулевой лимит. [Hyprland PR #16737](https://github.com/hyprwm/Hyprland/pull/16737) открыт 2026-10-30, **closed 2026-11-05, mergedAt=null**: не считать поставленным исправлением.

## Когда исправление попадёт в stable

Дополнительно проверено **2026-11-10**:

- [PR #16824](https://github.com/omacom/omarchy/pull/16824) влит в development-ветку **quattro** 2026-10-28, а не непосредственно в stable. Его milestone — **4.5.1**, без due date: это ориентир, не опубликованный срок выпуска.
- Последний опубликованный stable — [v4.5.0](https://github.com/omacom/omarchy/releases/tag/v4.5.0), опубликован 2026-11-05 в 08:36:53 MSK. Исправления в нём нет: [сравнение с merge-коммитом](https://github.com/omacom/omarchy/compare/b58e5b999c03a1795badfd342a3f02986d854715...v4.5.0) показывает расходящиеся истории; дополнительно проверены дерево тега, отсутствие repair/migration/drop-ins и [базовый список пакетов](https://github.com/omacom/omarchy/blob/v4.5.0/install/omarchy-base.packages) без rtkit.
- Ветка v4-5-1 на момент проверки тоже ещё не содержала merge-коммит. Нельзя утверждать, что 4.5.1 уже выпущен с исправлением.
- [Рецепт development-пакета](https://github.com/omacom/omarchy-pkgs/blob/857fd0c8443052fe9e45060cd72471a80bbd2617/pkgbuilds/omarchy-dev/PKGBUILD) уже указывает на исходники с исправлением. Это не доказывает дату публикации готового бинарного пакета и не означает его поставку в stable.
- Точная дата stable-релиза с исправлением не установлена: milestone due_on=null, опубликованного ETA в проверенных release/PR/issue нет. Закрытие issue и принятие PR не равны доставке исправления пользователям stable.

## Что следует из публичных workaround

- Ненулевой RTTIME или infinity устраняет нулевой порог, не все возможные причины SIGKILL Chromium.
- Установка rtkit сама по себе не исправляет hard=0 уже живущего приложения и может разрешить realtime при старом нуле. Поэтому PR #16824 восстанавливает лимиты и portal в определённом порядке.
- Перезапуск от чистого предка и привилегированная коррекция — разные способы. Изменение только текущего дерева приложения не является постоянным исправлением сессии.
- 200 ms — бюджет realtime-работы между блокировками, не ограничение обычного браузера на всю жизнь. Само повышение RTTIME не повышает производительность. Давать браузеру realtime-приоритет для устранения нулевого лимита не требуется.

Источники: [getrlimit(2)](https://man7.org/linux/man-pages/man2/getrlimit.2.html), [#16348](https://github.com/omacom/omarchy/issues/16348), [#16824](https://github.com/omacom/omarchy/pull/16824).

## Временный backport без конфликта с будущим пакетом

Это **план**, не отчёт о применении или проверке на работающей системе.

- [PKGBUILD omarchy-settings-dev](https://github.com/omacom/omarchy-pkgs/blob/857fd0c8443052fe9e45060cd72471a80bbd2617/pkgbuilds/omarchy-settings-dev/PKGBUILD#L278-L281) копирует etc/. в payload пакета. Следовательно будущие /etc/pipewire/{client,jack}.conf.d/50-omarchy-rtkit.conf будут package-owned. Не занимать эти пути заранее неучтёнными локальными файлами.
- Для временных локальных drop-in использовать отдельное имя, например 40-local-rtkit-backport.conf, с тем же содержимым module.rt.args = { rtportal.enabled = false }. Это не подмена context.modules и не пользовательский 99-override, который перекрыл бы будущий официальный 50.
- [PR #17103](https://github.com/omacom/omarchy/blob/cf71857c2589725558db9a8001ca353abedee360/default/uwsm/default#L13-L18) добавляет HYPRLAND_NO_RT=1. При полном backport с установкой rtkit предусмотреть этот guard для следующего старта compositor; поддержка уже есть в [Hyprland v0.56.2](https://github.com/hyprwm/Hyprland/blob/v0.56.2/src/main.cpp#L256-L257). Это не требует перезапуска текущего compositor.
- [Закреплённый upstream helper](https://github.com/omacom/omarchy/blob/b58e5b999c03a1795badfd342a3f02986d854715/bin/omarchy-realtime-repair) меняет не только Chromium: исправляет hard=0 у logged-in regular users, устанавливает rtkit под runtime-mask, чинит portal и при необходимости перезапускает audio units вызывающей сессии. Portal restart может прервать screen sharing; audio restart — звук и звонки. Shell/browser/Hyprland helper не перезапускает.
- Повторное выполнение предусмотрено: исправляются нулевые лимиты, здоровые portal/realtime-audio не требуют повторного рестарта. Не создавать вручную marker официальной миграции: [штатная миграция](https://github.com/omacom/omarchy/blob/b58e5b999c03a1795badfd342a3f02986d854715/migrations/1789747667.sh) должна позже выполниться сама.
- Не править package-owned /usr/share/omarchy и не класть локальную команду под официальным именем в PATH. Если понадобится отдельный privileged helper, после аудита разместить закреплённый код в защищённом root-owned каталоге вне PATH, а не запускать root-код из изменяемой пользователем staging-копии.
- После реального stable-обновления проверить владение официальными 50 через pacman -Qo, содержимое/эффективность конфигурации, результат штатной миграции и официальный compositor guard. Только затем удалить собственные уникальные drop-in, user guard и временный helper; rtkit, официальные файлы и внутренние lock/pending-файлы не удалять для косметической очистки. Не привязывать cleanup только к номеру версии.

## Охват и ограничения

Проверены публичные Issues/PR и Discussions Omarchy и связанные Hyprland Discussions/PR. API подтвердил перенос basecamp/omarchy в [omacom/omarchy](https://github.com/omacom/omarchy). По старому имени gh search возвращал ошибку недоступного репозитория; с новым именем работал. Rate-limit отказов не было.

Восемь поисковых запросов: два неуспешных по старому имени; по новому — Issues/PR RTTIME, Issues chromium, Discussions chromium, Discussions RTTIME, Discussions chromium killed; Hyprland Issues/PR RTTIME. Общий Chromium-поиск дал 571 issue, просмотрена первая страница (40); целевой RTTIME-поиск — 13 результатов. Discussions RTTIME: 0 результатов; chromium killed: одна нерелевантная дискуссия о memory-pressure stutter. Не все 571 issue были прочитаны. Отсутствие совпадения по словам не доказывает отсутствия других дискуссий.

Не установлены: первый upstream kernel commit с этим поведением, отдельный принятый kernel fix, применимость миграций к конкретной установленной системе и локальный источник hard=0. Совпадение публичного механизма сильное; окончательный вывод о конкретном убийстве требует собственных трасс/контрольного воспроизведения.
