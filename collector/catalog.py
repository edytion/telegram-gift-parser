from .i18n import tr
import asyncio
import logging
import re
from datetime import datetime, timezone

from telethon import types
from telethon.tl.functions.payments import GetResaleStarGiftsRequest, GetStarGiftsRequest, GetUniqueStarGiftRequest

from .accounts import GiftUnavailable, cancel_tasks
from .models import gift_record, parse_slug
from .storage import atomic_json

log = logging.getLogger('collector.catalog')


def metadata(record, gift_id=None, title=None):
    prefix, number = parse_slug(record['slug'])
    return dict(slug=prefix, title=title or record.get('nft_name', prefix), gift_id=gift_id if gift_id is not None else record.get('gift_id'),
                issued=int(record['quantity_issued']), supply=int(record['quantity_total']),
                url=f'https://t.me/nft/{prefix}-1', sample=record)


async def unique(account, slug):
    response = await account.call(GetUniqueStarGiftRequest(slug))
    return gift_record(response, slug)


async def resolve(account, gift):
    # A real slug from resale avoids guessing collection spelling.
    response = await account.call(GetResaleStarGiftsRequest(gift_id=gift.id, offset='', limit=1))
    for item in getattr(response, 'gifts', []):
        if isinstance(item, types.StarGiftUnique):
            wrapper = types.payments.UniqueStarGift(gift=item, chats=response.chats, users=response.users)
            return metadata(gift_record(wrapper, item.slug), gift.id, getattr(gift, 'title', None))
    title = getattr(gift, 'title', '') or ''
    prefix = re.sub(r'[^A-Za-z0-9]', '', title)
    if prefix and prefix[0].isalpha():
        for number in range(1, 6):
            try:
                response = await account.call(GetUniqueStarGiftRequest(f'{prefix}-{number}'))
            except GiftUnavailable:
                continue
            if getattr(response.gift, 'gift_id', None) == gift.id:
                return metadata(gift_record(response, response.gift.slug), gift.id, title)
    return None


async def discover(accounts, config, store, progress):
    progress.phase = tr('Получение каталога Telegram', 'Fetching Telegram catalog')
    response = await accounts[0].call(GetStarGiftsRequest(hash=0))
    if not hasattr(response, 'gifts'):
        raise ValueError(tr('Telegram не вернул полный каталог подарков.', 'Telegram did not return the full gift catalog.'))
    candidates = [g for g in response.gifts if isinstance(g, types.StarGift) and (
        getattr(g, 'upgrade_stars', None) is not None or
        getattr(g, 'availability_resale', None) is not None or
        bool(getattr(g, 'upgrade_variants', None)))]
    cursor = iter(candidates)
    found, unresolved = {}, []
    progress.total = len(candidates)

    async def worker(account):
        while True:
            gift = next(cursor, None)
            if gift is None:
                return
            progress.phase = tr(f'Каталог: {len(found) + len(unresolved)}/{len(candidates)}', f'Catalog: {len(found) + len(unresolved)}/{len(candidates)}')
            try:
                entry = await resolve(account, gift)
            except GiftUnavailable:
                entry = None
            if entry:
                entry['upgrade_variants'] = getattr(gift, 'upgrade_variants', None)
                entry['sample']['collected_by'] = account.name
                found[entry['slug'].casefold()] = entry
            else:
                unresolved.append(dict(gift_id=gift.id, title=getattr(gift, 'title', None)))
                log.warning(tr('Не удалось определить slug коллекции gift_id=%s title=%s', 'Could not resolve collection slug gift_id=%s title=%s'), gift.id, getattr(gift, 'title', None))
    tasks = [asyncio.create_task(worker(a)) for a in accounts]
    try:
        await asyncio.gather(*tasks)
    finally:
        await cancel_tasks(tasks)
    # Keep earlier known collections even when no copies are currently on resale.
    requested, _ = parse_slug(config['url'])
    known = {requested.casefold(): config['url']}
    for path in store.directory.glob('*.jsonl'):
        known.setdefault(path.stem.casefold(), f'https://t.me/nft/{path.stem}-1')
    cache = store.root / 'logs' / 'catalog.json'
    if cache.exists():
        import json
        previous = json.loads(cache.read_text(encoding='utf-8-sig'))
        for entry in previous.get('collections', []):
            known.setdefault(entry['slug'].casefold(), entry['url'])
    for key, url in known.items():
        if key not in found:
            prefix, number = parse_slug(url)
            try:
                record = await unique(accounts[0], f'{prefix}-{number}')
            except GiftUnavailable:
                unresolved.append(dict(url=url))
                log.warning(tr('Не найдена стартовая ссылка коллекции %s', 'Could not find the seed link for collection %s'), url)
                continue
            record['collected_by'] = accounts[0].name
            found[key] = metadata(record)
    ordered = sorted(found.values(), key=lambda item: (item['slug'].casefold() != requested.casefold(), item['slug']))
    # Avoid reporting a resolved ID as unresolved when a fallback found it.
    resolved_ids = {entry['gift_id'] for entry in ordered if entry['gift_id'] is not None}
    unresolved = [item for item in unresolved if item.get('gift_id') not in resolved_ids]
    atomic_json(cache, dict(checked_at=datetime.now(timezone.utc).isoformat(),
                collections=[{k: v for k, v in e.items() if k != 'sample'} for e in ordered],
                unresolved=unresolved, candidate_count=len(candidates)))
    if not ordered:
        raise ValueError(tr('Не удалось найти ни одной коллекции; сбор не запущен.', 'No collections found; collection has not started.'))
    for entry in ordered:
        store.path(entry['slug']).touch(exist_ok=True)
    log.info(tr('Каталог: %s подтверждённых коллекций; не разрешено: %s', 'Catalog: %s confirmed collections; unresolved: %s'), len(ordered), len(unresolved))
    return ordered, unresolved
