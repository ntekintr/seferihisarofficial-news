import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import publish_automatic, publish_one
from seferihisar.schedule import prepare
from seferihisar.selection import locality


def adapter():
    api = Mock()
    api.enabled.return_value = True
    api.account = '1234'
    api.session.head.return_value = SimpleNamespace(
        status_code=200, headers={'Content-Type': 'image/jpeg'})
    api.container.return_value = 'synthetic-container'
    api.call.return_value = {'id': 'synthetic-media'}
    return api


def assets(store):
    return {p['id']: {fmt: [f"media/{p['id']}/{fmt}-1.jpg"] for fmt in ('feed', 'story')}
            for p in store.posts() if not p.get('publish_format')}


def seed(store, at, cases):
    items = []
    ids = []
    for index, case in enumerate(cases):
        item = {'kind': case.get('kind', 'news'), 'title': case['title'],
                'description': 'Kaynak tarafından yerel duyurunun ayrıntıları kamuoyuyla paylaşıldı.', 'category': case.get('category', 'news'),
                'url': f'https://example.org/{index}', 'sources': [f'https://example.org/{index}'],
                'source_id': f'example-{index}', 'source_name': 'Yerel kaynak'}
        if item['kind'] == 'news':
            item['published_at'] = (at - timedelta(hours=case.get('age', 1))).isoformat()
            if item['category'] in ('outage', 'weather'):
                item['valid_until'] = (at + timedelta(hours=4)).isoformat()
        else:
            start = at + timedelta(hours=case.get('starts', 48))
            item.update(start=start.isoformat(), end=(start + timedelta(hours=2)).isoformat(),
                        time_known=True, status='scheduled', location=case.get('location'),
                        organizer=None, free=None, price=None, currency=None, ticket_url=None)
        items.append(item)
        ids.append(store.upsert(item, at.isoformat())[0])
    prepare(store, at)
    with store.db:
        for post in store.posts():
            if not post.get('item_id'):
                store.db.execute("UPDATE posts SET status='superseded' WHERE id=?", (post['id'],))
                continue
            case = cases[ids.index(post['item_id'])]
            post['due_at'] = (at - timedelta(hours=case.get('waiting', 1))).isoformat()
            store.db.execute('UPDATE posts SET due_at=?,payload=? WHERE id=?',
                             (post['due_at'], json.dumps(post), post['id']))
    return items, ids


@pytest.mark.parametrize('cases,selected', [
    ([{'title': 'Seferihisar kurum toplantısı', 'age': 36, 'waiting': 20},
      {'title': 'Seferihisar yeni hizmet duyurusu', 'age': 1}], 1),
    ([{'title': 'Seferihisar güncel haber', 'age': .5, 'waiting': 20},
      {'title': 'Seferihisar su kesintisi', 'kind': 'event', 'category': 'outage', 'starts': 3}], 1),
    ([{'title': 'Urla konseri uzaktaki tarih', 'kind': 'event', 'category': 'concert', 'starts': 360, 'waiting': 20},
      {'title': 'Urla yarınki tiyatro', 'kind': 'event', 'category': 'theatre', 'starts': 24}], 1),
    ([{'title': 'Urla güncel festival haberi', 'age': .5, 'waiting': 20},
      {'title': 'Seferihisar güncel haber', 'age': 3}], 1),
    ([{'title': 'Seferihisar eski toplantı', 'age': 36, 'waiting': 20},
      {'title': 'Urla bu akşam konser', 'kind': 'event', 'category': 'concert', 'starts': 2}], 1),
    ([{'title': 'Urla altı gün sonraki konser', 'kind': 'event', 'starts': 144, 'waiting': 20},
      {'title': 'Urla iki gün sonraki konser', 'kind': 'event', 'starts': 48}], 1),
    ([{'title': 'Seferihisar sabah haberi', 'age': 12, 'waiting': 20},
      {'title': 'Seferihisar yeni haber', 'age': 1}], 1),
])
def test_automatic_pair_uses_relevance_instead_of_queue_age(store, cases, selected):
    at = parse_date('2026-10-15T12:35:00+03:00')
    _, ids = seed(store, at, cases)
    api = adapter()
    result = publish_automatic(store, at, 'https://example.org/', assets(store), api)
    assert result == {'status': 'complete', 'feed': 'published', 'story': 'published'}
    parent = next(p for p in store.posts() if p['status'] == 'published' and not p.get('publish_format'))
    assert parent['item_id'] == ids[selected]
    child = next(p for p in store.posts() if p['id'] == digest(parent['id'] + ':story:0'))
    assert child['parent_post_id'] == parent['id'] and child['status'] == 'published'
    assert api.container.call_count == 2


