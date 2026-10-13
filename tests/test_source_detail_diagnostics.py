import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests

from seferihisar.collect import collect_source, detail_error_code
from seferihisar.pipeline import run
from seferihisar.schedule import prepare
from seferihisar.security import validate_public, validate_state
from seferihisar.store import Store


PRIVATE = 'api_key=PRIVATE_EXCEPTION_VALUE https://example.org/?access_token=PRIVATE_REQUEST_VALUE'


def http_error(status):
    response = requests.Response()
    response.status_code = status
    response.url = 'https://example.org/?access_token=PRIVATE_REQUEST_VALUE'
    response.headers['X-Private'] = PRIVATE
    return requests.HTTPError(PRIVATE, response=response)


@pytest.mark.parametrize(('exc', 'code'), [
    (requests.Timeout(PRIVATE), 'detail_timeout'),
    (requests.ConnectTimeout(PRIVATE), 'detail_timeout'),
    (requests.exceptions.SSLError(PRIVATE), 'detail_tls_failed'),
    (requests.ConnectionError(PRIVATE), 'detail_connection_failed'),
    (http_error(403), 'detail_http_403'),
    (http_error(429), 'detail_http_429'),
    (http_error(503), 'detail_http_503'),
    (ValueError('robots.txt disallows this path'), 'detail_robots_denied'),
    (ValueError('Response too large'), 'detail_response_too_large'),
    (ValueError('Too many redirects'), 'detail_redirect_limit'),
    (requests.HTTPError(PRIVATE), 'detail_check_failed'),
    (http_error(True), 'detail_check_failed'),
    (http_error(650), 'detail_check_failed'),
    (http_error('403'), 'detail_check_failed'),
    (ValueError('robots.txt disallows this path ' + PRIVATE), 'detail_check_failed'),
    (OSError(PRIVATE), 'detail_check_failed'),
])
def test_detail_failure_reports_only_controlled_code_and_keeps_old_event(source, event, exc, code):
    fetcher = Mock()
    fetcher.get.side_effect = [('<html></html>', source['url']), exc]
    before = json.dumps(event, sort_keys=True)
    items, candidates, errors = collect_source(source, fetcher, [event])
    assert not items and not candidates
    assert errors == [{'source_id': source['id'], 'code': code}]
    assert json.dumps(event, sort_keys=True) == before
    assert 'PRIVATE' not in json.dumps(errors)
    assert detail_error_code(exc, calendar=True) == 'calendar_' + code


def test_specific_detail_error_still_blocks_publication_and_never_persists_private_data(tmp_path, source, event, at, monkeypatch, capsys):
    state, public = tmp_path / 'state.sqlite', tmp_path / 'public'
    sources = tmp_path / 'sources.json'
    sources.write_text(json.dumps([source]))
    db = Store(state)
    db.upsert(event, at.isoformat())
    prepare(db, at)
    db.close()
    fetcher = Mock()
    fetcher.get.side_effect = [('<html></html>', source['url']), http_error(403)]
    monkeypatch.setattr('seferihisar.pipeline.Fetcher', lambda _: fetcher)
    run(state, public, sources, at + timedelta(minutes=15))
    db = Store(state)
    assert db.items()[0]['last_seen'] == at.isoformat()
    assert db.posts() and all(p['status'] == 'blocked_source' for p in db.posts())
    assert db.rows('SELECT errors FROM runs')[-1]['errors'] == json.dumps([
        {'source_id': source['id'], 'code': 'detail_http_403'}])
    db.close()
    exported = json.loads((public / 'data.json').read_text())
    assert exported['source_health'][0]['status'] == 'partial'
    assert exported['events'][0]['source_current'] is False
    assert all(not p['assets'] for p in exported['posts'])
    assert b'PRIVATE_' not in state.read_bytes()
    assert 'PRIVATE_' not in (public / 'data.json').read_text()
    assert 'PRIVATE_' not in capsys.readouterr().out
    validate_state(state)
    validate_public(public)

