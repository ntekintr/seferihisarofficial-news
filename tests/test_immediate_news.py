"""Owner decision, 14 Nov 2026 (both factories, from 15 Nov).

No daily publication cap. Current news goes out in the run that finds it,
with its own story, instead of waiting for a timetable slot.
"""
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import publish_automatic
from seferihisar.publication_policy import daily_limit_reason, immediate_news_item
from seferihisar.schedule import prepare
from seferihisar.security import validate_state

SITE = 'https://example.org/'


def api():
    result = Mock()
    result.enabled.return_value = True
    result.account = '1234'
    result.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    result.container.return_value = 'container'
    result.call.return_value = {'id': 'media'}
    return result


def news(store, at, name, *, seen=None, published=None):
    seen = seen or at
    item = {'kind': 'news', 'title': 'Seferihisar kültür duyurusu ' + name,
            'description': 'Kaynak tarafından yerel kültür haberinin ayrıntıları duyuruldu ' + name + '.',
            'url': 'https://example.org/news/' + name, 'sources': ['https://example.org/news/' + name],
            'source_id': 'example', 'source_name': 'Yerel kaynak', 'category': 'culture',
            'published_at': (published or seen - timedelta(minutes=20)).isoformat()}
    store.upsert(item, seen.isoformat())
    prepare(store, seen)
    return {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"],
                      'story': [f"media/{p['id']}/story-1.jpg"]}
            for p in store.posts() if not p.get('publish_format')}


def clock(at):
    ticks = iter(at + timedelta(seconds=90 * n) for n in range(1, 50))
    return lambda: next(ticks)


def feeds(store, status='published'):
    return [p for p in store.posts() if not p.get('publish_format') and p['status'] == status]


def test_five_new_articles_go_out_at_once_without_waiting_for_a_slot(store):
    # 10:05 is outside every timetable window.
    at = parse_date('2026-11-15T10:05:00+03:00')
    assets = {}
    for name in 'abcde':
        assets.update(news(store, at, name))
    adapter, pause = api(), Mock()
    result = publish_automatic(store, at, SITE, assets, adapter, clock=clock(at), pause=pause)
    assert result == {'status': 'outside_window', 'immediate': 'published'}
    # One run publishes four pairs, 90 seconds apart; the fifth follows next run.
    assert len(feeds(store)) == 4 and adapter.container.call_count == 8
    assert [c.args for c in pause.call_args_list] == [(90,)] * 3
    for parent in feeds(store):
        child = next(p for p in store.posts() if p['id'] == digest(parent['id'] + ':story:0'))
        assert parent['immediate'] is True and child['status'] == 'published'
    later = at + timedelta(minutes=15)
    assert publish_automatic(store, later, SITE, assets, adapter, clock=clock(later), pause=Mock())['immediate'] == 'published'
    assert len(feeds(store)) == 5 and adapter.container.call_count == 10
    validate_state(store.path)


def test_there_is_no_daily_cap_any_more(store):
    at = parse_date('2026-11-15T19:40:00+03:00')
    assets = {}
    for name in 'abcd':
        assets.update(news(store, at - timedelta(hours=10), 'old' + name))
    for post, stamp in zip(feeds(store, 'prepared'), ('08:35', '12:35', '15:10', '18:35')):
        payload = {**post, 'published_at': parse_date('2026-11-15T' + stamp + ':00+03:00').isoformat()}
        with store.db:
            store.db.execute("UPDATE posts SET payload=?,status='published' WHERE id=?", (json.dumps(payload), post['id']))
    assert daily_limit_reason(store, at) is None
    assets.update(news(store, at, 'new'))
    adapter = api()
    assert publish_automatic(store, at, SITE, assets, adapter, clock=clock(at), pause=Mock())['immediate'] == 'published'
    assert adapter.container.call_count == 2


def test_an_old_backlog_is_not_dumped(store):
    at = parse_date('2026-11-15T10:05:00+03:00')
    assets = news(store, at, 'seen-yesterday-evening', seen=at - timedelta(hours=9))
    assets.update(news(store, at, 'dated-two-days-ago', published=at - timedelta(hours=30)))
    adapter = api()
    assert publish_automatic(store, at, SITE, assets, adapter, clock=clock(at), pause=Mock())['immediate'] == 'empty'
    adapter.container.assert_not_called()


