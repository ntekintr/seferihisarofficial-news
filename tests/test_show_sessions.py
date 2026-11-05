"""Sessions of one show on one day reach followers as one card (5 Nov 2026)."""
import json

from seferihisar.domain import parse_date
from seferihisar.quality import publication_copy_reason
from seferihisar.schedule import prepare, queue_item, session_card
from seferihisar.security import validate_state

URL = 'https://biletinial.com/tr-tr/tiyatro/mavis-baba-kelebek-avcisi'
VENUE = 'Seferihisar Çağan Irmak Kültür Merkezi'


def session(start, *, venue=VENUE, url=URL):
    begin = parse_date(start)
    return {'kind': 'event', 'title': 'Mavişehir Baba Kelebek Avcısı', 'category': 'festival',
            'description': 'Çocuklar için tiyatro oyunu.', 'url': url, 'sources': [url],
            'identity': url + '#session-' + start, 'source_id': 'biletinial', 'source_name': 'Biletinial',
            'start': begin.isoformat(), 'end': begin.replace(minute=45).isoformat(), 'time_known': True,
            'status': 'scheduled', 'location': venue, 'organizer': 'FRK Organizasyon', 'free': None,
            'price': '448.0', 'currency': 'TRY', 'ticket_url': url, 'previous_start': None}


def seed(store, at, *starts, **changes):
    keys = [store.upsert(session(start, **changes), at.isoformat())[0] for start in starts]
    prepare(store, at)
    return keys


def live(store, kind):
    return [p for p in store.posts() if p['kind'] == kind and not p.get('publish_format')
            and p['status'] in ('prepared', 'blocked_source')]


def test_two_sessions_same_day_make_one_announcement_naming_both(store):
    at = parse_date('2026-11-05T08:35:00+03:00')
    early, late = seed(store, at, '2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00')
    [card] = live(store, 'announcement')
    assert card['item_id'] == early and card['session_ids'] == [early, late]
    assert 'Seanslar 15:30 ve 19:00' in card['slides'][0]['body']
    assert 'Seanslar 15:30 ve 19:00' in card['caption']
    items = {i['id']: i for i in store.items()}
    assert publication_copy_reason(card, items) is None
    validate_state(store.path)


def test_reminders_follow_the_same_single_card(store):
    at = parse_date('2026-11-05T08:35:00+03:00')
    early, late = seed(store, at, '2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00')
    [card] = live(store, 'announcement')
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",
                         (json.dumps({**card, 'published_at': at.isoformat()}), card['id']))
    three_days = parse_date('2026-11-09T08:35:00+03:00')
    for start in ('2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00'):
        store.upsert(session(start), three_days.isoformat())
    prepare(store, three_days)
    assert live(store, 'announcement') == []
    [reminder] = live(store, 'reminder_3d')
    assert reminder['item_id'] == early and 'Seanslar 15:30 ve 19:00' in reminder['slides'][0]['body']


def test_later_session_does_not_repeat_after_first_one_started(store):
    """Once the 15:30 session is under way, the 19:00 one must not reannounce the show."""
    at = parse_date('2026-11-12T08:35:00+03:00')
    early, late = seed(store, at, '2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00')
    [day] = live(store, 'reminder_day')
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",
                         (json.dumps({**day, 'published_at': at.isoformat()}), day['id']))
    evening = parse_date('2026-11-12T16:00:00+03:00')
    store.upsert(session('2026-11-12T19:00:00+03:00'), evening.isoformat())
    prepare(store, evening)
    assert live(store, 'reminder_day') == []


def test_card_already_queued_for_later_session_is_superseded(store):
    """Cards created before this rule must not reach followers either."""
    at = parse_date('2026-11-05T08:35:00+03:00')
    late_key, _ = store.upsert(session('2026-11-12T19:00:00+03:00'), at.isoformat())
    late = next(i for i in store.items() if i['id'] == late_key)
    queue_item(store, late, 'announcement', at, at)
    seed(store, at, '2026-11-12T15:30:00+03:00')
    statuses = {p['item_id']: p['status'] for p in store.posts() if p['kind'] == 'announcement' and not p.get('publish_format')}
    assert statuses[late_key] == 'superseded'
    assert sum(s in ('prepared', 'blocked_source') for s in statuses.values()) == 1


def test_other_days_and_other_venues_stay_separate(store):
    at = parse_date('2026-11-05T08:35:00+03:00')
    seed(store, at, '2026-11-12T15:30:00+03:00', '2026-11-19T15:30:00+03:00')
    seed(store, at, '2026-11-12T19:00:00+03:00', venue='Bademler Sanat Köyü')
    cards = live(store, 'announcement')
    assert len(cards) == 3 and not any(c.get('session_ids') for c in cards)


def test_session_missing_from_latest_reading_is_not_named(store):
    """A record the source just dropped must not put a wrong time on the card."""
    first = parse_date('2026-11-05T08:35:00+03:00')
    seed(store, first, '2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00')
    later = parse_date('2026-11-05T09:05:00+03:00')
    [early] = seed(store, later, '2026-11-12T15:30:00+03:00')
    [card] = live(store, 'announcement')
    assert card['item_id'] == early and 'session_ids' not in card
    assert 'Seanslar' not in card['slides'][0]['body'] and '15:30' in card['slides'][0]['body']
    items = {i['id']: i for i in store.items()}
    stale = {**card, 'session_ids': [early, next(k for k in items if k != early)]}
    assert session_card(items[early], stale, items) is None


def test_card_naming_a_vanished_session_is_not_current(store):
    at = parse_date('2026-11-05T08:35:00+03:00')
    early, late = seed(store, at, '2026-11-12T15:30:00+03:00', '2026-11-12T19:00:00+03:00')
    [card] = live(store, 'announcement')
    items = {i['id']: i for i in store.items()}
    assert session_card(items[early], card, items)['session_times'] == ['15:30', '19:00']
    del items[late]
    assert session_card(items[early], card, items) is None
    assert publication_copy_reason(card, items) == 'event_metadata_stale'
