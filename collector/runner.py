from .i18n import tr, choose_language
from . import __version__
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .accounts import Account, GiftUnavailable, cancel_tasks
from .catalog import discover, metadata, unique
from .models import parse_slug
from .runtime import Counts, Progress, Stop, configure_logs
from .storage import Store, atomic_json
from .setup import prepare, load_accounts

log = logging.getLogger('collector')


class ProjectLock:
    def __init__(self, path):
        self.path, self.file = path, None

    def __enter__(self):
        self.file = self.path.open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ValueError(tr('Сборщик уже запущен из этой папки.', 'A collector is already running from this folder.')) from exc
        return self

    def __exit__(self, *_):
        self.file.close()


class TelethonFailure(logging.Handler):
    def __init__(self, stop):
        super().__init__(logging.WARNING)
        self.stop, self.loop = stop, asyncio.get_running_loop()

    def emit(self, record):
        if not record.name.startswith('telethon'):
            return
        text = record.getMessage()
        if record.levelno >= logging.ERROR or any(word in text.lower() for word in (
                'wrong session id', 'security error', 'server closed the connection')):
            self.loop.call_soon_threadsafe(self.stop.fail, 'Telethon: ' + text)


def migrate_legacy(root, config):
    folder = root / 'sessions'; folder.mkdir(exist_ok=True)
    settings = folder / 'asessions.json'
    if not settings.exists():
        if not config.get('accounts'):
            raise ValueError(tr('Нет sessions/asessions.json с настройками аккаунтов.', 'Account settings are missing from sessions/asessions.json.'))
        atomic_json(settings, {'accounts': config['accounts']})
    accounts = load_accounts(settings)
    for account in accounts:
        name = account['session']
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(tr('Некорректное имя session.', 'Invalid session name.'))
        for suffix in ('.session', '.session-journal', '.session-wal', '.session-shm'):
            old, new = root / (name + suffix), folder / (name + suffix)
            if old.exists():
                if new.exists():
                    if old.read_bytes() != new.read_bytes():
                        raise ValueError(tr(f'Две разные сессии {name}: оставьте актуальный файл в sessions.', f'Two different sessions {name}: keep the current file in sessions.'))
                else:
                    os.replace(old, new)
    if 'accounts' in config:
        config = {key: value for key, value in config.items() if key != 'accounts'}
        atomic_json(root / 'config.json', config)
    return config, accounts


async def collect_collection(entry, accounts, store, progress, stop, first=1, refresh=False, last=None):
    prefix, issued, supply = entry['slug'], entry['issued'], entry['supply']
    if issued <= 0:
        return dict(slug=prefix, status='complete', found=0, issued=issued, supply=supply)
    sample = entry['sample']; _, sample_number = parse_slug(sample['slug'])
    upper = max(issued, supply, sample_number, max(store.numbers(prefix), default=0))
    if last is not None:
        upper = last
    if first < 1 or upper < first:
        raise ValueError(tr('Неверный диапазон номеров.', 'Invalid number range.'))
    target = issued if first == 1 and last is None else min(issued, upper - first + 1)
    found = set() if refresh else {n for n in store.numbers(prefix) if first <= n <= upper}
    progress.name, progress.issued = prefix, target
    progress.found, progress.attempts, progress.phase = len(found), 0, tr('Импорт', 'Importing')
    numbers = iter(range(first, upper + 1))
    if first <= sample_number <= upper and sample_number not in found:
        if store.save(sample, stop):
            progress.counts.success += 1
        found.add(sample_number); progress.found = len(found)

    async def worker(account):
        while len(found) < target:
            stop.check()
            number = next(numbers, None)
            if number is None:
                return
            if number in found:
                continue
            slug = f'{prefix}-{number}'
            try:
                record = await unique(account, slug); record['collected_by'] = account.name
            except GiftUnavailable:
                progress.attempts += 1
                log.warning(tr('%s: номер недоступен: %s', '%s: number unavailable: %s'), account.name, slug)
                continue
            except ValueError as exc:
                progress.attempts += 1
                log.error(tr('%s: неполные данные %s: %s', '%s: incomplete data %s: %s'), account.name, slug, exc)
                continue
            stop.check(); progress.attempts += 1
            if store.save(record, stop):
                progress.counts.success += 1
            found.add(number); progress.found = len(found)
    tasks = [asyncio.create_task(worker(a)) for a in accounts]
    try:
        await asyncio.gather(*tasks)
    finally:
        await cancel_tasks(tasks)
    complete = len(found) >= target
    if not complete:
        log.warning(tr('%s: коллекция неполна: %s/%s; диапазон до %s', '%s: collection incomplete: %s/%s; range ends at %s'), prefix, len(found), target, upper)
    else:
        log.info(tr('%s: завершена: %s/%s', '%s: complete: %s/%s'), prefix, len(found), target)
    return dict(slug=prefix, status='complete' if complete else 'incomplete', found=len(found),
                issued=issued, supply=supply, goal=target, upper_checked=upper,
                checked_at=datetime.now(timezone.utc).isoformat())


