import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from seferihisar.collect import Fetcher, collect_source
from seferihisar.instagram import publish_one
from seferihisar.pipeline import export, run
from seferihisar.schedule import prepare
from seferihisar.security import contains_secret, validate_public, validate_state
from seferihisar.store import Store

SOURCES = Path('config/sources.json')


def test_all_sources_offline_produces_no_content_or_ai(tmp_path, at, monkeypatch, capsys):
    collect = Mock(side_effect=requests.ConnectionError('api_key=PRIVATE_EXCEPTION_VALUE'))
    ai = Mock()
    monkeypatch.setattr('seferihisar.pipeline.collect_source', collect)
    monkeypatch.setattr('seferihisar.pipeline.ai_priority', ai)
    result = run(tmp_path/'state.sqlite', tmp_path/'public', SOURCES, at)
    data = json.loads((tmp_path/'public/data.json').read_text())
    assert result['collected'] == result['prepared'] == 0
    assert result['errors'] == sum(s.get('enabled', False) for s in json.loads(SOURCES.read_text()))
    assert data['news'] == data['events'] == data['posts'] == []
    ai.assert_not_called()
    assert 'PRIVATE_EXCEPTION_VALUE' not in (tmp_path/'public/data.json').read_text()
    assert b'PRIVATE_EXCEPTION_VALUE' not in (tmp_path/'state.sqlite').read_bytes()
    assert 'PRIVATE_EXCEPTION_VALUE' not in capsys.readouterr().out


def test_offline_source_blocks_existing_posts_and_new_event_day_reminder(tmp_path, at, event, monkeypatch):
    db_path, public = tmp_path/'state.sqlite', tmp_path/'public'
    db = Store(db_path)
    db.upsert(event, at.isoformat())
    prepare(db, at)
    initial_ids = {p['id'] for p in db.posts()}
    db.close()
    monkeypatch.setattr('seferihisar.pipeline.collect_source', Mock(side_effect=requests.Timeout()))
    run(db_path, public, SOURCES, at + timedelta(minutes=15))
    db = Store(db_path)
    assert {p['id'] for p in db.posts()} == initial_ids
    assert all(p['status'] == 'blocked_source' for p in db.posts())
    assert db.items()[0]['last_seen'] == at.isoformat()
    data = json.loads((public/'data.json').read_text())
    assert not data['events'][0]['source_current']
    assert all(not p['assets'] for p in data['posts'])
    assert b'STATUS:TENTATIVE' in (public/'events.ics').read_bytes()
    api = Mock()
    api.enabled.return_value = True
    assert publish_one(db, at+timedelta(minutes=15), 'https://example.org/', {}, adapter=api)['status']=='empty'
    api.container.assert_not_called()
    db.close()
    run(db_path, public, SOURCES, at+timedelta(days=3))
    db = Store(db_path)
    assert not any(p['kind']=='reminder_day' for p in db.posts())
    assert not any(p['status']=='prepared' for p in db.posts())
    db.close()


def test_recovered_source_rearms_only_current_content(tmp_path,at,event,monkeypatch):
    path=tmp_path/'state.sqlite'
    db=Store(path)
    db.upsert(event,at.isoformat())
    prepare(db,at)
    db.close()
    monkeypatch.setattr('seferihisar.pipeline.collect_source',Mock(side_effect=requests.Timeout()))
    run(path,tmp_path/'public',SOURCES,at+timedelta(minutes=15))
    monkeypatch.setattr('seferihisar.pipeline.collect_source',lambda s,f,k: ([event],[],[]) if s['id']==event['source_id'] else ([],[],[]))
    run(path,tmp_path/'public',SOURCES,at+timedelta(days=3))
    db=Store(path)
    assert any(p['kind']=='reminder_day' and p['status']=='prepared' for p in db.posts())
    assert not any(p['kind']=='reminder_3d' and p['status']=='prepared' for p in db.posts())
    assert db.items()[0]['revision']==1
    db.close()


def test_missing_page_never_infers_cancellation_or_renews_verification(source,event):
    fetcher=Mock()
    fetcher.get.side_effect=[('<html></html>',source['url']),requests.HTTPError('404')]
    items,candidates,errors=collect_source(source,fetcher,[event])
    assert not items and errors==[{'source_id':source['id'],'code':'detail_check_failed'}]
    assert event['status']=='scheduled'


