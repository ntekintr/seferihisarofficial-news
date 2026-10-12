import base64
import io
import json
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest
import requests
from PIL import Image

from seferihisar.domain import digest
from seferihisar.illustrations import Illustrator, STYLE, clean_image, image_key, topic
from seferihisar.pipeline import export
from seferihisar.schedule import prepare
from seferihisar.security import validate_public, validate_state
from seferihisar.state_git import persist, restore
from seferihisar.store import Store


def png():
    target = io.BytesIO()
    Image.new('RGB', (1024, 1024), '#f58220').save(target, format='PNG')
    return target.getvalue()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'SYNTHETIC_CLOUDFLARE_CREDENTIAL_0123456789')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')


def client():
    session = MagicMock()
    response = session.post.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [json.dumps({'success': True, 'result': {'image': base64.b64encode(png()).decode()}}).encode()]
    return session


def saved_item(store, event, at):
    store.upsert(event, at.isoformat())
    return store.items()[0]


def test_fresh_runner_reuses_revision_and_changed_item_gets_new_art(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    session = client()
    first = Illustrator(store, at, tmp_path/'first', session=session)
    art = first.image(item, True)
    assert art and art.exists() and first.stats['generated'] == 1
    validate_state(store.path)
    second = Illustrator(store, at+timedelta(minutes=15), tmp_path/'second', session=session)
    assert second.image(item, True).read_bytes() == art.read_bytes()
    assert session.post.call_count == 1
    event['title'] += ' - yeni tarih'
    store.upsert(event, (at+timedelta(minutes=15)).isoformat())
    assert second.image(store.items()[0], True)
    assert session.post.call_count == 2
    args, kwargs = session.post.call_args
    assert args[0].endswith('/ai/run/@cf/black-forest-labs/flux-1-schnell')
    assert kwargs['json']['steps'] == 4
    assert kwargs['allow_redirects'] is False
    assert kwargs['stream'] is True


def test_no_secret_or_provider_metadata_in_cache_or_public(store, event, at, tmp_path, configured, monkeypatch):
    source = json.loads(Path('config/sources.json').read_text())
    saved_item(store, event, at)
    prepare(store, at)
    session = client()
    monkeypatch.setattr('seferihisar.illustrations.requests', session)
    export(store, tmp_path/'public', source, at)
    validate_state(store.path)
    validate_public(tmp_path/'public')
    data = json.loads((tmp_path/'public/data.json').read_text())
    assert data['illustrations']['generated'] == 1
    assert data['illustrations']['reused'] >= 2
    assert len(list((tmp_path/'public').rglob('*.jpg'))) >= 2
    assert 'SYNTHETIC_CLOUDFLARE' not in json.dumps(data)
    assert b'SYNTHETIC_CLOUDFLARE' not in store.path.read_bytes()
    assert not list((tmp_path/'public').rglob('*.png'))


def test_demo_and_disabled_mode_never_call_provider(store, event, at, tmp_path, configured, monkeypatch):
    item = saved_item(store, event, at)
    session = client()
    assert Illustrator(store, at, tmp_path, demo=True, session=session).image(item, True) is None
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'false')
    assert Illustrator(store, at, tmp_path, session=session).image(item, True) is None
    session.post.assert_not_called()


