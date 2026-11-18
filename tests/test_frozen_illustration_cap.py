"""18 Nov 2026: a claimed key whose bytes were pruned must not be regenerated.

The cache held 80 frozen images, so the end-of-run prune dropped a fresh scene
already bound to a prepared parent. Its story went out with that binding. The
next research run regenerated the key for the still-prepared parent; prune
never evicts a frozen row, so 81 ready images failed the state check in every
run from 13:17Z.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

from seferihisar.domain import digest
from seferihisar.illustrations import EVENT_SCENES, NEWS_SCENES, Illustrator, image_key, scene_brief, subject
from seferihisar.schedule import prepare
from seferihisar.security import failure_location, validate_state

from test_illustrations import client, configured, saved_item  # noqa: F401  (fixture)


def jpeg(colour):
    out = io.BytesIO()
    Image.new('RGB', (768, 768), colour).save(out, format='JPEG', quality=82)
    return out.getvalue()


def publish_story_of(store, parent, key):
    story = {**{k: v for k, v in parent.items() if k not in ('status', 'container_id', 'media_id')},
             'id': digest('story:' + parent['id']), 'publish_format': 'story', 'parent_post_id': parent['id'],
             'story_index': 0, 'illustration_keys': {'0': key}, 'published_at': parent['due_at']}
    with store.db:
        store.db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?)',
                         (story['id'], parent.get('item_id'), parent['revision'], parent['kind'], parent['due_at'],
                          'published', json.dumps(story, ensure_ascii=False), '1', '2'))


def fill_cache_with_frozen(store, item_id, count, at):
    keys = []
    for index in range(count):
        key = digest('frozen-%d' % index)
        keys.append(key)
        with store.db:
            store.db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',
                             (key, item_id, 'ready', jpeg((index, 40, 90)), 1, at.isoformat(), at.isoformat()))
            store.db.execute('INSERT INTO posts VALUES(?,?,?,?,?,?,?,?,?)',
                             (digest('post-%d' % index), item_id, 1, 'announcement', at.isoformat(), 'published',
                              json.dumps({'id': digest('post-%d' % index), 'illustration_keys': {'0': key}}), '1', '2'))
    return keys


def outage(event):
    # The 18 Nov item: a planned power cut, a topic scene outside the v5
    # event/news briefs, so the older v5-only frozen check did not apply.
    return {**event, 'category': 'outage', 'title': 'Seferihisar planlı elektrik kesintisi'}


def test_claimed_key_without_bytes_is_not_regenerated_and_cache_stays_valid(store, event, at, tmp_path, configured):
    item = saved_item(store, outage(event), at)
    assert subject(item) == 'electrical'
    assert scene_brief(item) not in (*EVENT_SCENES.values(), *NEWS_SCENES.values())
    prepare(store, at)
    parent = next(p for p in store.posts() if p['kind'] == 'announcement' and p.get('item_id') == item['id'])
    key = image_key(item)
    fill_cache_with_frozen(store, item['id'], 80, at)
    # The scene was bound and exported, then pruned; its story was published.
    publish_story_of(store, parent, key)
    assert not store.rows('SELECT id FROM illustrations WHERE id=?', (key,))
    session = client()
    generator = Illustrator(store, at, tmp_path / 'next', session=session)
    generator.prune({item['id']})
    assert generator.for_post(parent, {item['id']: item}) == {}
    generator.prune({item['id']})
    session.post.assert_not_called()
    assert not store.rows('SELECT id FROM illustrations WHERE id=?', (key,))
    assert generator.stats['deferred'] == 1 and generator.stats['attempted'] == 0
    assert store.db.execute("SELECT count(*) FROM illustrations WHERE status='ready'").fetchone()[0] == 80
    validate_state(store.path)


def test_unclaimed_key_is_still_generated(store, event, at, tmp_path, configured):
    item = saved_item(store, outage(event), at)
    prepare(store, at)
    parent = next(p for p in store.posts() if p['kind'] == 'announcement' and p.get('item_id') == item['id'])
    session = client()
    generator = Illustrator(store, at, tmp_path, session=session)
    assert generator.for_post(parent, {item['id']: item})
    assert session.post.call_count == 1
    validate_state(store.path)


def test_state_check_names_table_and_rule_without_row_content(store, event, at, tmp_path):
    item = saved_item(store, event, at)
    fill_cache_with_frozen(store, item['id'], 81, at)
    try:
        validate_state(store.path)
    except ValueError as exc:
        assert failure_location(exc) == 'table=illustrations rule=Illustration cache exceeds limit'
    else:
        raise AssertionError('81 cached images must fail the state check')
    with store.db:
        store.db.execute("DELETE FROM illustrations WHERE id IN (SELECT id FROM illustrations LIMIT 1)")
        store.db.execute("UPDATE illustrations SET updated_at='not-a-date-secret-value' WHERE rowid=(SELECT min(rowid) FROM illustrations)")
    result = subprocess.run([sys.executable, '-m', 'seferihisar.security', 'state', str(store.path)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode != 0
    assert 'table=illustrations rule=ValueError' in result.stderr
    assert 'not-a-date-secret-value' not in result.stderr + result.stdout