def test_night_hours_and_days_before_the_decision_keep_the_old_rule(store):
    night = parse_date('2026-11-15T06:40:00+03:00')
    assets = news(store, night, 'night')
    adapter = api()
    assert publish_automatic(store, night, SITE, assets, adapter, clock=clock(night), pause=Mock())['immediate'] == 'empty'
    before = parse_date('2026-11-14T10:05:00+03:00')
    assert publish_automatic(store, before, SITE, assets, adapter) == {'status': 'outside_window'}
    adapter.container.assert_not_called()
    item = store.items('news')[0]
    assert immediate_news_item(item, parse_date('2026-11-15T07:00:00+03:00'))
    assert not immediate_news_item(item, parse_date('2026-11-15T23:30:00+03:00'))


def test_an_uncertain_delivery_stops_the_run_and_is_never_resent(store):
    at = parse_date('2026-11-15T10:05:00+03:00')
    assets = news(store, at, 'a')
    assets.update(news(store, at, 'b'))
    adapter = api()
    adapter.call.side_effect = RuntimeError('provider details')
    result = publish_automatic(store, at, SITE, assets, adapter, clock=clock(at), pause=Mock())
    assert result['immediate'] == 'uncertain' and adapter.container.call_count == 1
    first = feeds(store, 'uncertain')[0]['id']
    later = at + timedelta(minutes=15)
    publish_automatic(store, later, SITE, assets, adapter, clock=clock(later), pause=Mock())
    # The next run tries the other article once; the uncertain one is never resent.
    assert adapter.container.call_count == 2
    assert {p['id'] for p in feeds(store, 'uncertain')} - {first} != set()


def test_a_post_published_at_once_does_not_take_a_timetable_slot(store):
    at = parse_date('2026-11-15T12:35:00+03:00')
    assets = news(store, at, 'fresh')
    adapter = api()
    result = publish_automatic(store, at, SITE, assets, adapter, clock=clock(at), pause=Mock())
    # The window has no claim of its own (no "awaiting_resolution" or story
    # retry for it); timetabled content keeps its 45-minute gap after news.
    assert result == {'status': 'rate_limited', 'immediate': 'published'}
    later = at + timedelta(minutes=50)
    assert publish_automatic(store, later, SITE, assets, adapter, clock=clock(later), pause=Mock()) == {
        'status': 'empty', 'immediate': 'empty'}


def mirrored_parent(store, at, name):
    item = {'kind': 'news', 'title': 'Seferihisar kültür duyurusu ' + name,
            'description': 'Kaynak tarafından yerel kültür haberinin ayrıntıları duyuruldu ' + name + '.',
            'url': 'https://example.org/news/' + name, 'sources': ['https://example.org/news/' + name],
            'source_id': 'example', 'source_name': 'Yerel kaynak', 'category': 'culture',
            'published_at': (at - timedelta(minutes=20)).isoformat()}
    item_id, _ = store.upsert(item, at.isoformat())
    key = digest('facebook-immediate-' + name)
    parent = {'id': key, 'item_id': item_id, 'revision': 1, 'kind': 'news', 'due_at': at.isoformat(),
              'title': item['title'], 'caption': 'Haber metni. Kaynak: ' + item['url'],
              'source_urls': item['sources'], 'created_at': at.isoformat(), 'category': 'culture',
              'published_at': (at - timedelta(minutes=5)).isoformat(), 'immediate': True}
    store.queue(parent)
    store.queue({**parent, 'id': digest(key + ':story:0'), 'parent_post_id': key, 'publish_format': 'story',
                 'story_index': 0, 'story_asset': f'media/{key}/story-1.jpg'})
    with store.db:
        store.db.execute("UPDATE posts SET status='published',media_id='7890'")
    return {key: {'feed': [f'media/{key}/feed-1.jpg'], 'story': [f'media/{key}/story-1.jpg']}}


def test_every_article_published_at_once_is_mirrored_to_facebook_in_the_same_run(store):
    from seferihisar.facebook import publish_recent
    at = parse_date('2026-11-15T10:10:00+03:00')
    assets = mirrored_parent(store, at, 'a')
    assets.update(mirrored_parent(store, at, 'b'))
    page = Mock()
    page.enabled.return_value = True
    page.check_identity.return_value = True
    page.page = '1303548319516253'
    page.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    page.upload.return_value = '12345'
    page.publish.side_effect = lambda *args: 'media'
    assert publish_recent(store, at, SITE, assets, page)['status'] == 'complete'
    # Two feeds and two stories, and no daily cap stops the second pair.
    assert page.publish.call_count == 4
    rows = store.rows("SELECT post_id,format,status FROM facebook_deliveries")
    assert len(rows) == 4 and all(r['status'] == 'published' for r in rows)