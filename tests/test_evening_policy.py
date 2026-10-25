"""Fresh evening news may use one extra pair; old queues never gain a slot."""
import json
from datetime import timedelta

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import publish_automatic, publish_one
from seferihisar.publication_policy import (daily_limit_reason, dispatch_window,
                                           evening_news_item, evening_post)
from seferihisar.schedule import SLOTS, prepare
from seferihisar.store import Store
from test_automatic_publication import api, claim


def add_news(store, at, label, published=None):
    url = 'https://example.org/news/' + label
    key, _ = store.upsert({'kind': 'news', 'title': 'Seferihisar yerel kültür haberi ' + label,
        'description': 'Seferihisar için yerel kültür haberinin doğrulanmış ayrıntıları açıklandı.',
        'url': url, 'sources': [url], 'source_id': 'example', 'source_name': 'Yerel kaynak',
        'category': 'culture', 'published_at': (published or at - timedelta(minutes=5)).isoformat()}, at.isoformat())
    prepare(store, at)
    return next(p for p in store.posts() if p.get('item_id') == key and not p.get('publish_format'))


def asset_map(store):
    return {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"],
                      'story': [f"media/{p['id']}/story-1.jpg"]}
            for p in store.posts() if not p.get('publish_format')}


def pair_claim(store, parent, stamp, status='published'):
    claim(store, parent, stamp, status)
    child = {**parent, 'id': digest(parent['id'] + ':story:0'), 'publish_format': 'story',
             'parent_post_id': parent['id'], 'story_index': 0,
             'story_asset': f"media/{parent['id']}/story-1.jpg"}
    store.queue(child)
    claim(store, child, stamp, status)


def three_pairs(store, at, third='18:35'):
    for index, clock in enumerate(('08:35', '12:35', third)):
        stamp = parse_date(at.date().isoformat() + 'T' + clock + ':00+03:00')
        parent = add_news(store, stamp - timedelta(minutes=5), 'base' + str(index))
        pair_claim(store, parent, stamp)


@pytest.mark.parametrize('clock', ['20:30', '21:30', '22:30', '23:20'])
def test_fourth_new_evening_feed_and_story_are_allowed_but_fifth_is_not(store, clock):
    at = parse_date('2026-10-25T' + clock + ':00+03:00')
    three_pairs(store, at)
    pub = min(at - timedelta(minutes=5), at.replace(hour=22, minute=55))
    fourth = add_news(store, at, 'fourth', pub)
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter) == {
        'status': 'complete', 'feed': 'published', 'story': 'published'}
    assert adapter.container.call_count == 2
    assert next(p for p in store.posts() if p['id'] == fourth['id'])['status'] == 'published'
    later = at + timedelta(minutes=1)
    fifth = add_news(store, later, 'fifth', pub)
    assert daily_limit_reason(store, later, fifth) == 'daily_limit'
    assert publish_one(store, later, 'https://example.org/', asset_map(store), adapter=adapter)['status'] == 'daily_limit'
    assert adapter.container.call_count == 2


def test_later_fourth_is_not_hidden_by_a_complete_third_pair_in_same_22_window(store):
    at = parse_date('2026-10-25T22:50:00+03:00')
    three_pairs(store, at, third='22:05')
    fourth = add_news(store, at, 'latefourth')
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter)['status'] == 'complete'
    assert next(p for p in store.posts() if p['id'] == fourth['id'])['status'] == 'published'
    assert adapter.container.call_count == 2


def test_evening_pair_still_respects_45_minute_spacing(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    three_pairs(store, at, third='22:05')
    add_news(store, at, 'tooclose')
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter)['status'] == 'rate_limited'
    adapter.container.assert_not_called()


