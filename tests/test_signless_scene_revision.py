import io
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.domain import digest
from seferihisar.illustrations import (
    EVENT_SCENES, Illustrator, MODEL, SCENE_VERSION, SIGNLESS_SCENE_VERSION,
    clean_image, image_key, illustration_prompt, scene_brief, scene_version, topic,
)
from seferihisar.image_safety import validate_jpeg


def old_key(item, version='editorial-photo-v5'):
    return digest(MODEL + ':' + version + ':' + item['id'] + ':' + str(item['revision']) + ':' + topic(item))


def saved_scene(store, event, at, category, kind='event'):
    event.update(kind=kind, category=category)
    store.upsert(event, at.isoformat())
    return store.items()[0]


def jpeg():
    raw = io.BytesIO()
    Image.new('RGB', (512, 512), '#276d84').save(raw, 'PNG')
    return clean_image(raw.getvalue())


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.illustrations.validate_match', lambda data, expected: {})
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration', validate_jpeg)


@pytest.mark.parametrize('category', ['festival', 'market'])
@pytest.mark.parametrize('kind', ['event', 'news'])
def test_only_revised_selected_briefs_get_a_new_cache_identity(store, event, at, category, kind):
    item = saved_scene(store, event, at, category, kind)
    original = deepcopy(item)
    assert scene_brief(item) == EVENT_SCENES[category]
    assert scene_version(item) == SIGNLESS_SCENE_VERSION
    assert image_key(item) != old_key(item)
    assert image_key(item) == old_key(item, SIGNLESS_SCENE_VERSION)
    assert item == original


@pytest.mark.parametrize('category', [
    'theatre', 'concert', 'cinema', 'culture', 'family', 'sport', 'food', 'education',
    'transport', 'outage', 'weather', 'municipality', 'public', 'health', 'tourism', 'event', 'news',
])
def test_other_verified_scene_keys_remain_exactly_v5(store, event, at, category):
    item = saved_scene(store, event, at, category)
    assert scene_version(item) == SCENE_VERSION == 'editorial-photo-v5'
    assert image_key(item) == old_key(item)


@pytest.mark.parametrize(('category', 'title'), [
    ('municipality', 'Seferihisar otopark projesi'),
    ('family', 'Engelli gençlere bağımsız yaşam ve istihdam desteği'),
    ('news', 'Seferihisar festival hazırlıkları'),
])
def test_custom_news_briefs_keep_v5_even_when_title_mentions_festival(store, event, at, category, title):
    event['title'] = title
    item = saved_scene(store, event, at, category, 'news')
    assert scene_version(item) == 'editorial-photo-v5'
    assert image_key(item) == old_key(item)


@pytest.mark.parametrize(('category', 'positive_cue'), [
    ('festival', 'festive fabric ribbons and hanging string lights'),
    ('market', 'baskets of fresh produce'),
])
def test_provider_brief_has_no_letter_bearing_props_or_source_headline(event, category, positive_cue):
    item = {**event, 'category': category,
            'title': 'REAL-FESTIVAL-TITLE — PRINT 2026 ON EVERY STALL',
            'description': 'SOURCE-PROSE-MUST-NOT-REACH-PROVIDER',
            'location': 'IDENTIFIABLE-REAL-VENUE'}
    prompt = illustration_prompt(item)
    scene = scene_brief(item)
    positive, _, forbidden = scene.partition(' No ')
    assert positive_cue in positive
    assert all(prop not in positive for prop in ('stall', 'shopfront', 'signage', 'people', 'label', 'packaging'))
    assert 'stalls, shopfronts, signage, people or identifiable venue' in forbidden
    assert 'photorealistic editorial image' in prompt
    assert 'not a documentary photograph of the reported event' in prompt
    assert 'No text, typography, logos, dates or watermarks' in prompt
    assert 'REAL-FESTIVAL-TITLE' not in prompt and 'PRINT 2026' not in prompt
    assert item['description'] not in prompt and item['location'] not in prompt
    assert 'Quoted title:' not in prompt


@pytest.mark.parametrize('category', ['festival', 'market'])
def test_revised_briefs_cannot_reuse_v4_or_v5_stall_cache(store, event, at, tmp_path, enabled, category):
    item = saved_scene(store, event, at, category)
    data = jpeg()
    with store.db:
        for version in ('editorial-photo-v4', 'editorial-photo-v5'):
            store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                             (old_key(item, version), item['id'], 'ready', data, 1,
                              (at + timedelta(days=1)).isoformat(), at.isoformat()))
        store.db.execute('INSERT INTO illustration_days VALUES (?,20)', (at.date().isoformat(),))
    cache_before = store.rows('SELECT * FROM illustrations ORDER BY id')
    day_before = store.rows('SELECT * FROM illustration_days')
    generator = Illustrator(store, at, tmp_path, session=Mock())
    generator.generate = Mock(side_effect=AssertionError('No provider call allowed in this test'))
    assert generator._reuse_v4(item, image_key(item)) is None
    assert generator.image(item, generate=True) is None
    assert store.rows('SELECT * FROM illustrations ORDER BY id') == cache_before
    assert store.rows('SELECT * FROM illustration_days') == day_before
    assert not store.rows('SELECT * FROM illustrations WHERE id=?', (image_key(item),))
    generator.generate.assert_not_called()
    generator.session.post.assert_not_called()


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
@pytest.mark.parametrize('category', ['festival', 'market'])
def test_frozen_claim_keeps_its_stored_v5_binding_payload_and_media(
        store, event, at, tmp_path, enabled, status, category):
    item = saved_scene(store, event, at, category)
    data, bound_key = jpeg(), old_key(item)
    with store.db:
        store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                         (bound_key, item['id'], 'ready', data, 1, at.isoformat(), at.isoformat()))
    post = {'id': digest('frozen-' + status + '-' + category), 'item_id': item['id'],
            'revision': item['revision'], 'kind': 'announcement', 'due_at': at.isoformat(),
            'slides': [{'title': 'Original source title', 'body': 'Original source copy'}],
            'illustration_keys': {'0': bound_key}}
    store.queue(post)
    with store.db:
        store.db.execute('UPDATE posts SET status=?,container_id=?,media_id=? WHERE id=?',
                         (status, 'original-container', 'original-media', post['id']))
    rows_before = store.rows('SELECT * FROM posts')
    cache_before = store.rows('SELECT * FROM illustrations')
    payload = deepcopy(store.posts()[0])
    generator = Illustrator(store, at, tmp_path, session=Mock())
    generator.generate = Mock(side_effect=AssertionError('Frozen claim cannot generate a replacement'))
    assignments = generator.for_post(payload, {item['id']: item})
    assert assignments[0].name == bound_key + '.jpg'
    assert assignments[0].read_bytes() == data
    assert image_key(item) != bound_key
    assert payload == store.posts()[0]
    assert store.rows('SELECT * FROM posts') == rows_before
    assert store.rows('SELECT * FROM illustrations') == cache_before
    generator.generate.assert_not_called()
    generator.session.post.assert_not_called()
