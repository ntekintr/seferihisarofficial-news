"""Owner decision, 19 Nov 2026: a published scene leaves the cache after 24 h.

"7 gün bile saklama 1 gün sonra silsin." The bytes go 24 hours after the
last delivery that used them (all posts binding the key and their Facebook
mirror). The key stays claimed and is never generated again. A full cache
spends no provider call and no daily attempt.
"""
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.domain import digest
from seferihisar.historical_visuals import eligible, fingerprint, recover
from seferihisar.illustration_retention import RETAIN_AFTER_PUBLICATION
from seferihisar.illustrations import Illustrator, image_key
from seferihisar.schedule import prepare
from seferihisar.security import validate_state

from test_illustrations import client, configured, saved_item  # noqa: F401  (fixture)
from test_frozen_illustration_cap import outage


def jpeg(colour=(30, 60, 90)):
    out = io.BytesIO()
    Image.new('RGB', (768, 768), colour).save(out, format='JPEG', quality=82)
    return out.getvalue()


def cache(store, key, item_id, at):
    with store.db:
        store.db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',
                         (key, item_id, 'ready', jpeg(), 1, at.isoformat(), at.isoformat()))


def post(store, name, status, key, published_at=None, **extra):
    payload = {'id': digest(name), 'illustration_keys': {'0': key}, **extra}
    if published_at:
        payload['published_at'] = published_at.isoformat()
    due = published_at or datetime(2026, 10, 1, tzinfo=timezone.utc)
    claimed = status == 'published'
    with store.db:
        store.db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?)',
                         (payload['id'], digest('item'), 1, 'announcement', due.isoformat(), status,
                          json.dumps(payload), '1' if claimed else None, '2' if claimed else None))
    return payload['id']


def facebook(store, post_id, status, stamp, kind='feed'):
    with store.db:
        store.db.execute('INSERT INTO facebook_deliveries VALUES(?,?,?,?,?,?,?,?,?)',
                         (digest('fb:' + post_id + kind), post_id, '123', kind, status, stamp.isoformat(), stamp.isoformat(),
                          '[]', '456' if status == 'published' else None))


def cached(store, key):
    return bool(store.rows('SELECT id FROM illustrations WHERE id=?', (key,)))


@pytest.mark.parametrize('age,kept', [(RETAIN_AFTER_PUBLICATION - timedelta(minutes=1), True),
                                      (RETAIN_AFTER_PUBLICATION, False)])
def test_published_scene_leaves_24_hours_after_last_publication(store, at, tmp_path, age, kept):
    key = digest('scene')
    cache(store, key, digest('item'), at)
    post(store, 'feed', 'published', key, at - age - timedelta(hours=1))
    post(store, 'story', 'published', key, at - age, publish_format='story')
    Illustrator(store, at, tmp_path).prune({digest('item')})
    assert cached(store, key) is kept
    validate_state(store.path)


@pytest.mark.parametrize('child', ['prepared', 'blocked_source', 'publishing', 'uncertain'])
def test_unfinished_child_keeps_scene(store, at, tmp_path, child):
    key = digest('scene')
    cache(store, key, digest('item'), at)
    post(store, 'feed', 'published', key, at - timedelta(days=3))
    post(store, 'story', child, key, publish_format='story')
    Illustrator(store, at, tmp_path).prune({digest('item')})
    assert cached(store, key)


def test_facebook_mirror_keeps_scene_until_finished_and_24_hours_old(store, at, tmp_path):
    key = digest('scene')
    cache(store, key, digest('item'), at)
    parent = post(store, 'feed', 'published', key, at - timedelta(days=3))
    facebook(store, parent, 'uncertain', at - timedelta(days=3))
    Illustrator(store, at, tmp_path).prune({digest('item')})
    assert cached(store, key)
    with store.db:
        store.db.execute("UPDATE facebook_deliveries SET status='published',media_id='456',updated_at=?",
                         ((at - timedelta(hours=23)).isoformat(),))
    Illustrator(store, at, tmp_path).prune({digest('item')})
    assert cached(store, key)  # The mirror delivery is the last one: 23 h ago.
    Illustrator(store, at + timedelta(hours=1), tmp_path).prune({digest('item')})
    assert not cached(store, key)
    validate_state(store.path)


def test_released_claimed_scene_is_never_generated_again(store, event, at, tmp_path, configured):
    item = saved_item(store, outage(event), at)
    prepare(store, at)
    parent = next(p for p in store.posts() if p['kind'] == 'announcement' and p.get('item_id') == item['id'])
    key = image_key(item)
    cache(store, key, item['id'], at - timedelta(days=2))
    post(store, 'published-sibling', 'published', key, at - timedelta(days=2))
    session = client()
    generator = Illustrator(store, at, tmp_path, session=session)
    generator.prune({item['id']})
    assert not cached(store, key) and generator.stats['released'] == 1
    assert generator.for_post(parent, {item['id']: item}) == {}
    session.post.assert_not_called()
    assert not store.rows('SELECT * FROM illustration_days')
    assert not cached(store, key)
    validate_state(store.path)


@pytest.mark.parametrize('limit', ['count', 'bytes'])
def test_full_cache_spends_no_provider_call_or_daily_attempt(store, event, at, tmp_path, configured, monkeypatch, limit):
    item = saved_item(store, outage(event), at)
    if limit == 'count':
        for index in range(80):
            cache(store, digest('draft-%d' % index), item['id'], at)
    else:
        cache(store, digest('draft'), item['id'], at)
        size = store.rows('SELECT length(image) AS n FROM illustrations')[0]['n']
        monkeypatch.setattr('seferihisar.illustrations.MAX_CACHE_BYTES', size + 512 * 1024 - 1)
    session = client()
    generator = Illustrator(store, at, tmp_path, session=session)
    assert generator.image(item, True) is None
    session.post.assert_not_called()
    assert generator.stats['cache_full'] == 1 and generator.stats['deferred'] == 1
    assert generator.stats['attempted'] == 0
    assert not store.rows('SELECT * FROM illustration_days')
    assert not cached(store, image_key(item))


def test_cache_with_room_still_generates(store, event, at, tmp_path, configured):
    item = saved_item(store, outage(event), at)
    for index in range(79):
        cache(store, digest('draft-%d' % index), item['id'], at)
    session = client()
    generator = Illustrator(store, at, tmp_path, session=session)
    assert generator.image(item, True)
    assert session.post.call_count == 1 and generator.stats['cache_full'] == 0
    validate_state(store.path)


def test_archive_recovery_skips_a_released_scene(store, at, tmp_path):
    key = digest('historical')
    owner = post(store, 'owner', 'published', key, at - timedelta(days=30))
    row = store.db.execute('SELECT * FROM posts WHERE id=?', (owner,)).fetchone()
    manifest = {'state_commit': '0' * 40, 'snapshot_sha256': '0' * 64,
                'rows': [{'key': key, 'original': 'x', 'observed': None, 'owners': {owner: fingerprint(tuple(row))}}]}
    store.db.commit()
    with sqlite3.connect(store.path) as raw:
        assert eligible(raw, manifest['rows'][0])  # Only the retention filter skips it.
    git = Mock(side_effect=AssertionError('archive must not be read'))
    assert recover(store.path, git, manifest, at=at) == 0
    git.assert_not_called()