def test_blocked_robots_makes_no_article_request(source,monkeypatch):
    fetcher=Fetcher([source])
    request=Mock(return_value=('User-agent: *\nDisallow: /', 'https://seferihisar.bel.tr/robots.txt'))
    monkeypatch.setattr(fetcher,'request',request)
    with pytest.raises(ValueError,match='robots'):
        fetcher.get(source['url'])
    assert request.call_count==1


def test_unknown_fields_are_never_persisted_or_exported(tmp_path,event,at):
    event['internal_note']='UNPUBLISHED_PRIVATE_DETAILS'
    fixture=tmp_path/'input.json'
    fixture.write_text(json.dumps([event]))
    run(tmp_path/'state.sqlite',tmp_path/'public',SOURCES,at,fixture)
    assert 'UNPUBLISHED_PRIVATE_DETAILS' not in (tmp_path/'public/data.json').read_text()
    assert b'UNPUBLISHED_PRIVATE_DETAILS' not in (tmp_path/'state.sqlite').read_bytes()
    data=json.loads((tmp_path/'public/data.json').read_text())
    assert 'identity' not in data['events'][0]


@pytest.mark.parametrize('field', ['description','organizer','identity','ticket_url'])
def test_configured_secret_in_any_payload_never_leaves_memory(tmp_path,event,at,monkeypatch,field):
    secret='SYNTHETIC_REVIEW_SECRET_0123456789'
    monkeypatch.setenv('GEMINI_API_KEY',secret)
    event[field]='https://seferihisar.bel.tr/'+secret if field in ('identity','ticket_url') else secret
    fixture=tmp_path/'input.json'
    fixture.write_text(json.dumps([event]))
    run(tmp_path/'state.sqlite',tmp_path/'public',SOURCES,at,fixture)
    assert secret not in (tmp_path/'public/data.json').read_text()
    assert secret.encode() not in (tmp_path/'state.sqlite').read_bytes()
    assert not list((tmp_path/'public').rglob('*.jpg'))


def test_clean_pages_rebuild_drops_dotfiles_database_logs_and_stale_media(store,event,at,tmp_path):
    public=tmp_path/'public'
    public.mkdir()
    for name in ('.env','credentials.json','platform.sqlite','debug.log'):
        (public/name).write_text('PRIVATE_OLD_FILE')
    stale=public/'media/private'
    stale.mkdir(parents=True)
    (stale/'secret.jpg').write_bytes(b'private')
    store.upsert(event,at.isoformat())
    prepare(store,at)
    export(store,public,json.loads(SOURCES.read_text()),at)
    validate_public(public)
    assert not stale.exists()
    assert not any((public/name).exists() for name in ('.env','credentials.json','platform.sqlite','debug.log'))
    assert not list(public.rglob('*.sqlite'))


def test_state_guard_refuses_private_fields_or_secret_like_text(store,event,at):
    event['internal_note']='private'
    store.upsert(event,at.isoformat())
    with pytest.raises(ValueError,match='payload fields'):
        validate_state(store.path)


def test_public_guard_rejects_unexpected_files(tmp_path):
    (tmp_path/'.env').write_text('private')
    with pytest.raises(ValueError,match='Unexpected file'):
        validate_public(tmp_path)


def test_no_credential_literals_in_production_source():
    roots=[Path('seferihisar'),Path('config'),Path('site'),Path('.github/workflows')]
    for root in roots:
        for path in root.rglob('*'):
            if path.is_file() and path.suffix in ('.py','.json','.html','.js','.css','.yml'):
                assert not contains_secret(path.read_text()),str(path)


def test_stale_event_without_recent_evidence_cannot_create_reminders(store,event,at):
    store.upsert(event,(at-timedelta(hours=2)).isoformat())
    prepare(store,at)
    assert not store.posts()


def test_published_parent_cannot_spawn_stories_from_a_stale_source(store,event,at):
    store.upsert(event,at.isoformat())
    prepare(store,at)
    parent=next(p for p in store.posts() if p['kind']=='announcement')
    parent['published_at']=at.isoformat()
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",(json.dumps(parent),parent['id']))
    api=Mock()
    api.enabled.return_value=True
    result=publish_one(store,at+timedelta(hours=2),'https://example.org/',{parent['id']:{'story':['media/a/story-1.jpg']}},story=True,adapter=api)
    assert result['status']=='empty'
    api.container.assert_not_called()