def test_uncertain_request_is_claimed_and_not_repeated_by_next_runner(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    session = client()
    session.post.side_effect = requests.Timeout('Authorization=PRIVATE_EXCEPTION_VALUE')
    first = Illustrator(store, at, tmp_path, session=session)
    assert first.image(item, True) is None
    next_runner = Illustrator(store, at+timedelta(minutes=15), tmp_path, session=session)
    assert next_runner.image(item, True) is None
    assert session.post.call_count == 1
    assert b'PRIVATE_EXCEPTION_VALUE' not in store.path.read_bytes()
    next_day = Illustrator(store, at+timedelta(days=1), tmp_path, session=session)
    assert next_day.image(item, True) is None
    third_day = Illustrator(store, at+timedelta(days=2), tmp_path, session=session)
    assert third_day.image(item, True) is None
    assert session.post.call_count == 2
    validate_state(store.path)


def test_run_and_durable_daily_limits_keep_cached_art_available(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    session = client()
    generator = Illustrator(store, at, tmp_path, session=session)
    assert generator.image(item, True)
    assert generator.image({**item, 'id': digest('second')}, True)
    assert generator.image({**item, 'id': digest('third')}, True) is None
    with store.db:
        store.db.execute('UPDATE illustration_days SET attempts=20')
    fresh = Illustrator(store, at+timedelta(minutes=15), tmp_path, session=session)
    assert fresh.image({**item, 'id': digest('fourth')}, True) is None
    assert fresh.image(item, True)
    assert session.post.call_count == 2
    validate_state(store.path)


@pytest.mark.parametrize('status', [401, 403, 429, 500, 302])
def test_provider_failure_stops_more_requests_and_keeps_fallback(store, event, at, tmp_path, configured, status):
    item = saved_item(store, event, at)
    session = client()
    session.post.return_value.__enter__.return_value.status_code = status
    generator = Illustrator(store, at, tmp_path, session=session)
    assert generator.image(item, True) is None
    assert generator.image({**item, 'id': digest('other')}, True) is None
    assert session.post.call_count == 1
    assert generator.stats['failed'] == 1


def test_retained_local_claim_covers_abrupt_exit(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    first = Illustrator(store, at, tmp_path, session=client())
    first.generate = Mock(side_effect=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        first.image(item, True)
    second = Illustrator(store, at+timedelta(minutes=15), tmp_path, session=client())
    assert second.image(item, True) is None
    second.session.post.assert_not_called()
    assert store.rows('SELECT status FROM illustrations')[0]['status'] == 'pending'


def test_calendar_cover_has_no_scene_and_event_slide_reuses_matching_art(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    generator = Illustrator(store, at, tmp_path, session=client())
    post = {'item_id': item['id'], 'kind': 'announcement', 'status': 'prepared'}
    art = generator.for_post(post, {item['id']: item})[0]
    calendar = {'kind':'weekly', 'status':'prepared', 'slides':[{},{}], 'source_urls':[item['url']]}
    assert generator.for_post(calendar, {item['id']: item}) == {1: art}
    assert generator.session.post.call_count == 1


def test_cache_survives_isolated_git_state_restore(tmp_path, event, at, configured, monkeypatch):
    remote = tmp_path/'remote.git'
    subprocess.run(['git','init','--bare',str(remote)], check=True, capture_output=True)
    repo = tmp_path/'repo'
    repo.mkdir()
    subprocess.run(['git','init','-b','main'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git','remote','add','origin',str(remote)], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    path = repo/'state/platform.sqlite'
    store = Store(path)
    item = saved_item(store, event, at)
    assert Illustrator(store, at, tmp_path/'first', session=client()).image(item, True)
    store.close()
    persist(path)
    fresh_path = repo/'fresh/platform.sqlite'
    restore(fresh_path)
    fresh = Store(fresh_path)
    try:
        session = client()
        assert Illustrator(fresh, at+timedelta(minutes=15), tmp_path/'next', session=session).image(fresh.items()[0], True)
        session.post.assert_not_called()
        validate_state(fresh_path)
    finally:
        fresh.close()


def test_state_rejects_image_metadata_and_extra_payload(store, event, at):
    item = saved_item(store, event, at)
    data = clean_image(png())
    secret = b'api_key=PRIVATE_EMBEDDED_SECRET'
    comment = b'\xff\xfe' + (len(secret)+2).to_bytes(2,'big') + secret
    bad = data[:2] + comment + data[2:]
    with store.db:
        store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                         (image_key(item),item['id'],'ready',bad,1,at.isoformat(),at.isoformat()))
    with pytest.raises(ValueError, match='metadata'):
        validate_state(store.path)
    with store.db:
        store.db.execute('UPDATE illustrations SET image=?', (data+b'private trailing data',))
    with pytest.raises(ValueError):
        validate_state(store.path)


def test_prompt_is_bounded_and_no_source_url_or_credentials_are_sent(store, event, at):
    item = saved_item(store, event, at)
    item.update(title='t'*4000, description='d'*4000)
    assert len(STYLE + topic(item)) <= 2048
    assert item['url'] not in STYLE + topic(item)


def test_pruning_bounds_cache_and_drops_revoked_item(store, event, at, tmp_path, configured):
    item = saved_item(store, event, at)
    data = clean_image(png())
    with store.db:
        for index in range(90):
            store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                             (digest(str(index)), item['id'], 'ready', data, 1, at.isoformat(), at.isoformat()))
    generator = Illustrator(store, at, tmp_path, session=client())
    generator.prune({item['id']})
    assert len(store.rows('SELECT id FROM illustrations')) == 80
    validate_state(store.path)
    generator.prune(set())
    assert not store.rows('SELECT id FROM illustrations')


def test_explicit_preview_uploads_only_labelled_cards(tmp_path, configured, monkeypatch):
    from seferihisar.illustrations import preview
    session = client()
    monkeypatch.setattr('seferihisar.illustrations.requests', session)
    preview(tmp_path/'preview')
    assert {p.name for p in (tmp_path/'preview').iterdir()} == {'feed.jpg', 'story.jpg'}
    assert session.post.call_count == 1