@pytest.mark.parametrize('published,first,revision', [
    ('2026-10-25T19:59:00+03:00', '2026-10-25T21:00:00+03:00', 1),
    ('2026-10-24T21:00:00+03:00', '2026-10-25T21:00:00+03:00', 1),
    ('2026-10-25T21:00:00+03:00', '2026-10-25T19:59:00+03:00', 1),
    ('2026-10-25T21:00:00+03:00', '2026-10-25T20:00:00+03:00', 2),
    ('2026-10-25T23:00:00+03:00', '2026-10-25T23:01:00+03:00', 1),
])
def test_discovery_or_retimestamping_cannot_make_old_news_bonus_eligible(published, first, revision):
    item = {'kind': 'news', 'revision': revision, 'published_at': published, 'first_seen': first}
    assert not evening_news_item(item, parse_date('2026-10-25T23:20:00+03:00'))


def test_unchanged_old_article_retimestamped_in_second_revision_is_not_bonus(store):
    at = parse_date('2026-10-25T20:30:00+03:00')
    parent = add_news(store, at, 'oldarticle', at - timedelta(days=1))
    item = next(i for i in store.items() if i['id'] == parent['item_id'])
    store.upsert({k: v for k, v in item.items() if k not in ('id','revision','first_seen','last_seen')} |
                 {'published_at': at.isoformat()}, (at + timedelta(minutes=1)).isoformat())
    current = next(i for i in store.items() if i['id'] == item['id'])
    assert current['revision'] == 2 and current['first_seen'] == at.isoformat()
    assert not evening_news_item(current, at + timedelta(minutes=2))


def test_daytime_fourth_and_evening_calendar_are_not_exceptions(store):
    at = parse_date('2026-10-25T19:00:00+03:00')
    three_pairs(store, at)
    post = add_news(store, at, 'daytimefourth')
    assert daily_limit_reason(store, at, post) == 'daily_limit'
    at = at.replace(hour=21)
    assert not evening_post(store, {**post, 'kind': 'monthly'}, at)
    assert not evening_post(store, {**post, 'kind': 'reminder_day'}, at)


def test_old_due_queue_head_does_not_hide_new_evening_news(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    old = add_news(store, at.replace(hour=18, minute=0), 'olddue')
    three_pairs(store, at)
    new = add_news(store, at, 'freshselected')
    with store.db:
        store.db.execute('UPDATE items SET last_seen=? WHERE id=?', (at.isoformat(), old['item_id']))
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter)['status'] == 'complete'
    assert next(p for p in store.posts() if p['id'] == new['id'])['status'] == 'published'
    assert next(p for p in store.posts() if p['id'] == old['id'])['status'] == 'prepared'


