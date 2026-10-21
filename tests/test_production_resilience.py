import io
import json
import zipfile
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests

from seferihisar.delivery_audit import feed_result, facebook_story_result, refresh, validate_row, summary, ReadError
from seferihisar.domain import digest
from seferihisar.ops_watch import evaluate, notify, MARKER
from seferihisar.security import validate_state
from seferihisar.state_backup import create, restore_drill
from seferihisar.backup_history import drill


def response(value, code=200):
    return Mock(ok=code < 300, status_code=code, json=lambda: value)


def claim(store, at, kind='feed', media='111'):
    parent = {'id': digest('parent'), 'item_id': digest('item'), 'revision': 1, 'kind': 'news',
              'due_at': at.isoformat(), 'published_at': at.isoformat(), 'caption': 'Yerel haber\n\nKaynak: kurum', 'category': 'culture'}
    store.queue(parent)
    store.db.execute("UPDATE posts SET status='published',media_id='111' WHERE id=?", (parent['id'],))
    if kind == 'story':
        child = {**parent, 'id': digest('child'), 'publish_format': 'story', 'parent_post_id': parent['id'], 'story_index': 0}
        store.queue(child)
        store.db.execute("UPDATE posts SET status='published',media_id=? WHERE id=?", (media, child['id']))
    store.db.commit()
    return parent


