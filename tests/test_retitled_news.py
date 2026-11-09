"""9 Nov 2026: a retitled source article must not go out a second time."""
import json
from datetime import timedelta

from seferihisar.domain import parse_date
from seferihisar.instagram import publish_automatic
from seferihisar.publication_policy import duplicate_reason
from seferihisar.schedule import prepare
from test_automatic_publication import api, news


def assets(store):
    return {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"],
                      'story': [f"media/{p['id']}/story-1.jpg", f"media/{p['id']}/story-2.jpg"]}
            for p in store.posts() if not p.get('publish_format')}


def due_now(store, at):
    with store.db:
        for row in store.rows("SELECT id,payload FROM posts WHERE status='prepared'"):
            payload = json.loads(row['payload'])
            payload['due_at'] = (at - timedelta(minutes=10)).isoformat()
            store.db.execute('UPDATE posts SET due_at=?,payload=? WHERE id=?',
                             (payload['due_at'], json.dumps(payload), row['id']))


def test_retitled_article_is_not_published_again_next_morning(store):
    at = parse_date('2026-11-08T15:00:00+03:00')
    news(store, at, 'taekwondo')
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', assets(store), adapter)['status'] == 'complete'
    sent = adapter.container.call_count
    assert sent == 2  # feed + first story

    item = store.items()[0]
    original = {k: item[k] for k in ('kind', 'title', 'description', 'url', 'sources', 'source_id',
                                     'source_name', 'category', 'published_at')}
    morning = parse_date('2026-11-09T08:32:00+03:00')
    store.upsert({**original, 'title': 'Seferihisar’da tekvando rüzgarı'}, morning.isoformat())
    assert store.items()[0]['revision'] == 2
    prepare(store, morning)
    due_now(store, morning)
    revised = [p for p in store.posts() if p.get('revision') == 2 and not p.get('publish_format')]
    assert revised and all(p['status'] != 'prepared' or duplicate_reason(store, p) == 'duplicate_story' for p in revised)

    result = publish_automatic(store, morning, 'https://example.org/', assets(store), adapter)
    assert result['status'] != 'complete' or result.get('feed') != 'published'
    assert adapter.container.call_count == sent
    claimed = [p for p in store.posts() if p['status'] in ('publishing', 'published', 'uncertain')]
    assert {p['revision'] for p in claimed} == {1}


def test_unpublished_revision_still_replaces_the_waiting_card(store):
    at = parse_date('2026-11-08T15:00:00+03:00')
    news(store, at, 'kultur')
    item = store.items()[0]
    original = {k: item[k] for k in ('kind', 'title', 'description', 'url', 'sources', 'source_id',
                                     'source_name', 'category', 'published_at')}
    later = at + timedelta(minutes=30)
    store.upsert({**original, 'title': 'Seferihisar kültür duyurusu güncellendi'}, later.isoformat())
    prepare(store, later)
    due_now(store, later)
    revised = next(p for p in store.posts() if p.get('revision') == 2 and not p.get('publish_format'))
    assert duplicate_reason(store, revised) is None
    adapter = api()
    assert publish_automatic(store, later, 'https://example.org/', assets(store), adapter)['feed'] == 'published'
    claimed = [p for p in store.posts() if p['status'] == 'published' and not p.get('publish_format')]
    assert [p['revision'] for p in claimed] == [2]


def test_a_different_article_from_the_same_source_still_publishes(store):
    at = parse_date('2026-11-08T15:00:00+03:00')
    news(store, at, 'birinci')
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', assets(store), adapter)['status'] == 'complete'
    later = parse_date('2026-11-09T08:32:00+03:00')
    news(store, later, 'ikinci')
    assert publish_automatic(store, later, 'https://example.org/', assets(store), adapter)['feed'] == 'published'
