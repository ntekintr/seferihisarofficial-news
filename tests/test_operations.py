import json
import sys
from datetime import timedelta
from unittest.mock import Mock

import pytest

from seferihisar.domain import parse_date
from seferihisar.operations import failed, record_check, safe_result, summary
from seferihisar.security import validate_state
from seferihisar.store import Store


def test_check_history_is_durable_bounded_and_has_no_untrusted_fields(store, at):
    for i in range(105):
        record_check(store, {'status': 'outside_window', 'caption': 'PRIVATE_PAYLOAD',
            'post_id': 'PRIVATE_ID', 'facebook': {'status': 'empty', 'body': 'PRIVATE_BODY'}}, at + timedelta(minutes=i), 'automatic')
    validate_state(store.path)
    with StoreContext(store.path) as reopened:
        rows = reopened.rows('SELECT * FROM publication_checks')
        assert len(rows) == 100
        assert rows[0]['checked_at'] == (at + timedelta(minutes=5)).isoformat()
        assert json.loads(rows[-1]['result']) == {'status': 'outside_window', 'facebook': {'status': 'empty'}}
    assert 'PRIVATE_' not in json.dumps(rows)


class StoreContext:
    def __init__(self, path):
        self.store = Store(path)
    def __enter__(self):
        return self.store
    def __exit__(self, *args):
        self.store.close()


@pytest.mark.parametrize('result', [
    {'status': 'api_key=PRIVATE_VALUE'}, {'status': []}, {'status': 'complete', 'story': {}},
    {'status': 'complete', 'facebook': {'status': 'complete', 'facebook': {'status': 'uncertain'}}},
])
def test_only_known_statuses_can_enter_check_log(result):
    value = safe_result(result)
    from seferihisar.operations import validate_result
    validate_result(value)
    assert 'PRIVATE_VALUE' not in json.dumps(value)
    assert not value.get('facebook', {}).get('facebook')


@pytest.mark.parametrize('payload', [
    {'status': 'complete', 'url': 'https://example.org/'}, {'status': []},
    {'status': 'complete', 'facebook': {'status': 'complete', 'facebook': {'status': 'empty'}}},
])
def test_state_writer_refuses_injected_extra_fields_or_statuses(store, at, payload):
    with store.db:
        store.db.execute('INSERT INTO publication_checks(checked_at,mode,result) VALUES(?,?,?)', (at.isoformat(), 'automatic', json.dumps(payload)))
    with pytest.raises(ValueError):
        validate_state(store.path)


def test_summary_uses_turkish_publication_day_and_utc_illustration_day(store):
    at = parse_date('2026-10-15T02:06:00+03:00')
    store.queue({'id': 'a'*24, 'title': 'Frozen', 'kind': 'news', 'source_urls': [],
                 'due_at': at.isoformat(), 'published_at': at.isoformat()})
    with store.db:
        store.db.execute("UPDATE posts SET status='uncertain'")
        store.db.execute('INSERT INTO illustration_days VALUES(?,?)', ('2026-10-14', 20))
    before = store.rows('SELECT * FROM posts')
    result = summary(store, at)
    assert result['today']['instagram_feed'] == 1 and result['unresolved']['instagram'] == 1
    assert result['illustrations'] == {'utc_day':'2026-10-14','attempts':20,'limit':20,'remaining':0,'reset_at':'2026-10-15T03:00:00+03:00'}
    assert result['window_start'] == '2026-10-15T08:30:00+03:00'
    assert result['window_open'] is False
    assert summary(store, parse_date('2026-10-15T08:50:00+03:00'))['window_open'] is True
    assert summary(store, parse_date('2026-10-15T22:00:00+03:00'))['window_start'] == '2026-10-16T08:30:00+03:00'
    assert store.rows('SELECT * FROM posts') == before


@pytest.mark.parametrize('result,critical', [
    ({'status':'outside_window', 'facebook':{'status':'empty'}}, False),
    ({'status':'daily_limit'}, False), ({'status':'complete','facebook':{'status':'disabled'}}, False),
    ({'status':'story_pending','story':'rate_limited'}, False),
    ({'status':'complete','facebook':{'status':'story_pending','story':'uncertain'}}, True),
    ({'status':'media_not_deployed'}, True), ({'status':'awaiting_resolution'}, True),
])
def test_waits_are_distinct_from_failures(result, critical):
    assert failed(result) is critical


@pytest.mark.parametrize('status,exit_code', [('outside_window', None), ('uncertain', 1)])
def test_cli_records_outcome_and_marks_failure_without_republishing(store, at, tmp_path, monkeypatch, status, exit_code):
    from seferihisar.cli import main
    public = tmp_path/'public'; public.mkdir()
    (public/'data.json').write_text(json.dumps({'demo':False, 'posts':[]}))
    report = tmp_path/'summary.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(report))
    monkeypatch.delenv('STATE_GIT_CHECKPOINT', raising=False)
    publish = Mock(return_value={'status':status})
    monkeypatch.setattr('seferihisar.instagram.publish_automatic', publish)
    monkeypatch.setattr('seferihisar.facebook.publish_recent', Mock(return_value={'status':'disabled'}))
    monkeypatch.setattr(sys, 'argv', ['cli', 'publish', '--automatic', '--db', str(store.path), '--public', str(public), '--at', at.isoformat()])
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == exit_code
    else:
        main()
    publish.assert_called_once()
    assert json.loads(store.rows('SELECT result FROM publication_checks')[0]['result'])['status'] == status
    assert status in report.read_text(encoding='utf-8')
    validate_state(store.path)