def test_actual_feed_caption_and_timestamp_are_checked_without_changing_claim(store, at):
    p = claim(store, at)
    before = store.rows('SELECT * FROM posts')
    session = Mock()
    session.get.side_effect = [response({'id': '123', 'username': 'seferihisarofficial'}),
                              response({'id': '111', 'caption': p['caption'], 'timestamp': at.isoformat()})]
    value = refresh(store, at + timedelta(minutes=3), session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['results'] == {'present': 1}
    assert store.rows('SELECT * FROM posts') == before
    assert session.get.call_count == 2
    session.post.assert_not_called()
    for call in session.get.call_args_list:
        assert call.kwargs['allow_redirects'] is False
        assert 'synthetic' not in call.args[0] and 'access_token' not in call.kwargs['params']
    assert 'synthetic' not in json.dumps(store.rows('SELECT * FROM delivery_audits'))
    validate_state(store.path)
    refresh(store, at + timedelta(minutes=30), session=session, environ={})
    assert session.get.call_count == 2


@pytest.mark.parametrize('change,result', [({'id': '222'}, 'not_visible'),
    ({'caption': 'Başka haber'}, 'caption_mismatch'), ({'timestamp': '2025-01-01T00:00:00+03:00'}, 'timestamp_mismatch'),
    ({'timestamp': None}, 'timestamp_mismatch')])
def test_mismatched_real_delivery_is_not_success(at, change, result):
    value = {'id': '111', 'caption': 'Caption', 'timestamp': at.isoformat(), **change}
    assert feed_result(value, '111', 'Caption', at, 'caption') == result


def test_expired_story_does_not_become_a_false_missing_alert(store, at):
    claim(store, at - timedelta(hours=25), 'story', '222')
    session = Mock()
    session.get.side_effect = [response({'id': '123', 'username': 'seferihisarofficial'}),
                              response({'id': '111', 'caption': 'Yerel haber\n\nKaynak: kurum', 'timestamp': (at - timedelta(hours=25)).isoformat()})]
    value = refresh(store, at + timedelta(minutes=3), session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['results'] == {'present': 1, 'expired_not_checked': 1}
    assert value['recent_failures'] == 0
    assert session.get.call_count == 2


def test_active_story_must_be_in_this_accounts_list(store, at):
    p = claim(store, at, 'story', '222')
    session = Mock()
    session.get.side_effect = [response({'id': '123', 'username': 'seferihisarofficial'}),
                              response({'id': '111', 'caption': p['caption'], 'timestamp': at.isoformat()}),
                              response({'data': [{'id': '333'}]})]
    value = refresh(store, at + timedelta(minutes=3), session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['results'] == {'present': 1, 'not_visible': 1}
    assert value['recent_failures'] == 1


def test_weather_audit_without_facebook_credentials_does_not_damage_facebook_observations(store, at):
    p = claim(store, at)
    store.db.execute('INSERT INTO facebook_deliveries VALUES (?,?,?,?,?,?,?,?,?)',
        (digest('fb'), p['id'], '555', 'feed', 'published', at.isoformat(), at.isoformat(), '[]', '555_777'))
    store.db.commit()
    refresh(store, at + timedelta(minutes=3), environ={})
    assert not store.rows("SELECT * FROM delivery_audits WHERE channel='facebook'")
    assert store.rows('SELECT * FROM facebook_deliveries')[0]['status'] == 'published'


def test_meta_error_is_controlled_and_never_replayed(store, at):
    claim(store, at)
    session = Mock()
    session.get.return_value = response({'error': {'code': 190, 'message': 'PRIVATE_CONTENT'}}, 400)
    value = refresh(store, at + timedelta(minutes=3), session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['results'] == {'credential_invalid': 1}
    assert 'PRIVATE_CONTENT' not in json.dumps(store.rows('SELECT * FROM delivery_audits'))
    session.post.assert_not_called()


def test_first_three_minutes_wait_for_provider_propagation(store, at):
    claim(store, at)
    session = Mock()
    assert refresh(store, at + timedelta(minutes=2), environ={}, session=session)['results'] == {}
    session.get.assert_not_called()


def test_facebook_story_matches_own_page_post_id_status_and_time_without_replay(store, at):
    p = claim(store, at)
    store.db.execute('INSERT INTO facebook_deliveries VALUES (?,?,?,?,?,?,?,?,?)',
        (digest('fb-story'), p['id'], '555', 'story', 'published', at.isoformat(), at.isoformat(), '[]', '777'))
    store.db.commit()
    before = store.rows('SELECT * FROM facebook_deliveries')
    session = Mock()
    session.get.side_effect = [response({'id': '123', 'username': 'seferihisarofficial'}),
                              response({'id': '111', 'caption': p['caption'], 'timestamp': at.isoformat()}),
                              response({'id': '555', 'instagram_business_account': {'id': '123'}}),
                              response({'data': [{'post_id': '777', 'status': 'published', 'creation_time': str(int(at.timestamp()))}]})]
    value = refresh(store, at + timedelta(minutes=3), session=session,
        environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic',
                 'FACEBOOK_PUBLISH_ENABLED': 'true', 'FACEBOOK_PAGE_ID': '555', 'FACEBOOK_PAGE_ACCESS_TOKEN': 'synthetic-page'})
    assert value['results'] == {'present': 2}
    assert value['image_pixels_inspected'] is False and value['republishing_allowed'] is False
    assert store.rows('SELECT * FROM facebook_deliveries') == before
    assert session.get.call_count == 4
    assert session.get.call_args.args[0].endswith('/555/stories')
    assert session.get.call_args.kwargs['params']['fields'] == 'post_id,status,creation_time'
    session.post.assert_not_called()


@pytest.mark.parametrize('row,result', [
    ({'id': '777', 'post_id': '888', 'status': 'published'}, 'not_visible'),
    ({'post_id': '777', 'status': 'ARCHIVED'}, 'not_visible'),
    ({'post_id': '777', 'status': 'published', 'creation_time': None}, 'timestamp_mismatch'),
    ({'post_id': '777', 'status': 'published', 'creation_time': '999999999999'}, 'timestamp_mismatch'),
    ({'post_id': '777', 'status': 'published', 'creation_time': '2025-01-01T10:00:00Z'}, 'timestamp_mismatch'),
])
def test_facebook_story_never_confuses_object_id_old_or_unpublished_story(at, row, result):
    assert facebook_story_result([row], '777', at) == result


def test_facebook_story_invalid_provider_list_is_unavailable_not_missing(at):
    for rows in ({'post_id': '777'}, [{'id': '777'}], [None]):
        with pytest.raises(ReadError, match='story_read_unavailable'):
            facebook_story_result(rows, '777', at)


def test_legacy_story_failure_is_rechecked_once_and_edge_failure_keeps_cooldown(store, at):
    p = claim(store, at)
    for key in (digest('fb-story'), digest('fb-story-2')):
        store.db.execute('INSERT INTO facebook_deliveries VALUES (?,?,?,?,?,?,?,?,?)',
            (key, p['id'], '555', 'story', 'published', at.isoformat(), at.isoformat(), '[]', '777'))
        store.db.execute('INSERT INTO delivery_audits VALUES (?,?,?,?,?)',
            (digest('facebook:' + key), 'facebook', 'story', at.isoformat(), 'read_failed'))
    store.db.execute('INSERT INTO delivery_audits VALUES (?,?,?,?,?)',
        (digest('instagram:' + p['id']), 'instagram', 'feed', at.isoformat(), 'present'))
    store.db.commit()
    session = Mock()
    session.get.side_effect = [response({'id': '555', 'instagram_business_account': {'id': '123'}}),
                              response({'error': {'code': 100}}, 400)]
    env = {'INSTAGRAM_USER_ID': '123', 'FACEBOOK_PUBLISH_ENABLED': 'true',
           'FACEBOOK_PAGE_ID': '555', 'FACEBOOK_PAGE_ACCESS_TOKEN': 'synthetic'}
    result = refresh(store, at + timedelta(minutes=10), session=session, environ=env)
    assert result['results'] == {'present': 1, 'story_read_unavailable': 2}
    assert session.get.call_count == 2
    refresh(store, at + timedelta(minutes=30), session=session, environ=env)
    assert session.get.call_count == 2
    session.post.assert_not_called()
    validate_state(store.path)


def healthy(at):
    return {'demo': False, 'runs': [{'finished_at': at.isoformat()}],
            'source_health': [{'status': 'ok'}] * 10, 'publishing_enabled': True,
            'weather_story': {'day': at.date().isoformat(), 'status': 'published'},
            'operations': {'unresolved': {'instagram': 0, 'facebook': 0}}}


def test_monitor_distinguishes_empty_sources_from_failure_and_waiting_from_missing_weather(at):
    v = healthy(at)
    v['source_health'] = [{'status': 'empty'}] * 10
    assert evaluate(v, at) == []
    v['weather_story'] = {'day': at.date().isoformat(), 'status': 'prepared'}
    assert 'weather_missing' in evaluate(v, at)
    assert 'weather_missing' not in evaluate(v, at.replace(hour=8, minute=30))
    v['runs'][0]['finished_at'] = (at - timedelta(hours=2)).isoformat()
    assert 'research_stale' in evaluate(v, at)
    v['source_health'] = [{'status': 'failed'}] * 4 + [{'status': 'ok'}] * 6
    assert 'source_coverage_drop' in evaluate(v, at)


def test_alert_is_owner_assigned_and_deduplicated(at):
    api = Mock()
    api.call.return_value = []
    assert notify(api, ['research_stale'], at) == 'opened'
    data = api.call.call_args.kwargs['json']
    assert data['assignees'] == ['ntekintr'] and MARKER in data['body']
    previous = {'number': 42, 'body': data['body'], 'user': {'login': 'github-actions[bot]'}, 'state': 'open'}
    api.reset_mock()
    api.call.return_value = [previous]
    assert notify(api, ['research_stale'], at + timedelta(hours=1)) == 'unchanged'
    assert api.call.call_count == 1
    assert notify(api, [], at + timedelta(hours=1)) == 'resolved'
    assert api.call.call_args.args[1] == 'issues/42/comments'


def test_monitor_does_not_modify_user_issues_or_send_when_healthy(at):
    api = Mock()
    api.call.return_value = [{'number': 1, 'body': MARKER, 'user': {'login': 'someone'}, 'state': 'open'}]
    assert notify(api, [], at) == 'healthy_no_issue'
    assert api.call.call_count == 1
    with pytest.raises(ValueError):
        notify(api, ['PRIVATE_PROVIDER_TEXT'], at)


def test_backup_is_consistent_restorable_and_does_not_change_live_database(store, at, tmp_path):
    claim(store, at)
    before = store.path.read_bytes()
    archive = tmp_path / 'state.zip'
    result = create(store.path, archive, at, 'a' * 40)
    assert result['integrity'] == 'ok' and result['restored_in_isolation']
    assert result['production_modified'] is False and result['provider_independent'] is False
    assert store.path.read_bytes() == before
    assert restore_drill(archive) == result


def test_backup_rejects_changed_or_unexpected_archive_members(store, at, tmp_path):
    original = tmp_path / 'original.zip'
    create(store.path, original, at, 'a' * 40)
    with zipfile.ZipFile(original) as source:
        manifest = json.loads(source.read('manifest.json'))
        payload = source.read('platform.sqlite')
    changed = tmp_path / 'changed.zip'
    manifest['sha256'] = '0' * 64
    with zipfile.ZipFile(changed, 'w') as target:
        target.writestr('manifest.json', json.dumps(manifest))
        target.writestr('platform.sqlite', payload)
    with pytest.raises(ValueError, match='differs'):
        restore_drill(changed)
    with zipfile.ZipFile(changed, 'a') as target:
        target.writestr('../outside', 'x')
    with pytest.raises(ValueError, match='Unexpected'):
        restore_drill(changed)


def test_first_backup_does_not_fabricate_a_historical_restore(at):
    api = Mock()
    api.call.return_value = {'artifacts': []}
    session = Mock()
    assert drill(api, session, at, '1')['status'] == 'previous_day_backup_not_yet_available'
    session.get.assert_not_called()
