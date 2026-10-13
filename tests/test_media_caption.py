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
from seferihisar.instagram import publish_one
from seferihisar.media_caption import GENERATED_IMAGE_NOTE, generated_image_caption
from seferihisar.pipeline import export
from seferihisar.schedule import prepare


@pytest.fixture
def generated_scene(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'SYNTHETIC_CLOUDFLARE_CREDENTIAL_0123456789')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
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
def test_generated_disclosure_survives_research_to_disabled_publisher_and_final_prepare(
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
    assert expected_keys and GENERATED_IMAGE_NOTE in post['caption']
    assert len(post['caption']) <= 2200
    assert generated_scene.call_count == 1

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
    assert retained['caption'].count(GENERATED_IMAGE_NOTE) == 1
    public = json.loads((tmp_path / 'publisher/data.json').read_text(encoding='utf-8'))
    assert next(p for p in public['posts'] if p['id'] == post['id'])['caption'] == retained['caption']

    api = meta_adapter()
    result = publish_one(store, publish_at, 'https://example.org/', assets, adapter=api, target_id=post['id'])
    assert result['status'] == 'published'
    urls, published_caption, story = api.container.call_args.args
    assert urls == ['https://example.org/' + path for path in assets[post['id']]['feed']]
    assert story is False
    assert published_caption.count(GENERATED_IMAGE_NOTE) == 1
    assert published_caption == retained['caption']
    assert len(published_caption) <= 2200
    assert generated_scene.call_count == 1


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
def test_claimed_caption_and_bindings_are_not_rewritten_by_prepare_or_export(
        store, event, at, tmp_path, generated_scene, status):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    export(store, tmp_path / 'initial', source_config(), at)
    post = next(p for p in store.posts() if p['kind'] == 'announcement')
    with store.db:
        store.db.execute('UPDATE posts SET status=? WHERE id=?', (status, post['id']))
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
    assert all(GENERATED_IMAGE_NOTE in p['caption'] for p in store.posts())
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',
                        Mock(side_effect=IllustrationTextRejected('Illustration lettering rejected')))
    export(store, tmp_path / 'fallback', source_config(), at + timedelta(minutes=15))
    public = json.loads((tmp_path / 'fallback/data.json').read_text(encoding='utf-8'))
    assert all(GENERATED_IMAGE_NOTE not in p['caption'] for p in public['posts'])
    assert all(p['illustration_keys'] == {} for p in store.posts())
    assert generated_scene.call_count == 1


def test_disclosure_is_idempotent_and_reserves_complete_source_and_tags_under_limit():
    source = 'Kaynak: İzmir Art\nhttps://www.izmir.art/etkinlik/123#program'
    tags = ['#urla', '#tiyatro', '#tiyatrooyunu', '#seferihisarofficial']
    original = caption_with_hashtags('Uzun duyuru açıklaması ' * 300, tags, footer=source)
    disclosed = generated_image_caption(original, True)
    assert len(disclosed) <= 2200
    assert disclosed.count(GENERATED_IMAGE_NOTE) == 1
    assert source in disclosed
    assert disclosed.endswith(' '.join(tags))
    assert generated_image_caption(disclosed, True) == disclosed
    removed = generated_image_caption(disclosed, False)
    assert GENERATED_IMAGE_NOTE not in removed
    assert source in removed and removed.endswith(' '.join(tags))
    assert generated_image_caption(original, False) == original

