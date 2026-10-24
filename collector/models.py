from .i18n import tr
import re
from datetime import datetime, timezone
from telethon import types, utils

def parse_slug(value):
    match = re.fullmatch(r'(?:https?://t\.me/nft/)?([A-Za-z][A-Za-z0-9]*)-([1-9][0-9]*)/?', value.strip())
    if not match:
        raise ValueError(tr('Нужна ссылка https://t.me/nft/PlushPepe-1 или PlushPepe-1', 'Expected https://t.me/nft/PlushPepe-1 or PlushPepe-1'))
    return match[1], int(match[2])

def attribute_data(attribute):
    name = attribute.name
    rarity = getattr(attribute, 'rarity', None)
    permille = getattr(attribute, 'rarity_permille', None)
    if permille is None:
        permille = getattr(rarity, 'permille', None)
    percent = permille / 10 if permille is not None else None
    tier = type(rarity).__name__.removeprefix('StarGiftAttributeRarity') if rarity else ''
    label = f'{percent:g}%' if percent is not None else tier
    return name + (f' {label}' if label else ''), name, percent

def gift_record(response, requested_slug):
    gift = response.gift
    if not isinstance(gift, types.StarGiftUnique):
        raise ValueError(tr('API не вернул коллекционный подарок.', 'API did not return a collectible gift.'))
    if gift.slug.casefold() != requested_slug.casefold():
        raise ValueError(tr('API вернул другой slug; запись пропущена.', 'API returned a different slug; record skipped.'))
    peer = getattr(gift, 'owner_id', None)
    owner_id = utils.get_peer_id(peer) if peer else None
    owner = getattr(gift, 'owner_address', None) or getattr(gift, 'owner_name', None) or ''
    username = None
    if not owner and peer:
        for entity in list(getattr(response, 'users', [])) + list(getattr(response, 'chats', [])):
            if utils.get_peer_id(entity) == owner_id:
                owner = utils.get_display_name(entity)
                username = getattr(entity, 'username', None)
                break
    # Telegram may not disclose a name. Preserve a real ID without inventing one.
    owner = owner or (f'id:{owner_id}' if owner_id is not None else None)
    issued, total = gift.availability_issued, gift.availability_total
    record = {
        'slug': gift.slug, 'gift_id': gift.gift_id, 'collectible_id': gift.num,
        'nft_name': gift.title, 'owner': owner,
        'owner_id': owner_id, 'owner_username': username,
        'quantity': f'{issued:,}/{total:,} issued'.replace(',', ' '),
        'quantity_issued': issued, 'quantity_total': total,
        'page_scraped_url': f'https://t.me/nft/{gift.slug}',
        'source': 'telegram_api',
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
    for attribute in gift.attributes:
        if isinstance(attribute, types.StarGiftAttributeModel):
            key = 'model'
        elif isinstance(attribute, types.StarGiftAttributeBackdrop):
            key = 'backdrop'
        elif isinstance(attribute, types.StarGiftAttributePattern):
            key = 'symbol'
        else:
            continue
        record[key], record[key + '_name'], record[key + '_rarity_percent'] = attribute_data(attribute)
    missing = [key for key in ('model', 'backdrop', 'symbol') if not record.get(key)]
    if missing:
        raise ValueError(tr('Неполные атрибуты: ', 'Incomplete attributes: ') + ', '.join(missing))
    return record
