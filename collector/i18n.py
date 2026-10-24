"""Small explicit RU/EN translations; data fields stay language-independent."""
import json
from pathlib import Path

_language = 'en'


def set_language(language):
    global _language
    if language not in ('ru', 'en'):
        raise ValueError('Language must be ru or en')
    _language = language


def tr(ru, en):
    return ru if _language == 'ru' else en


def choose_language(root, override=None, interactive=True):
    config = Path(root) / 'config.json'
    saved = None
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding='utf-8-sig'))
            saved = data.get('language')
        except (ValueError, AttributeError, UnicodeError) as exc:
            raise ValueError('Invalid config.json / Некорректный config.json') from exc
    language = override or (saved if saved in ('ru', 'en') else None)
    if language is None and interactive:
        while True:
            answer = input('Language / Язык: [1] English [2] Русский (Enter = English): ').strip().lower()
            if answer in ('', '1', 'en', 'english'):
                language = 'en'; break
            if answer in ('2', 'ru', 'русский'):
                language = 'ru'; break
            print('Choose 1/en or 2/ru / Выберите 1/en или 2/ru.')
    language = language or 'en'
    set_language(language)
    return language
