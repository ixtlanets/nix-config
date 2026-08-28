# Подключение нового пользователя к Audiobookshelf через Absorb

Публичный сервер: `https://books.nikcode.xyz`.

## Самая короткая инструкция для пользователя

Для Absorb `1.9.3+220` или новее:

1. Установить Absorb и открыть присланную персональную ссылку либо отсканировать
   QR-код.
2. Проверить, что приложение показывает сервер `books.nikcode.xyz` и ожидаемое
   имя пользователя.
3. Нажать **Sign in**.

Адрес сервера, логин и пароль вводить не требуется. Если мессенджер не открывает
ссылку вида `absorb://setup/...`, её можно скопировать и выбрать на экране входа
Absorb **Paste login link**.

## Подготовка ссылки администратором

Функция QR/deep link впервые опубликована в prerelease Absorb `v1.9.3-220`.
До выхода `1.9.3` в stable оба устройства должны использовать совместимую
prerelease-версию: Android — GitHub prerelease или alpha track, iOS — TestFlight
или prerelease IPA.

1. Заранее создать в Audiobookshelf отдельного обычного пользователя. Выдать
   только необходимые библиотеки и возможности; не использовать root/admin.
2. Войти в Absorb под Audiobookshelf-аккаунтом типа `admin` или `root`.
3. Открыть **Settings → Admin Controls → Admin → Users → пользователь**.
4. Нажать кнопку с иконкой **Share** / **Share sign-in**.
5. Проверить адрес: `https://books.nikcode.xyz` без порта и дополнительного пути.
6. Нажать **Create link** и приватно отправить ссылку либо показать QR-код.

Absorb создаёт для пользователя отдельный Audiobookshelf API key с именем вида
`Absorb setup: <username>`. Ссылка автоматически передаёт адрес сервера, имя
пользователя и этот ключ; пароль пользователя в неё не включается.

## Stable `v1.9.2`: подключение через файл

В stable `v1.9.2` QR/deep link ещё отсутствует, но доступен почти такой же flow:

1. Администратор входит в Absorb под account типа `admin` или `root`, открывает
   **Settings → Admin Controls → Admin → Users → пользователь**, нажимает Share
   и выбирает **Create setup file**.
2. Проверяет `https://books.nikcode.xyz` и сохраняет файл
   `absorb_setup_<username>.absorb`.
3. Передаёт файл пользователю приватно.
4. Пользователь на экране входа Absorb нажимает **Import**, выбирает файл и
   подтверждает вход.

Ручной ввод сервера, логина и пароля также не требуется.

## Безопасность и отзыв доступа

Ссылка и `.absorb`-файл содержат действующий API key. Данные в setup link только
Base64URL-кодированы, а не зашифрованы. Это многоразовый credential, а не
одноразовое приглашение.

- передавать ссылку/файл только лично или через доверенный приватный канал;
- не публиковать QR на веб-странице, не сохранять его в этом репозитории и не
  отправлять в общий чат;
- при утечке или потере устройства отозвать ключ `Absorb setup: <username>` в
  Audiobookshelf и создать новый;
- удалять старые setup keys после повторной выдачи, чтобы у пользователя не
  оставалось несколько незаметных способов входа.

Текущее приложение не реализует одноразовый обмен приглашения на новый
device-bound credential. Для действительно одноразовых ссылок потребуется
отдельный enrollment service; для семейного сервера встроенный персональный API
key и возможность его отзыва проще и надёжнее.

## Upstream

- [Absorb releases](https://github.com/pounat/absorb/releases)
- [Release `v1.9.3-220` with sign-in links and QR](https://github.com/pounat/absorb/releases/tag/v1.9.3-220)
- [Setup-link encoding and validation](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/services/setup_link_service.dart)
- [Admin API-key and link generation](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/lib/screens/admin_users_screen.dart)
- [Android `absorb://setup` handler](https://github.com/pounat/absorb/blob/630757d207edcd365ea263399c2aef9b0a670d57/android/app/src/main/AndroidManifest.xml)
