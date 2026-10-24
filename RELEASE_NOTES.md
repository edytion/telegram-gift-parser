# Telegram Gift Parser v0.1.0

> Licensing update (2026-10-24): current distribution uses the Personal Noncommercial Use License. Earlier MIT revisions retain their original permissions. See LICENSE.
>
> Изменение условий (24.10.2026): текущая публикация использует лицензию личного некоммерческого использования. Прежние MIT-версии сохраняют исходные разрешения. См. LICENSE.

**Русский**

Первый публичный релиз. Парсер собирает сведения о коллекционных подарках Telegram и сохраняет их в JSONL — отдельно по коллекциям и в общую базу.

В этой версии доступны настройка аккаунтов при первом запуске, несколько сессий, интерфейс RU/EN, продолжение прерванного сбора, обновление снимков и обработка FLOOD_WAIT. В README есть инструкции запуска и примеры работы.

Для Windows скачайте `gift-parser-v0.1.0.zip`, распакуйте архив и запустите `START.bat`. Понадобятся Python 3.10+ и ваши API ID/hash с my.telegram.org/apps. Сначала рекомендуем проверить один подарок с `--single`.

Используйте отдельные аккаунты. Автор не гарантирует защиту от блокировок; полнота сбора зависит от Telegram.

**English**

The first public release collects Telegram collectible gift data and saves it to per-collection JSONL files and a combined database.

This version includes first-run account setup, multiple sessions, an English/Russian CLI, resumable collection, snapshot refresh and FLOOD_WAIT handling. The README includes setup instructions and screenshots.

On Windows, download `gift-parser-v0.1.0.zip`, extract it and run `START.bat`. You will need Python 3.10+ and your own API ID/hash from my.telegram.org/apps. We recommend starting with a single gift using `--single`.

Use separate accounts. The author cannot guarantee protection from account bans; data coverage depends on Telegram.

---

thugger / edytion · https://github.com/edytion
