"""Reviewed city features: sourced city-history posts and reply-prompt stories.

Owner decision (14 Nov 2026): besides source news, the account shares content that
invites interaction. Every word and photo comes from config/city-features.json,
reviewed copy with cited sources and licensed photos pinned by SHA-256. Nothing is
generated at run time.

One feature per scheduled day. Instagram's API cannot add poll or question
stickers, so stories ask for a reply (replies reach the account as messages).
A claimed entry is never repeated or resent; a publishing/uncertain claim stops
the series until it is resolved, like every other delivery.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

import requests

from .domain import TZ, digest

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / 'config/city-features.json'
PHOTOS = Path(__file__).with_name('assets') / 'city-features'
START = date(2026, 11, 16)
# Monday=0. Feed posts Tuesday and Saturday evening, reply stories Mon/Wed/Fri.
SCHEDULE = {'feed': ((1, 5), time(19, 30)), 'story': ((0, 2, 4), time(20, 30))}
WINDOW = timedelta(hours=3)
LAST_START = time(23, 30)
SIZES = {'feed': (1080, 1350), 'story': (1080, 1920)}
STATES = ('publishing', 'published', 'uncertain')
COLUMNS = ['id', 'format', 'day', 'status', 'claimed_at', 'container_id', 'media_id']
LIMITS = {'title': 90, 'body': 420, 'question': 160, 'label': 24}


def load_bank(path: Path = BANK, photos: Path = PHOTOS) -> dict:
    bank = json.loads(Path(path).read_text(encoding='utf-8'))
    if bank.get('version') != 'city-features-v1' or not isinstance(bank.get('entries'), list):
        raise ValueError('Unsupported city feature bank')
    for key, photo in bank['photos'].items():
        data = (Path(photos) / photo['file']).read_bytes()
        if (not re.fullmatch(r'[a-z0-9-]{3,60}', key) or photo['file'] != key + '.jpg'
                or hashlib.sha256(data).hexdigest() != photo['sha256'] or not photo['author'].strip()
                or not photo['license'] or not photo['source'].startswith('https://commons.wikimedia.org/')):
            raise ValueError('City feature photo does not match its reviewed record')
    seen = set()
    for entry in bank['entries']:
        if (not re.fullmatch(r'[a-z0-9-]{3,60}', entry.get('id', '')) or entry['id'] in seen
                or entry.get('format') not in SCHEDULE or entry.get('photo') not in bank['photos']):
            raise ValueError('Invalid city feature entry')
        seen.add(entry['id'])
        for field, limit in LIMITS.items():
            if field in entry and (not isinstance(entry[field], str) or not entry[field].strip() or len(entry[field]) > limit):
                raise ValueError('City feature text exceeds its reviewed length')
        if entry['format'] == 'feed' and (not entry.get('question') or not entry.get('sources') or not all(
                s['url'].startswith('https://') and s['name'].strip() for s in entry['sources'])):
            raise ValueError('A city history post needs a question and a cited source')
    return bank


def scheduled_format(day: date) -> str | None:
    if day < START:
        return None
    return next((fmt for fmt, (days, _) in SCHEDULE.items() if day.weekday() in days), None)


def window(day: date, fmt: str) -> tuple[datetime, datetime]:
    start = datetime.combine(day, SCHEDULE[fmt][1], TZ)
    return start, min(start + WINDOW, datetime.combine(day, LAST_START, TZ))


def rows(store) -> list[dict]:
    return store.rows('SELECT * FROM city_features ORDER BY claimed_at')


def planned(store, day: date, bank: dict) -> tuple[dict, dict | None] | None:
    """Today's entry: the claimed one, else the first never-claimed entry of the format."""
    fmt = scheduled_format(day)
    if not fmt:
        return None
    claimed = rows(store)
    today = next((r for r in claimed if r['day'] == day.isoformat() and r['format'] == fmt), None)
    if today:
        entry = next((e for e in bank['entries'] if e['id'] == today['id']), None)
        return (entry, today) if entry else None
    used = {r['id'] for r in claimed}
    entry = next((e for e in bank['entries'] if e['format'] == fmt and e['id'] not in used), None)
    return (entry, None) if entry else None


def asset_id(entry: dict, bank: dict) -> str:
    copy = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    return digest('city:' + bank['version'] + ':' + copy + ':' + bank['photos'][entry['photo']]['sha256'])


def asset_path(entry: dict, bank: dict) -> str:
    return f"media/{asset_id(entry, bank)}/{entry['format']}-1.jpg"


def caption(entry: dict, bank: dict) -> str:
    photo = bank['photos'][entry['photo']]
    sources = '\n'.join(f"Kaynak: {s['name']}\n{s['url']}" for s in entry['sources'])
    licence = photo['license'] + (f" ({photo['license_url']})" if photo.get('license_url') else '')
    share_alike = ' Kart aynı lisansla paylaşılır.' if 'SA' in photo['license'] else ''
    return (f"{entry['title']}\n\n{entry['body']}\n\n{entry['question']}\n\n"
            f"Fotoğraf: {photo['author']}, Wikimedia Commons, {licence}; kırpılarak kullanıldı.{share_alike}\n"
            f"{sources}\n\n" + ' '.join(entry['hashtags']))


