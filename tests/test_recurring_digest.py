"""A digest and a queued story must survive what happens to their neighbours."""
from datetime import timedelta

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import prepare_story_jobs, publish_outage_story
from seferihisar.schedule import prepare
from test_publication_policy import all_assets, api, outage


def session(event, day, hour, name):
    return {**event, 'identity': f"{event['identity']}-{name}", 'start': day.replace(hour=hour).isoformat(),
            'end': day.replace(hour=hour + 2).isoformat(), 'time_known': True}


@pytest.mark.parametrize('stale_first', [False, True])
def test_stale_session_on_the_same_url_cannot_block_a_digest(store, event, at, stale_first):
    day = at + timedelta(days=2)
    current, stale = session(event, day, 14, 'current'), session(event, day, 17, 'stale')
    writes = [(current, at), (stale, at - timedelta(hours=8))]
    for item, seen in reversed(writes) if stale_first else writes:
        store.upsert(item, seen.isoformat())
    prepare(store, at)
    weekly = next(p for p in store.posts() if p['kind'] == 'weekly')
    assert weekly['status'] == 'prepared' and len(weekly['event_ids']) == 1
    prepare(store, at + timedelta(minutes=8), refresh_digests=False)
    assert next(p for p in store.posts() if p['id'] == weekly['id'])['status'] == 'prepared'


def test_digest_still_stops_when_its_own_event_goes_stale(store, event, at):
    store.upsert(session(event, at + timedelta(days=2), 14, 'current'), at.isoformat())
    prepare(store, at)
    prepare(store, at + timedelta(hours=2), refresh_digests=False)
    assert next(p for p in store.posts() if p['kind'] == 'weekly')['status'] == 'blocked_source'


def queued_outage(store):
    morning = parse_date('2026-10-23T09:09:48+03:00')
    store.upsert(outage(morning), morning.isoformat())
    prepare(store, morning)
    assets = all_assets(store)
    prepare_story_jobs(store, assets)
    parent = next(p for p in store.posts() if not p.get('publish_format') and p['category'] == 'outage')
    return morning, assets, parent['id'], digest(parent['id'] + ':story:0')


def status(store, key):
    return store.rows('SELECT status FROM posts WHERE id=?', (key,))[0]['status']


def test_briefly_blocked_parent_keeps_its_story(store):
    morning, assets, parent, story = queued_outage(store)
    with store.db:
        store.db.execute("UPDATE posts SET status='blocked_source' WHERE id=?", (parent,))
    prepare_story_jobs(store, assets)
    assert status(store, story) != 'superseded'


def test_story_lost_to_a_past_block_returns_with_its_prepared_parent(store):
    morning, assets, parent, story = queued_outage(store)
    with store.db:
        store.db.execute("UPDATE posts SET status='superseded' WHERE id=?", (story,))
    adapter = api()
    assert publish_outage_story(store, morning, 'https://example.org/', assets, adapter)['status'] == 'published'
    assert status(store, story) == 'published'


@pytest.mark.parametrize('claimed', ['published', 'blocked_source'])
def test_dropped_story_stays_dropped_unless_its_parent_is_waiting(store, claimed):
    morning, assets, parent, story = queued_outage(store)
    with store.db:
        store.db.execute("UPDATE posts SET status='superseded' WHERE id=?", (story,))
        store.db.execute('UPDATE posts SET status=? WHERE id=?', (claimed, parent))
    prepare_story_jobs(store, assets)
    assert status(store, story) == 'superseded'
