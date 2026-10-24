from .i18n import tr
"""Local account configuration. Never includes credentials in diagnostics."""
import json
import re
import os
from getpass import getpass
from .storage import atomic_json

NAME = re.compile(r'[A-Za-z0-9_-]{1,64}')
HASH = re.compile(r'[a-fA-F0-9]{32}')
DEFAULT_CONFIG = {'url': 'https://t.me/nft/PlushPepe-1', 'scan': True,
                  'first': 1, 'interval': 0.3}


def validate(accounts):
    if not isinstance(accounts, list):
        raise ValueError(tr('accounts должен быть массивом в sessions/asessions.json.', 'accounts must be an array in sessions/asessions.json.'))
    names, sessions = set(), set()
    for index, account in enumerate(accounts, 1):
        if not isinstance(account, dict):
            raise ValueError(tr(f'Аккаунт #{index}: ожидается объект.', f'Account #{index}: expected an object.'))
        name, session = account.get('name', ''), account.get('session', '')
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(tr(f'Аккаунт #{index}: имя должно содержать буквы A-Z, цифры, _ или -.', f'Account #{index}: name must contain A-Z letters, digits, _ or -.'))
        if not isinstance(session, str) or not NAME.fullmatch(session):
            raise ValueError(tr(f'Аккаунт #{index}: некорректное имя session.', f'Account #{index}: invalid session name.'))
        api_id = account.get('api_id')
        if isinstance(api_id, bool) or not str(api_id).isdigit() or int(api_id) <= 0:
            raise ValueError(tr(f'Аккаунт #{index}: api_id должен быть положительным числом.', f'Account #{index}: api_id must be a positive number.'))
        if not isinstance(account.get('api_hash'), str) or not HASH.fullmatch(account['api_hash']):
            raise ValueError(tr(f'Аккаунт #{index}: api_hash должен содержать 32 шестнадцатеричных символа.', f'Account #{index}: api_hash must contain 32 hexadecimal characters.'))
        if name.casefold() in names or session.casefold() in sessions:
            raise ValueError(tr('Повторное имя аккаунта или сессии в asessions.json.', 'Duplicate account or session name in asessions.json.'))
        names.add(name.casefold()); sessions.add(session.casefold())
    return accounts


def load_accounts(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(tr('sessions/asessions.json повреждён. Исправьте JSON; файл не перезаписан.', 'sessions/asessions.json is corrupt. Fix the JSON; the file was not overwritten.')) from exc
    if not isinstance(data, dict) or 'accounts' not in data:
        raise ValueError(tr('В sessions/asessions.json требуется объект с массивом accounts.', 'sessions/asessions.json must contain an object with an accounts array.'))
    return validate(data['accounts'])


def ask(prompt, check, hidden=False):
    while True:
        value = (getpass(prompt) if hidden else input(prompt)).strip()
        if check(value):
            return value
        print(tr('Некорректное значение. Повторите ввод.', 'Invalid value. Please try again.'))


def add_account(path, accounts):
    print(tr('\nДобавление аккаунта. API ID и API hash: https://my.telegram.org/apps', '\nAdding an account. Get your API ID and API hash at: https://my.telegram.org/apps'))
    print(tr('Код входа и пароль 2FA будут запрошены при подключении к Telegram.', 'The login code and 2FA password will be requested when connecting to Telegram.'))
    names = {a['name'].casefold() for a in accounts}
    name = ask(tr('Имя аккаунта (A-Z, цифры, _ или -): ', 'Account name (A-Z, digits, _ or -): '),
               lambda x: bool(NAME.fullmatch(x)) and x.casefold() not in names)
    session = 'telegram_' + name
    # Reserve session names independently from display names (including legacy files).
    occupied = {a['session'].casefold() for a in accounts}
    if len(session) > 64:
        session = name
    if session.casefold() in occupied or (path.parent / (session + '.session')).exists():
        session = ask(tr('Уникальное имя сессии: ', 'Unique session name: '), lambda x: bool(NAME.fullmatch(x))
                      and x.casefold() not in occupied
                      and not (path.parent / (x + '.session')).exists())
    api_id = int(ask('API ID: ', lambda x: x.isascii() and x.isdigit() and int(x) > 0))
    api_hash = ask(tr('API hash (ввод скрыт): ', 'API hash (hidden input): '), lambda x: bool(HASH.fullmatch(x)), hidden=True)
    updated = accounts + [dict(name=name, session=session, api_id=api_id, api_hash=api_hash)]
    validate(updated)
    atomic_json(path, {'accounts': updated})
    if os.name != 'nt':
        path.chmod(0o600)
    print(tr(f'Настройки {name} сохранены в sessions/asessions.json.', f'Settings for {name} saved to sessions/asessions.json.'))
    return updated


def prepare(root, add=False, listing=False):
    config_path = root / 'config.json'
    if not config_path.exists():
        atomic_json(config_path, DEFAULT_CONFIG)
    folder = root / 'sessions'; folder.mkdir(exist_ok=True)
    if os.name != 'nt':
        folder.chmod(0o700)
    path = folder / 'asessions.json'
    accounts = load_accounts(path)
    # Preserve the existing runner's migration of older config.json accounts.
    if not path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if config.get('accounts'):
            accounts = validate(config['accounts'])
            atomic_json(path, {'accounts': accounts})
            if os.name != 'nt': path.chmod(0o600)
    if listing:
        for account in accounts:
            print(f"{account['name']} | session: {account['session']}")
        if not accounts: print(tr('Аккаунты пока не добавлены. Запустите --add-account.', 'No accounts yet. Run --add-account.'))
        return
    if add or not accounts:
        add_account(path, accounts)