def test_priority_never_unblocks_failed_source(store):
    at = parse_date('2026-10-15T12:35:00+03:00')
    _, ids = seed(store, at, [{'title': 'Seferihisar elektrik kesintisi', 'category': 'outage'},
                             {'title': 'Seferihisar kültür haberi'}])
    with store.db:
        store.db.execute('INSERT INTO runs(started_at,finished_at,errors) VALUES(?,?,?)',
                         (at.isoformat(), at.isoformat(), json.dumps([{'source_id': 'example-0', 'code': 'source_timeout'}])))
    api = adapter()
    assert publish_automatic(store, at, 'https://example.org/', assets(store), api)['status'] == 'complete'
    assert all(p['item_id'] == ids[1] for p in store.posts() if p['status'] == 'published')


def test_future_due_service_cannot_jump_its_deadline(store):
    at = parse_date('2026-10-15T12:35:00+03:00')
    _, ids = seed(store, at, [{'title': 'Seferihisar elektrik kesintisi', 'category': 'outage', 'waiting': -2},
                             {'title': 'Seferihisar güncel haber'}])
    assert publish_automatic(store, at, 'https://example.org/', assets(store), adapter())['status'] == 'complete'
    assert all(p['item_id'] == ids[1] for p in store.posts() if p['status'] == 'published')


def test_manual_publish_retains_due_order(store):
    at = parse_date('2026-10-15T12:35:00+03:00')
    _, ids = seed(store, at, [{'title': 'Seferihisar eski haber', 'age': 36, 'waiting': 20},
                             {'title': 'Seferihisar yeni haber'}])
    assert publish_one(store, at, 'https://example.org/', assets(store), adapter=adapter())['status'] == 'published'
    assert next(p for p in store.posts() if p['status'] == 'published')['item_id'] == ids[0]


def test_announced_event_correction_leads_without_rewriting_original_claim(store):
    at = parse_date('2026-10-15T12:35:00+03:00')
    items, ids = seed(store, at, [{'title': 'Seferihisar yeni haber', 'waiting': 20},
                                {'title': 'Seferihisar ay sonu festivali', 'kind': 'event', 'starts': 360}])
    parent = next(p for p in store.posts() if p.get('item_id') == ids[1] and p['kind'] == 'announcement')
    parent['published_at'] = (at - timedelta(days=1)).isoformat()
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",
                         (json.dumps(parent), parent['id']))
    before = store.rows('SELECT * FROM posts WHERE id=?', (parent['id'],))[0]
    store.upsert({**items[1], 'location': 'Seferihisar yeni açıklanan mekân'}, at.isoformat())
    prepare(store, at)
    assert publish_automatic(store, at, 'https://example.org/', assets(store), adapter())['status'] == 'complete'
    assert any(p.get('item_id') == ids[1] and p['revision'] == 2 and p['status'] == 'published'
               for p in store.posts() if not p.get('publish_format'))
    assert store.rows('SELECT * FROM posts WHERE id=?', (parent['id'],))[0] == before


def test_verified_venue_outweighs_brand_or_incidental_district():
    assert locality({'location': 'Urla Kültür Merkezi', 'title': 'Seferihisar ekibinden konser',
                     'source_name': 'Seferihisar Belediyesi'}) == 1
    assert locality({'location': 'Ürkmez kültür salonu', 'title': 'Urla ekibinden konser'}) == 0
    assert locality({'title': 'Yoga', 'source_name': 'SeferihisarOfficial'}) == 2