async def run(root, args):
    counts, stop = Counts(), Stop()
    (root / 'logs').mkdir(exist_ok=True)
    with ProjectLock(root / 'logs' / 'collector.lock'):
        configure_logs(root, counts)
        handler = TelethonFailure(stop); logging.getLogger().addHandler(handler)
        ui = Progress(counts); accounts, monitors = [], []
        try:
            config = json.loads((root / 'config.json').read_text(encoding='utf-8-sig'))
            config, settings = migrate_legacy(root, config)
            if args.url: config['url'] = args.url
            if args.account:
                settings = [a for a in settings if a['name'].casefold() == args.account.casefold()]
            if not settings: raise ValueError(tr('Нет выбранных аккаунтов.', 'No accounts selected.'))
            if len({a['session'] for a in settings}) != len(settings):
                raise ValueError(tr('Повторное имя сессии в asessions.json.', 'Duplicate session name in asessions.json.'))
            interval = args.interval if args.interval is not None else float(config.get('interval', 0.05))
            store = Store(root); store.reconcile()
            identities = set()
            for setting in settings:
                account = Account(setting, root / 'sessions', interval, stop); accounts.append(account)
                identity = await stop.guard(account.login())
                if identity in identities:
                    raise ValueError(tr(f'{account.name}: этот же аккаунт уже подключён другой сессией.', f'{account.name}: this account is already connected through another session.'))
                identities.add(identity)
                monitors.append(asyncio.create_task(account.monitor()))
            await ui.start()
            if args.single or not config.get('scan', True):
                prefix, number = parse_slug(config['url'])
                record = await stop.guard(unique(accounts[0], f'{prefix}-{number}'))
                record['collected_by'] = accounts[0].name
                entries, unresolved = [metadata(record)], []
                first = last = number
            else:
                entries, unresolved = await stop.guard(discover(accounts, config, store, ui))
                first = args.first if args.first is not None else int(config.get('first', 1))
                last = args.last
            ui.total = len(entries); states = []
            ui.overall_total = sum(e['issued'] if first == 1 and last is None else min(e['issued'], (last if last is not None else e['supply']) - first + 1) for e in entries)
            for entry in entries:
                if states:
                    ui.base_done += ui.found
                stop.check()
                state = await stop.guard(collect_collection(entry, accounts, store, ui, stop,
                    first=first, refresh=args.refresh, last=last))
                states.append(state); ui.finished += 1; ui.complete += state['status'] == 'complete'
                atomic_json(root / 'logs' / 'state.json', dict(collections=states, unresolved=unresolved))
            ui.phase = tr('Готово', 'Done') if not unresolved and ui.complete == ui.total else tr('Есть неполные коллекции', 'Some collections are incomplete')
            return 0 if not unresolved and ui.complete == ui.total else 2
        except BaseException as exc:
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
                ui.phase = tr('Остановлено пользователем', 'Stopped by user'); log.warning(tr('Остановлено пользователем', 'Stopped by user'))
            else:
                ui.phase = tr('СТОП: ошибка, см. logs/errors.log', 'STOP: error, see logs/errors.log')
                log.exception(tr('Весь сбор остановлен: %s', 'All collection stopped: %s'), exc)
            raise
        finally:
            for account in accounts: account.closing = True
            await cancel_tasks(monitors)
            for account in accounts:
                try: await account.close()
                except Exception: log.exception(tr('Ошибка закрытия %s', 'Error closing %s'), account.name)
            if ui.task: await ui.close()
            logging.getLogger().removeHandler(handler)


def main(root):
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument('--version', action='version', version='Telegram Gift Parser ' + __version__)
    language_parser.add_argument('--lang', choices=('ru', 'en'))
    language_args, _ = language_parser.parse_known_args()
    language = choose_language(root, language_args.lang, interactive=not any(
        flag in sys.argv[1:] for flag in ('--help', '-h')))
    parser = argparse.ArgumentParser(description='Telegram Gifts → collection JSONL + unified JSONL')
    parser.add_argument('--version', action='version', version='Telegram Gift Parser ' + __version__)
    parser.add_argument('--lang', choices=('ru', 'en'), help=tr('Язык интерфейса (сохраняется)', 'Interface language (saved for future runs)'))
    parser.add_argument('url', nargs='?')
    parser.add_argument('--single', action='store_true', help=tr('Только подарок по ссылке', 'Only the gift specified by the link'))
    parser.add_argument('--scan', action='store_true', help=tr('Все коллекции сканируются по умолчанию', 'All collections are scanned by default'))
    parser.add_argument('--first', type=int)
    parser.add_argument('--last', type=int, help=tr('Тестовый предел номера каждой коллекции', 'Maximum number to check in each collection'))
    parser.add_argument('--interval', type=float)
    parser.add_argument('--account')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--add-account', action='store_true', help=tr('Добавить аккаунт и выйти', 'Add an account and exit'))
    parser.add_argument('--list-accounts', action='store_true', help=tr('Показать имена аккаунтов без ключей', 'List account names without credentials'))
    parser.add_argument('--setup', action='store_true', help=tr('Настроить первый аккаунт без запуска сбора', 'Set up the first account without collecting'))
    args = parser.parse_args()
    root = Path(root)
    (root / 'logs').mkdir(exist_ok=True)
    with ProjectLock(root / 'logs' / 'collector.lock'):
        prepare(root, add=args.add_account, listing=args.list_accounts)
        config_path = root / 'config.json'
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        config['language'] = language
        atomic_json(config_path, config)
    if args.add_account or args.list_accounts or args.setup:
        return 0
    return asyncio.run(run(root, args))
