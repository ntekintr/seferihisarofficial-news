import io
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.editor import caption_with_hashtags
from seferihisar.illustrations import clean_image
from seferihisar.image_safety import IllustrationTextRejected, validate_jpeg
from seferihisar.instagram import publish_one, prepare_story_jobs
from seferihisar.media_caption import GENERATED_IMAGE_NOTE, generated_image_caption
from seferihisar.pipeline import export
from seferihisar.schedule import prepare


@pytest.fixture
def generated_scene(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'SYNTHETIC_CLOUDFLARE_CREDENTIAL_0123456789')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.illustrations.validate_match', lambda data, expected: {})
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration', validate_jpeg)
    image = io.BytesIO()
    Image.new('RGB', (512, 512), '#346175').save(image, 'PNG')
    generate = Mock(return_value=clean_image(image.getvalue()))
    monkeypatch.setattr('seferihisar.illustrations.Illustrator.generate', generate)
    return generate


def source_config():
    return json.loads(Path('config/sources.json').read_text())


def meta_adapter():
    api = Mock()
    api.enabled.return_value = True
    api.account = '1234'
    api.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    api.container.return_value = 'mock-container'
    api.call.return_value = {'id': 'mock-media'}
    return api


@pytest.mark.parametrize('kind', ['news', 'event', 'weekly'])
def test_source_only_caption_survives_research_to_disabled_publisher_and_final_prepare(
        store, event, at, tmp_path, monkeypatch, generated_scene, kind):
    research_at = at.replace(hour=15)
    if kind == 'news':
        event = json.loads(Path('tests/fixtures/items.json').read_text())[3]
        event['category'] = 'transport'
    store.upsert(event, research_at.isoformat())
    prepare(store, research_at)
    export(store, tmp_path / 'research', source_config(), research_at)
    post = next(p for p in store.posts() if p['kind'] == {'event': 'reminder_3d'}.get(kind, kind))
    expected_keys = post['illustration_keys']
    assert bool(expected_keys) == (kind != 'news')
    assert GENERATED_IMAGE_NOTE not in post['caption']
    assert event['source_name'] in post['caption'] and event['url'] in post['caption']
    assert len(post['caption']) <= 2200
    assert generated_scene.call_count == (0 if kind == 'news' else 1)

    # An older research version may already have queued the retired note.
    legacy = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    legacy['caption'] += '\n\n' + GENERATED_IMAGE_NOTE
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(legacy), post['id']))

    # The production publisher has no artwork credentials/enable flag. It
    # creates its manifest locally but sends deployed research media URLs.
    monkeypatch.delenv('ILLUSTRATIONS_ENABLED')
    monkeypatch.delenv('CLOUDFLARE_API_TOKEN')
    monkeypatch.delenv('CLOUDFLARE_ACCOUNT_ID')
    publish_at = research_at + timedelta(minutes=15)
    prepare(store, publish_at)
    assets = export(store, tmp_path / 'publisher', source_config(), publish_at)
    retained = next(p for p in store.posts() if p['id'] == post['id'])
    assert retained['illustration_keys'] == expected_keys
    assert GENERATED_IMAGE_NOTE not in retained['caption']
    public = json.loads((tmp_path / 'publisher/data.json').read_text(encoding='utf-8'))
    assert next(p for p in public['posts'] if p['id'] == post['id'])['caption'] == retained['caption']

    api = meta_adapter()
    result = publish_one(store, publish_at, 'https://example.org/', assets, adapter=api, target_id=post['id'])
    assert result['status'] == 'published'
    urls, published_caption, story = api.container.call_args.args
    assert urls == ['https://example.org/' + path for path in assets[post['id']]['feed']]
    assert story is False
    assert GENERATED_IMAGE_NOTE not in published_caption
    assert published_caption == retained['caption']
    assert len(published_caption) <= 2200
    assert generated_scene.call_count == (0 if kind == 'news' else 1)


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
def test_claimed_caption_and_bindings_are_not_rewritten_by_prepare_or_export(
        store, event, at, tmp_path, generated_scene, status):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    export(store, tmp_path / 'initial', source_config(), at)
    post = next(p for p in store.posts() if p['kind'] == 'announcement')
    payload = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    payload['caption'] += '\n\n' + GENERATED_IMAGE_NOTE
    with store.db:
        store.db.execute('UPDATE posts SET payload=?,status=? WHERE id=?', (json.dumps(payload), status, post['id']))
    original_payload = store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload']
    assert GENERATED_IMAGE_NOTE in json.loads(original_payload)['caption']
    later = at + timedelta(minutes=15)
    prepare(store, later)
    export(store, tmp_path / 'later', source_config(), later)
    assert store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'] == original_payload
    assert generated_scene.call_count == 1


def test_rejected_generated_scene_falls_back_without_an_ai_disclosure(
        store, event, at, tmp_path, monkeypatch, generated_scene):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    export(store, tmp_path / 'initial', source_config(), at)
    assert all(GENERATED_IMAGE_NOTE not in p['caption'] for p in store.posts())
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',
                        Mock(side_effect=IllustrationTextRejected('Illustration lettering rejected')))
    export(store, tmp_path / 'fallback', source_config(), at + timedelta(minutes=15))
    public = json.loads((tmp_path / 'fallback/data.json').read_text(encoding='utf-8'))
    assert all(GENERATED_IMAGE_NOTE not in p['caption'] for p in public['posts'])
    assert all(p['illustration_keys'] == {} for p in store.posts())
    assert generated_scene.call_count == 1


@pytest.mark.parametrize('generated', [False, True])
def test_legacy_note_removal_reserves_complete_source_and_tags_under_limit(generated):
    source = 'Kaynak: İzmir Art\nhttps://www.izmir.art/etkinlik/123#program'
    tags = ['#urla', '#tiyatro', '#tiyatrooyunu', '#seferihisarofficial']
    original = caption_with_hashtags('Uzun duyuru açıklaması ' * 300, tags, footer=source)
    legacy = original.replace('\n\nKaynak:', '\n\n' + GENERATED_IMAGE_NOTE + '\n\nKaynak:')
    cleaned = generated_image_caption(legacy, generated)
    assert len(cleaned) <= 2200
    assert GENERATED_IMAGE_NOTE not in cleaned
    assert source in cleaned and cleaned.endswith(' '.join(tags))
    assert generated_image_caption(cleaned, generated) == cleaned
    assert generated_image_caption(original, generated) == original


def test_news_about_ai_keeps_its_facts():
    caption = 'Yapay zekâ eğitimleri başladı.\n\nKaynak: Yerel Haber\nhttps://example.org/haber'
    assert generated_image_caption(caption, True) == caption


def test_future_story_cleans_legacy_parent_note_without_rewriting_published_feed(store, event, at):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    post = next(p for p in store.posts() if p['kind'] == 'announcement')
    payload = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    payload['caption'] += '\n\n' + GENERATED_IMAGE_NOTE
    with store.db:
        store.db.execute("UPDATE posts SET payload=?,status='published' WHERE id=?", (json.dumps(payload), post['id']))
    before = store.rows('SELECT * FROM posts WHERE id=?', (post['id'],))[0]
    prepare_story_jobs(store, {post['id']: {'story': [f"media/{post['id']}/story-1.jpg"]}})
    child = next(p for p in store.posts() if p.get('parent_post_id') == post['id'])
    assert GENERATED_IMAGE_NOTE not in child['caption']
    assert event['source_name'] in child['caption'] and event['url'] in child['caption']
    assert store.rows('SELECT * FROM posts WHERE id=?', (post['id'],))[0] == before
