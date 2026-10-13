import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seferihisar.domain import parse_date
from seferihisar.instagram import publish_automatic
from seferihisar.schedule import prepare


def seed_event(store, at):
    date = at + timedelta(days=2)
    item = {'kind': 'event', 'title': 'Ürkmez Kültür ve Sanat Festivali',
            'description': 'Ürkmez için doğrulanmış festival duyurusu.', 'category': 'festival',
            'url': 'https://example.org/urkmez', 'sources': ['https://example.org/urkmez'],
            'source_id': 'example', 'source_name': 'Yerel kaynak',
            'start': date.replace(hour=0, minute=0, second=0).isoformat(),
            'end': date.replace(hour=0, minute=0, second=0).isoformat(),
            'time_known': False, 'status': 'scheduled', 'location': None, 'organizer': None,
            'free': None, 'price': None, 'currency': None, 'ticket_url': None, 'previous_start': None}
    key, _ = store.upsert(item, at.isoformat())
    prepare(store, at)
    # Isolate individual-event selection from independent calendar editions.
    with store.db:
        store.db.execute("UPDATE posts SET status='superseded' WHERE kind IN ('weekly','monthly')")
    assets = {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"],
                         'story': [f"media/{p['id']}/story-1.jpg"]} for p in store.posts()}
    return item, key, assets


def adapter():
    result = Mock()
    result.enabled.return_value = True
    result.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    result.container.return_value = 'container'
    result.call.return_value = {'id': 'published-media'}
    return result


@pytest.mark.parametrize('claim_status', ['published', 'uncertain', 'publishing'])
def test_same_event_reminder_does_not_take_second_daily_slot(store, claim_status):
    morning = parse_date('2026-10-13T08:35:00+03:00')
    item, _, assets = seed_event(store, morning)
    first = next(p for p in store.posts() if p['kind'] == 'announcement')
    with store.db:
        store.db.execute('UPDATE posts SET status=?,payload=? WHERE id=?',
                         (claim_status, json.dumps({**first, 'published_at': morning.isoformat()}), first['id']))
    afternoon = parse_date('2026-10-13T12:35:00+03:00')
    store.upsert(item, afternoon.isoformat())
    api = adapter()
    assert publish_automatic(store, afternoon, 'https://example.org/', assets, api)['status'] == 'empty'
    api.container.assert_not_called()


def test_source_correction_stays_eligible_for_same_event(store):
    morning = parse_date('2026-10-13T08:35:00+03:00')
    item, _, assets = seed_event(store, morning)
    first = next(p for p in store.posts() if p['kind'] == 'announcement')
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",
                         (json.dumps({**first, 'published_at': morning.isoformat()}), first['id']))
    afternoon = parse_date('2026-10-13T12:35:00+03:00')
    store.upsert({**item, 'location': 'Ürkmez meydanı — yeni açıklanan mekân'}, afternoon.isoformat())
    prepare(store, afternoon)
    update = next(p for p in store.posts() if p['kind'] == 'update')
    assets[update['id']] = {'feed': [f"media/{update['id']}/feed-1.jpg"],
                            'story': [f"media/{update['id']}/story-1.jpg"]}
    api = adapter()
    result = publish_automatic(store, afternoon, 'https://example.org/', assets, api)
    assert result == {'status': 'complete', 'feed': 'published', 'story': 'published'}
    assert api.container.call_count == 2
