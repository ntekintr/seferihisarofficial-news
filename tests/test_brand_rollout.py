"""A logo rollout must not mutate any previously claimed social asset."""
import json
import shutil
from copy import deepcopy

import pytest

from seferihisar import brand, render
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.security import validate_public, validate_state
from seferihisar.visual_gate import content_key, review, valid_review
from seferihisar.weather import parse_forecast
from seferihisar.weather_data import asset_id, validate_forecast
from tests.test_weather_story import HTML, MORNING


@pytest.mark.parametrize('status', ['prepared', 'blocked_source'])
def test_only_unclaimed_posts_get_the_current_brand(status):
    post = {'status': status}
    brand.prepare(post)
    assert post['brand_version'] == brand.VERSION


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
@pytest.mark.parametrize('marked', [False, True])
def test_claims_keep_their_original_brand_and_payload(status, marked, tmp_path, monkeypatch):
    post = {'id': 'a'*24, 'kind': 'news', 'category': 'news', 'status': status,
            'slides': [{'title': 'Seferihisar gündemi', 'body': 'Haberin ayrıntıları'}]}
    if marked:
        post['brand_version'] = brand.VERSION
    original = deepcopy(post)
    brand.prepare(post)
    assert post == original
    calls = []
    monkeypatch.setattr(render, 'card', lambda *args, **kw: calls.append(kw))
    render.render_post(post, tmp_path)
    assert len(calls) == 2
    assert {c['brand_version'] for c in calls} == {brand.VERSION if marked else brand.LEGACY}


def test_rollout_invalidates_only_unclaimed_old_visual_proof():
    post = {'id': 'a'*24, 'status': 'prepared', 'kind': 'news', 'slides': []}
    old_key = content_key(post)
    post['visual_review'] = review(post, {})
    assert valid_review(post)
    old = deepcopy(post)
    brand.prepare(post)
    assert content_key(post) != old_key and not valid_review(post)
    post['visual_review'] = review(post, {})
    assert valid_review(post)
    assert post['visual_review']['edition'] != old['visual_review']['edition']
    assert content_key(old) == old_key and valid_review(old)


def test_prepared_export_and_queue_refresh_keep_versioned_brand(store, event, source, at, tmp_path, monkeypatch):
    store.upsert(event, at.isoformat())
    item = store.items()[0]
    queue_item(store, item, 'announcement', at, at)
    _export(store, tmp_path/'public', [source], at)
    post = store.posts()[0]
    assert post['brand_version'] == brand.VERSION and valid_review(post)
    assert (tmp_path/'public'/brand.PUBLIC_ASSET).read_bytes() == brand.logo_path().read_bytes()
    snapshot = json.loads((tmp_path/'public/data.json').read_text(encoding='utf8'))
    assert snapshot['brand'] == {'version': brand.VERSION, 'logo': brand.PUBLIC_ASSET}
    queue_item(store, item, 'announcement', at, at)
    assert store.posts()[0]['brand_version'] == brand.VERSION
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'false')
    _export(store, tmp_path/'publisher', [source], at)
    assert store.posts()[0] == post
    validate_state(store.path)
    validate_public(tmp_path/'publisher')


def test_weather_brand_changes_asset_identity_without_touching_legacy_forecast():
    current = parse_forecast(HTML, MORNING)
    assert current['brand_version'] == brand.VERSION
    old = {k:v for k,v in current.items() if k != 'brand_version'}
    original = deepcopy(old)
    validate_forecast(old)
    assert asset_id(old) != asset_id(current)
    assert old == original
    current['fetched_at'] = '2026-10-16T08:10:00+03:00'
    assert asset_id(current) != asset_id(old)


@pytest.mark.parametrize('value', ['unknown', '../logo.png', None, [], {}])
def test_unknown_brand_rejected_in_forecast_and_logo_selection(value):
    forecast = parse_forecast(HTML, MORNING)
    forecast['brand_version'] = value
    with pytest.raises(ValueError, match='brand'):
        validate_forecast(forecast)
    with pytest.raises(ValueError, match='brand'):
        brand.logo_path(value)


def test_unknown_post_brand_rejected_at_durable_state_boundary(store, event, at):
    store.upsert(event, at.isoformat())
    queue_item(store, store.items()[0], 'announcement', at, at)
    post = store.posts()[0]
    post['brand_version'] = '../private-file'
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(post), post['id']))
    with pytest.raises(ValueError, match='brand'):
        validate_state(store.path)


def test_public_boundary_accepts_only_the_exact_approved_brand_image(tmp_path):
    target = tmp_path/brand.PUBLIC_ASSET
    shutil.copyfile(brand.logo_path(), target)
    validate_public(tmp_path)
    target.write_bytes(b'private contents disguised as logo')
    with pytest.raises(ValueError, match='brand asset'):
        validate_public(tmp_path)
    target.unlink()
    (tmp_path/'unapproved.png').write_bytes(b'not a public asset')
    with pytest.raises(ValueError, match='Unexpected file'):
        validate_public(tmp_path)


def test_site_uses_approved_logo_for_header_and_browser_icon():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1]/'site/index.html').read_text(encoding='utf8')
    assert 'src="'+brand.PUBLIC_ASSET+'"' in html
    assert 'href="'+brand.PUBLIC_ASSET+'"' in html
    assert '<span class="brand-icon">' not in html