def test_fourth_story_cannot_attach_to_a_third_feed_or_resume_after_midnight(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    three_pairs(store, at, third='22:05')
    third = max((p for p in store.posts() if not p.get('publish_format')), key=lambda p: p['published_at'])
    candidate = {**third, 'parent_post_id': third['id'], 'story_index': 0, 'publish_format': 'story'}
    assert not evening_post(store, candidate, at, story=True)
    assert not evening_post(store, candidate, at + timedelta(hours=2), story=True)


def test_extended_22_window_is_fresh_only_and_has_bounded_grace():
    for stamp in ('2026-10-25T22:30:00+03:00', '2026-10-25T23:29:59+03:00'):
        assert dispatch_window(parse_date(stamp), SLOTS)[2] is True
    assert dispatch_window(parse_date('2026-10-25T23:30:00+03:00'), SLOTS) is None
    assert dispatch_window(parse_date('2026-10-26T00:00:00+03:00'), SLOTS) is None


def test_preexisting_unclaimed_fresh_night_card_is_pulled_back_from_tomorrow(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    three_pairs(store, at)
    post = add_news(store, at, 'oldscheduledtomorrow')
    tomorrow = (at + timedelta(days=1)).replace(hour=8, minute=30).isoformat()
    payload = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    payload['due_at'] = tomorrow
    with store.db:
        store.db.execute('UPDATE posts SET due_at=?,payload=? WHERE id=?', (tomorrow, json.dumps(payload), post['id']))
    frozen = store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id")
    later = at + timedelta(minutes=1)
    prepare(store, later)
    refreshed = next(p for p in store.posts() if p['id'] == post['id'])
    assert refreshed['due_at'] == later.isoformat()
    assert refreshed['created_at'] == post['created_at']
    assert store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id") == frozen


def test_uncertain_fourth_consumes_extra_even_after_restart(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    three_pairs(store, at)
    fourth = add_news(store, at, 'uncertainfourth')
    adapter = api()
    adapter.call.side_effect = RuntimeError('unconfirmed write')
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter)['status'] == 'uncertain'
    reopened = Store(store.path)
    try:
        assert daily_limit_reason(reopened, at, fourth) == 'daily_limit'
        assert publish_automatic(reopened, at + timedelta(minutes=5), 'https://example.org/', asset_map(reopened), adapter)['status'] == 'awaiting_resolution'
    finally:
        reopened.close()
    assert adapter.container.call_count == 1


@pytest.mark.parametrize('clock', ['20:30', '22:30'])
def test_added_windows_do_not_drain_old_prepared_queue_even_below_regular_cap(store, clock):
    at = parse_date('2026-10-25T' + clock + ':00+03:00')
    old = add_news(store, at.replace(hour=18, minute=0), 'oldqueue')
    with store.db:
        store.db.execute('UPDATE items SET last_seen=? WHERE id=?', (at.isoformat(), old['item_id']))
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), adapter)['status'] == 'empty'
    adapter.container.assert_not_called()


def test_quickly_edited_fresh_news_can_use_regular_budget_but_not_bonus(store):
    at = parse_date('2026-10-25T22:30:00+03:00')
    parent = add_news(store, at - timedelta(minutes=5), 'quickedit')
    item = next(i for i in store.items() if i['id'] == parent['item_id'])
    store.upsert({k: v for k, v in item.items() if k not in ('id','revision','first_seen','last_seen')} |
                 {'description': 'Seferihisar için kaynak tarafından yeni doğrulanmış kültür ayrıntıları açıklandı.'}, at.isoformat())
    prepare(store, at)
    current = next(i for i in store.items() if i['id'] == item['id'])
    assert not evening_news_item(current, at)
    assert evening_news_item(current, at, bonus=False)
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), api())['status'] == 'complete'


def test_fourth_facebook_pair_is_not_hidden_behind_completed_third(store):
    from test_facebook_publication import api as facebook_api
    from seferihisar.facebook import publish_recent
    at = parse_date('2026-10-25T22:50:00+03:00')
    three_pairs(store, at, third='22:05')
    adapter = facebook_api()
    for parent in [p for p in store.posts() if not p.get('publish_format')]:
        for kind in ('feed', 'story'):
            key = digest(f"facebook:{adapter.page}:{parent['id']}:{kind}")
            with store.db:
                store.db.execute('INSERT INTO facebook_deliveries VALUES(?,?,?,?,?,?,?,?,?)',
                    (key, parent['id'], adapter.page, kind, 'published', parent['published_at'],
                     parent['published_at'], '[]', '12345678'))
    fourth = add_news(store, at, 'facebookfourth')
    assert publish_automatic(store, at, 'https://example.org/', asset_map(store), api())['status'] == 'complete'
    result = publish_recent(store, at, 'https://example.org/', asset_map(store), adapter)
    assert result == {'status': 'complete', 'feed': 'published', 'story': 'published'}
    rows = store.rows('SELECT * FROM facebook_deliveries WHERE post_id=?', (fourth['id'],))
    assert len(rows) == 2 and all(r['status'] == 'published' for r in rows)
    assert adapter.publish.call_count == 2
    assert publish_recent(store, at + timedelta(minutes=1), 'https://example.org/', asset_map(store), adapter)['status'] == 'complete'
    assert adapter.publish.call_count == 2
