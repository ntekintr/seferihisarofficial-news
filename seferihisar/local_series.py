"""Small, source-bound local guides inside the existing two-feed daily budget."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .domain import TZ, digest, parse_date

KINDS = ('weekend', 'free_week')


def edition(kind, at):
    monday = at.date() - timedelta(days=at.weekday())
    if kind == 'weekend':
        due = datetime.combine(monday + timedelta(days=4), time(12, 30), TZ)
        start = datetime.combine(monday + timedelta(days=5), time(), TZ)
        end = start + timedelta(days=2)
        title = 'Seferihisar ve çevresinde bu hafta sonu'
        active = at.weekday() in (3, 4, 5)
    else:
        due = datetime.combine(monday + timedelta(days=1), time(12, 30), TZ)
        start, end = due.replace(hour=0, minute=0), due.replace(hour=0, minute=0) + timedelta(days=7)
        title = 'Yakınında ücretsiz etkinlikler'
        active = at.weekday() in (0, 1, 2)
    return {'key': digest(kind + ':' + monday.isoformat()), 'due': due, 'start': start,
            'end': end, 'title': title, 'active': active, 'expires': due + timedelta(hours=25)}


def expired(post, at):
    return post.get('kind') in KINDS and at >= parse_date(post['due_at']) + timedelta(hours=25)


def current_copy(post, items):
    from .editor import event_title
    from .schedule import slide_body
    urls, slides = post.get('source_urls', []), post.get('slides', [])
    if not 2 <= len(urls) <= 4 or len(slides) != len(urls) + 1:
        return False
    period = edition(post['kind'], parse_date(post['due_at']))
    for index, url in enumerate(urls, 1):
        item = next((i for i in items.values() if i.get('url') == url and i.get('kind') == 'event'), None)
        if (not item or item.get('status') not in ('scheduled', 'rescheduled')
                or not period['start'] <= parse_date(item['start']) < period['end']
                or (post['kind'] == 'free_week' and item.get('free') is not True)
                or slides[index] != {'title': event_title(item), 'body': slide_body(item), 'category': item['category']}
                or url not in post.get('caption', '')):
            return False
    return True


def prepare(store, at):
    import json
    from .editor import caption_with_hashtags, digest_hashtags, event_title, event_date_label, excerpt, plain_source_text
    from .schedule import blocked_sources, source_current, slide_body
    failed = blocked_sources(store)
    for kind in KINDS:
        period = edition(kind, at)
        key = period['key']
        old = next((p for p in store.posts() if p['id'] == key), None)
        if old and old['status'] not in ('prepared', 'blocked_source'):
            continue
        if not period['active'] or at >= period['expires']:
            continue
        candidates = [item for item in store.items('event')
            if item.get('status') in ('scheduled', 'rescheduled') and item.get('category') != 'outage'
            and period['start'] <= parse_date(item['start']) < period['end']
            and source_current(item, at, failed) and (kind != 'free_week' or item.get('free') is True)]
        from .selection import locality
        selected = sorted(candidates, key=lambda e: (locality(e), e['start'], e['id']))[:4]
        if len(selected) < 2:
            if old:
                store.db.execute("UPDATE posts SET status='blocked_source' WHERE id=? AND status IN ('prepared','blocked_source')", (key,))
                store.db.commit()
            continue
        footer = '\n\n'.join('Kaynak: ' + plain_source_text(e['source_name']) + '\n' + e['url'] for e in selected)
        while len(footer) > 1300 and len(selected) >= 2:
            selected.pop()
            footer = '\n\n'.join('Kaynak: ' + plain_source_text(e['source_name']) + '\n' + e['url'] for e in selected)
        if len(selected) < 2:
            continue
        label = period['start'].strftime('%d.%m.%Y') + ' – ' + (period['end'] - timedelta(days=1)).strftime('%d.%m.%Y')
        cover = label + '\n\n' + '\n\n'.join(excerpt(event_title(e), 75) + '\n' + event_date_label(e, include_time=False) for e in selected[:3])
        lines = [period['title'], label + ' için doğrulanmış ' + str(len(selected)) + ' etkinlikten seçki.']
        lines += [event_title(e) + '\n' + slide_body(e) for e in selected]
        post = {'id': key, 'kind': kind, 'revision': 1, 'due_at': period['due'].isoformat(),
                'title': period['title'], 'caption': caption_with_hashtags('\n\n'.join(lines), digest_hashtags(selected), footer=footer),
                'category': 'event', 'source_urls': [e['url'] for e in selected],
                'created_at': at.isoformat(), 'formats': ['carousel', 'story'],
                'slides': [{'title': period['title'], 'body': cover}] +
                          [{'title': event_title(e), 'body': slide_body(e), 'category': e['category']} for e in selected]}
        if not old:
            store.queue(post)
        else:
            # Rebuild only an unclaimed edition. Frozen claims keep all bytes and fields.
            with store.db:
                store.db.execute("UPDATE posts SET payload=?,status='prepared' WHERE id=? AND status IN ('prepared','blocked_source')",
                                 (json.dumps(post, ensure_ascii=False), key))


def summary(at):
    return {'version': 'local-series-v1', 'daily_feed_limit_shared': True,
            'series': [{'kind': kind, 'target_weekday': 'Friday' if kind == 'weekend' else 'Tuesday',
                        'target_time': '12:30', 'minimum_verified_events': 2, 'maximum_events': 4,
                        'priority_below_urgent_corrections': True} for kind in KINDS]}
