from .i18n import tr
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger('collector.storage')
SLUG = re.compile(r'([A-Za-z][A-Za-z0-9]*)-([1-9][0-9]*)')


def rows(path):
    if not path.exists():
        return
    with path.open('r', encoding='utf-8-sig') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(tr(f'{path.name}:{line_number}: повреждён JSONL; исходный файл сохранён.', f'{path.name}:{line_number}: corrupt JSONL; original file preserved.')) from exc
            if not valid(row):
                raise ValueError(tr(f'{path.name}:{line_number}: неполная запись; исходный файл сохранён.', f'{path.name}:{line_number}: incomplete record; original file preserved.'))
            yield row


def valid(row):
    return (isinstance(row, dict) and isinstance(row.get('slug'), str)
            and SLUG.fullmatch(row['slug']) is not None
            and all(row.get(k) for k in ('model', 'backdrop', 'symbol', 'quantity')))


def append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size:
        with path.open('rb') as stream:
            stream.seek(-1, 2)
            needs_newline = stream.read(1) != b'\n'
    else:
        needs_newline = False
    with path.open('a', encoding='utf-8') as stream:
        if needs_newline:
            stream.write('\n')
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Store:
    """Collection files and unified are reconciled after any interrupted dual write."""
    def __init__(self, root):
        self.root = Path(root)
        self.directory = self.root / 'gifts_database'
        self.unified = self.directory / 'unified' / 'unified.jsonl'
        self.unified.parent.mkdir(parents=True, exist_ok=True)
        self.unified.touch(exist_ok=True)
        self.seen = {}
        self.unified_keys = set()

    @staticmethod
    def key(row):
        return (row['slug'].casefold(), row.get('checked_at', ''))

    def path(self, collection):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', collection):
            raise ValueError(tr('Некорректное имя коллекции.', 'Invalid collection name.'))
        return self.directory / (collection + '.jsonl')

    def remember(self, row):
        prefix, number = SLUG.fullmatch(row['slug']).groups()
        self.seen.setdefault(prefix.casefold(), set()).add(int(number))

    def reconcile(self):
        # The legacy source is retained. Import only unseen snapshots.
        collection_keys = set()
        for path in self.directory.glob('*.jsonl'):
            for row in rows(path):
                collection_keys.add(self.key(row))
                self.remember(row)
        for row in rows(self.unified):
            self.unified_keys.add(self.key(row))
            self.remember(row)
            if self.key(row) not in collection_keys:
                append(self.path(SLUG.fullmatch(row['slug'])[1]), row)
                collection_keys.add(self.key(row))
        for row in rows(self.root / 'gifts.jsonl'):
            if self.key(row) not in collection_keys:
                append(self.path(SLUG.fullmatch(row['slug'])[1]), row)
                collection_keys.add(self.key(row))
                self.remember(row)
        repaired = 0
        for path in self.directory.glob('*.jsonl'):
            for row in rows(path):
                key = self.key(row)
                if key not in self.unified_keys:
                    append(self.unified, row)
                    self.unified_keys.add(key)
                    repaired += 1
        if repaired:
            log.info(tr('В общую базу добавлено %s записей при сверке', 'Reconciliation added %s records to the unified database'), repaired)

    def has(self, prefix, number):
        return number in self.seen.get(prefix.casefold(), set())

    def numbers(self, prefix):
        return self.seen.get(prefix.casefold(), set())

    def save(self, row, stop=None):
        if stop:
            stop.check()
        if not valid(row):
            raise ValueError(tr('Пустая запись не может быть сохранена как подарок.', 'An empty record cannot be saved as a gift.'))
        key = self.key(row)
        if key in self.unified_keys:
            return False
        prefix = SLUG.fullmatch(row['slug'])[1]
        append(self.path(prefix), row)
        append(self.unified, row)
        self.unified_keys.add(key)
        self.remember(row)
        return True