def export(store, public_dir: Path, at: datetime, bank: dict | None = None) -> dict | None:
    """Render today's entry so Pages serves it hours before its slot."""
    at = at.astimezone(TZ)
    bank = bank or load_bank()
    plan = planned(store, at.date(), bank)
    if not plan:
        return None
    entry, row = plan
    start, end = window(at.date(), entry['format'])
    result = {'day': at.date().isoformat(), 'format': entry['format'], 'id': entry['id'],
              'status': row['status'] if row else 'planned', 'window_start': start.isoformat(),
              'window_end': end.isoformat()}
    from .city_render import render
    from .text_quality import TextRenderError
    path = asset_path(entry, bank)
    try:
        render(entry, bank['photos'][entry['photo']], PHOTOS / bank['photos'][entry['photo']]['file'], Path(public_dir) / path)
    except (TextRenderError, OSError):
        return dict(result, status='unrenderable')
    result.update(asset=path, sha256={path: hashlib.sha256((Path(public_dir) / path).read_bytes()).hexdigest()})
    return result


def _deployed(api, site: str, expected: dict, size: tuple[int, int]) -> str | None:
    try:
        response = api.session.get(site + '/data.json', timeout=(8, 20), allow_redirects=False)
        if response.status_code != 200 or len(response.content) > 8_000_000:
            return None
        deployed = response.json().get('city_feature') or {}
        if any(deployed.get(k) != v for k, v in expected.items()):
            return None
        sha = deployed.get('sha256', {}).get(expected['asset'])
        if set(deployed.get('sha256', {})) != {expected['asset']} or not re.fullmatch(r'[a-f0-9]{64}', sha or ''):
            return None
        url = site + '/' + expected['asset']
        image = api.session.get(url, timeout=(8, 20), allow_redirects=False)
        if (image.status_code != 200 or not image.headers.get('Content-Type', '').startswith('image/jpeg')
                or len(image.content) > 6_000_000 or hashlib.sha256(image.content).hexdigest() != sha):
            return None
        from PIL import Image
        with Image.open(BytesIO(image.content)) as jpeg:
            if jpeg.format != 'JPEG' or jpeg.size != size:
                return None
            jpeg.verify()
        return url
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, OSError):
        return None


# Owner decision, 14 Nov 2026. Set False to pause the series without a state edit.
ENABLED = True


def _profile_enabled() -> bool:
    return ENABLED


def publish(store, at: datetime, site_url: str, adapter=None, checkpoint=None, bank: dict | None = None) -> dict:
    at = at.astimezone(TZ)
    day = at.date()
    fmt = scheduled_format(day)
    if not fmt:
        return {'status': 'not_scheduled'}
    start, end = window(day, fmt)
    if not start <= at < end:
        return {'status': 'outside_window'}
    if checkpoint is None or not _profile_enabled():
        return {'status': 'disabled'}
    from .weather_data import SITE
    if site_url.rstrip('/') != SITE:
        raise ValueError('Unexpected Seferihisar city feature media site')
    claimed = rows(store)
    if any(r['status'] in ('publishing', 'uncertain') for r in claimed):
        return {'status': 'awaiting_resolution'}
    if any(r['day'] == day.isoformat() and r['format'] == fmt for r in claimed):
        return {'status': 'already_published'}
    try:
        bank = bank or load_bank()
    except (ValueError, KeyError, TypeError, OSError):
        return {'status': 'bank_invalid'}
    plan = planned(store, day, bank)
    if not plan:
        return {'status': 'bank_empty'}
    entry = plan[0]
    from .instagram import Instagram
    api = adapter or Instagram()
    if not api.enabled():
        return {'status': 'disabled'}
    expected = {'day': day.isoformat(), 'format': fmt, 'id': entry['id'], 'status': 'planned',
                'asset': asset_path(entry, bank)}
    url = _deployed(api, SITE, expected, SIZES[fmt])
    if not url:
        return {'status': 'media_not_deployed'}
    from .pharmacy import account_matches
    try:
        if not account_matches(api):
            return {'status': 'account_mismatch'}
    except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError):
        return {'status': 'account_mismatch'}
    with store.db:
        changed = store.db.execute("INSERT OR IGNORE INTO city_features(id,format,day,status,claimed_at) "
                                   "VALUES(?,?,?,'publishing',?)", (entry['id'], fmt, day.isoformat(), at.isoformat()))
    if changed.rowcount != 1:
        return {'status': 'awaiting_resolution'}
    checkpoint()  # Durable claim before the first Meta mutation.
    try:
        container = api.container([url], '' if fmt == 'story' else caption(entry, bank), fmt == 'story')
        if not isinstance(container, str) or not re.fullmatch(r'\d{1,32}', container):
            raise ValueError('Invalid city feature container identity')
        with store.db:
            store.db.execute('UPDATE city_features SET container_id=? WHERE id=?', (container, entry['id']))
        checkpoint()
        api.wait(container)
        media = api.call(f'{api.account}/media_publish', creation_id=container)['id']
        if not isinstance(media, str) or not re.fullmatch(r'\d{1,32}', media):
            raise ValueError('Invalid city feature media identity')
        with store.db:
            store.db.execute("UPDATE city_features SET status='published',media_id=? WHERE id=?", (media, entry['id']))
        checkpoint()
        return {'status': 'published', 'id': entry['id'], 'format': fmt}
    except (requests.RequestException, RuntimeError, KeyError, ValueError, TypeError):
        with store.db:
            store.db.execute("UPDATE city_features SET status='uncertain' WHERE id=?", (entry['id'],))
        checkpoint()
        return {'status': 'uncertain', 'id': entry['id'], 'format': fmt}


def validate_row(row) -> None:
    key, fmt, day, status, claimed_at, container, media = row
    if (not re.fullmatch(r'[a-z0-9-]{3,60}', str(key)) or fmt not in SCHEDULE or status not in STATES
            or date.fromisoformat(day).isoformat() != day or datetime.fromisoformat(claimed_at).tzinfo is None
            or (container is not None and not re.fullmatch(r'\d{1,32}', container))
            or (media is not None and not re.fullmatch(r'\d{1,32}', media))
            or (status == 'published' and not media)):
        raise ValueError('Invalid city feature record')
