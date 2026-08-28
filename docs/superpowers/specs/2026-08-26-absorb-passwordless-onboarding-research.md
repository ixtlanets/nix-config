# Упрощённое подключение нового пользователя в Absorb

**Дата проверки:** 2026-08-26
**Проверенный upstream:** [`pounat/absorb`](https://github.com/pounat/absorb),
commit [`630757d`](https://github.com/pounat/absorb/commit/630757d207edcd365ea263399c2aef9b0a670d57)

## Краткий вывод

Нужный сценарий уже реализован в Absorb:

```text
администратор создаёт отдельного пользователя
  -> Absorb выпускает dedicated API key от имени этого пользователя
  -> показывает private absorb://setup/... link и QR
  -> пользователь открывает ссылку или сканирует QR
  -> проверяет books.nikcode.xyz и имя пользователя
  -> нажимает Sign In
```

Пользователю не надо вводить имя сервера, username или password. Ссылка содержит
`https://books.nikcode.xyz`, username и отдельный API key; Absorb после
подтверждения автоматически проверяет сервер и входит с этим ключом. Функция
официально появилась в prerelease
[`v1.9.3-220`](https://github.com/pounat/absorb/releases/tag/v1.9.3-220) как
"Shareable sign-in links and QR codes".

Главное ограничение: это **не одноразовое безопасное приглашение**. QR/ссылка
содержит постоянный bearer credential, закодированный Base64URL без шифрования.
Любой, кто получил ссылку, может войти с правами пользователя, пока API key не
отключён или не удалён. Поэтому ссылка удобна для личной выдачи доступа, но её
нельзя публиковать или превращать в постоянный QR на общей странице.

## Доступность по версиям

| Ветка Absorb | Возможность | Пользовательский сценарий |
|---|---|---|
| `v1.9.3-220` и новее | `absorb://setup/...`, Share, Copy, QR и сохранение файла | Открыть ссылку/сканировать QR, проверить сервер и нажать **Sign In** |
| Последний stable `v1.9.2` на дату проверки | setup-link и QR ещё нет, но есть `.absorb` setup file | Получить файл, на login screen нажать **Import**, выбрать файл и подтвердить вход |

На дату проверки последним full/stable release остаётся
[`v1.9.2`](https://github.com/pounat/absorb/releases/tag/v1.9.2), а актуальные
`v1.9.3-*` помечены GitHub как prerelease. Upstream поясняет release tracks:
Google Play open testing и App Store получают full releases, GitHub pre-release,
Android internal testing и iOS TestFlight — alpha builds. Следовательно, обычный
store build пока нельзя считать поддерживающим QR; нужен совместимый prerelease
или ожидание следующего full release. [Absorb README: release
tracks](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/README.md#release-tracks)

Stable fallback подтверждается исходниками тега `v1.9.2`: администратор создаёт
`.absorb` setup file с отдельным API key, а login screen импортирует его и
автоматически переключается на восстановленный account.
[`v1.9.2` admin export](https://github.com/pounat/absorb/blob/v1.9.2/lib/screens/admin_users_screen.dart#L786-L885),
[`v1.9.2` login import](https://github.com/pounat/absorb/blob/v1.9.2/lib/screens/login_screen.dart#L880-L936)

## Что именно реализовано

### Формат ссылки

Absorb регистрирует custom URI scheme и создаёт ссылку вида:

```text
absorb://setup/<base64url-encoded-json>
```

Payload содержит ровно один account:

- `serverUrl`;
- `username`;
- `token` — dedicated Audiobookshelf API key;
- опциональный `userId`;
- опциональные custom HTTP headers.

Парсер принимает только `http`/`https` URL, требует непустые username и token и
ограничивает encoded payload 16 000 символами. Однако `base64Url.encode(JSON)` —
это только обратимое кодирование, не конфиденциальность.
[`SetupLinkService`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/services/setup_link_service.dart#L30-L125),
[`BackupService.buildSetupFile`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/services/backup_service.dart#L448-L476)

### Создание администратором

В Absorb администратор открывает пользователя и нажимает share icon. Для root
этот action намеренно не показывается. Приложение:

1. спрашивает URL, который будет использовать новый пользователь;
2. вызывает `POST /api/api-keys` и создаёт ключ с именем
   `Absorb setup: <username>` от имени выбранного user;
3. не передаёт срок действия, то есть ключ создаётся без expiration;
4. формирует setup link;
5. показывает QR и действия **Share link**, **Copy link**, **Save setup file**.

[`admin_users_screen.dart`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/screens/admin_users_screen.dart#L386-L402),
[`создание ключа и ссылки`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/screens/admin_users_screen.dart#L795-L892),
[`QR/share UI`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/widgets/setup_link_share_sheet.dart#L1-L153)

### Получение пользователем

Android регистрирует browsable handler для scheme `absorb`, host `setup`; iOS
регистрирует тот же custom scheme через `CFBundleURLTypes`.
[`AndroidManifest.xml`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/android/app/src/main/AndroidManifest.xml#L44-L49),
[`Info.plist`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/ios/Runner/Info.plist#L92-L111)

После открытия Absorb показывает hostname и username и требует явное
подтверждение. Затем вызывает `loginWithApiKey`; password через ссылку не
передаётся. Если камера или messenger не открывает нестандартную схему, login
screen содержит fallback **Paste login link**.
[`setup-link login`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/widgets/setup_link_login.dart#L9-L74),
[`Paste login link`](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/screens/login_screen.dart#L1022-L1092)

Это custom URL scheme, а не iOS Universal Link и не Android verified App Link:
реализация не использует HTTPS domain association. Поэтому:

- Absorb должен быть уже установлен;
- некоторые messengers/QR scanners могут показать ссылку как текст вместо
  запуска приложения — тогда нужен **Paste login link**;
- scheme не имеет криптографической связи с разработчиком приложения и может
  быть зарегистрирован другим приложением.

Apple прямо предупреждает, что другое приложение может зарегистрировать ту же
scheme и обработчик при конфликте не определён; для уникальной защищённой связи
рекомендуются Universal Links. Android также рекомендует verified App Links для
защиты от deep-link interception. [Apple: custom URL scheme
security](https://developer.apple.com/documentation/xcode/defining-a-custom-url-scheme-for-your-app),
[Android: unsafe deep links](https://developer.android.com/privacy-and-security/risks/unsafe-use-of-deeplinks)

## Рекомендуемая процедура для `books.nikcode.xyz`

### Подготовка администратором

1. Создать в Audiobookshelf отдельного **non-admin** пользователя. Не раздавать
   один общий account: Audiobookshelf не поддерживает account sharing и progress
   хранится per user. Ограничить доступ нужными libraries/tags и включить только
   необходимые permissions. [Audiobookshelf user
   management](https://audiobookshelf.org/docs/documentation/server-management/user-management/)
2. Убедиться, что на обоих устройствах Absorb поддерживает setup links
   (`v1.9.3-220+`). Для store build `v1.9.2` использовать `.absorb` file fallback.
3. Войти в Absorb под account типа `admin` или `root`, затем открыть
   **Settings -> Admin Controls -> Admin -> Users -> <пользователь>** и нажать
   share icon.
4. Проверить URL **ровно** `https://books.nikcode.xyz` — без порта и без
   дополнительного path.
5. Нажать **Create link**.
6. Если пользователь находится рядом, показать QR на своём экране. Иначе
   передать link через доверенный end-to-end encrypted канал.

### Максимально короткая инструкция пользователю

> 1. Установи/обнови Absorb.
> 2. Отсканируй присланный QR или открой private link.
> 3. Проверь, что показан сервер **books.nikcode.xyz** и твоё имя.
> 4. Нажми **Sign In**. Больше ничего вводить не нужно.

Если ссылка не открыла приложение:

> Скопируй ссылку целиком, открой Absorb, на экране входа выбери **Paste login
> link**, вставь её и нажми **Sign In**.

Для stable `v1.9.2`:

> Сохрани присланный `.absorb` файл, открой Absorb, на экране входа нажми
> **Import**, выбери файл и подтверди вход.

## Security assessment

### Что хорошо

- password пользователя вообще не передаётся;
- используется отдельный key, связанный с конкретным non-admin user и
  наследующий только его permissions;
- key можно независимо deactivate/delete, не меняя пароль и не завершая другие
  sessions;
- получатель перед входом видит server hostname и username;
- Absorb заявляет, что server URL и auth token хранятся на устройстве и данные
  не проксируются через сервис разработчика. [Absorb privacy
  policy](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/PRIVACY_POLICY.md)

### Что важно принять

- API key является reusable bearer credential, а не одноразовым invite code;
- текущая генерация не задаёт expiration и setup payload называет его standing
  bearer key;
- QR, screenshot, clipboard, chat history, notification preview и `.absorb`
  file следует считать эквивалентом пароля;
- простое удаление сообщения после подключения снижает случайное распространение,
  но **не** аннулирует key;
- revoke/deactivate key немедленно лишит подключённый Absorb этого способа
  доступа; для продолжения работы придётся выдать новый link/key или выполнить
  обычный JWT/OIDC login;
- custom `absorb://` link потенциально может перехватить другое приложение,
  зарегистрировавшее ту же scheme.

Audiobookshelf документирует API keys как revocable credentials, acting on behalf
of a user, но отдельно рекомендует third-party clients использовать standard JWT
auth, а API keys — для server-to-server automation. Таким образом, функция Absorb
удобна, но сознательно выбирает долговечный API key ради onboarding без ввода
credentials. [Audiobookshelf API Keys](https://audiobookshelf.org/docs/documentation/server-management/api-keys/)

Практические guardrails:

- только отдельный non-admin account на человека;
- minimum libraries/tags/permissions;
- один generated key на пользователя/устройство, чтобы можно было отозвать его
  адресно;
- имя ключа `Absorb setup: <username>` не менять: оно упрощает аудит;
- не публиковать QR на сайте, в README или общем чате;
- после подключения удалить локальный screenshot/file и сообщение у обеих
  сторон, насколько позволяет messenger;
- при потере устройства или подозрении на утечку отключить соответствующий key
  в **Audiobookshelf -> Settings -> Users -> API Keys** и выдать новый;
- периодически проверять `lastUsedAt` и удалять неиспользуемые keys.

## Альтернативы

| Вариант | Ввод пользователем | Безопасность/ограничения | Вывод |
|---|---|---|---|
| Absorb QR/setup link | Только подтверждение | Максимально просто, но reusable unencrypted bearer в link | Лучший текущий вариант для небольшого доверенного круга |
| `.absorb` setup file | Import + подтверждение | Те же credential risks, менее удобно | Stable fallback |
| Обычный local login | URL + username + password | Нет bearer в передаваемой ссылке; стандартный JWT/refresh flow | Безопаснее для массовой выдачи, хуже UX |
| OIDC/SSO | URL один раз + login у IdP | PKCE/short-lived auth flow; отдельная IdP-инфраструктура | Лучший долгосрочный passwordless UX, особенно с passkey, но не zero-config |
| Audiobookshelf Public Share/RSS | Открыть media link | Без account и без server-side progress sync; не полный Absorb account | Только для разовой раздачи конкретной книги/feed |

Absorb поддерживает OIDC/SSO, а Audiobookshelf документирует mobile OAuth flow с
PKCE и allowlisted redirect URI. Но готовой ссылки, которая одновременно
предзаполняет `books.nikcode.xyz` и запускает OIDC без standing API key, в
текущем Absorb нет. [Audiobookshelf OIDC](https://audiobookshelf.org/docs/documentation/server-management/oidc-authentication/),
[Absorb features](https://github.com/pounat/absorb#features)

В core Audiobookshelf также нет документированного user invitation flow:
администратор создаёт account, после чего пользователь проходит local/OIDC auth.
Public Shares и hosted RSS действительно работают без login, но Audiobookshelf
прямо указывает, что server-side progress там не отслеживается. [User
management](https://audiobookshelf.org/docs/documentation/server-management/user-management/),
[Public Shares](https://audiobookshelf.org/docs/documentation/libraries/common-content/public-shares/)

## Рекомендация

Для текущего личного сервера использовать встроенный Absorb setup link/QR после
перехода на `v1.9.3-220+`, с отдельным minimally privileged user и приватной
передачей QR. Это полностью достигает цели "не вводить сервер, login и password".

Не размещать постоянный onboarding QR на `books.nikcode.xyz`: такой QR фактически
будет бессрочным ключом доступа. Если нужна выдача большому числу людей,
саморегистрация или настоящий one-time invite, текущей функциональности
Absorb/Audiobookshelf недостаточно. Для этого потребуется либо upstream feature с
одноразовым server-side exchange, либо OIDC/passkey onboarding.
