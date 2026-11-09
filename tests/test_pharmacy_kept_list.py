"""Isparta, 7 Nov 2026: an unreachable source must not withdraw today's verified list."""
from datetime import datetime, timedelta
import json
from unittest.mock import Mock

import pytest
import requests

from seferihisar import pharmacy as module
from seferihisar.collect import PublicDNSLookupError
from seferihisar.domain import TZ
from seferihisar.pharmacy_data import fresh, make_bulletin, profile
from seferihisar.store import Store

PREPARED = datetime(2026, 11, 7, 16, 17, tzinfo=TZ)
FAILED_READ = datetime(2026, 11, 7, 17, 2, tzinfo=TZ)


def bulletin(at, name='AKBAŞ ECZANESİ'):
    return make_bulletin([dict(name=name, address='Davraz Mahallesi 104. Cadde No:44', phone='02462186618',
                               region='MERKEZ' if profile()['city'] == 'isparta' else 'SEFERİHİSAR', note='')],
                         at.date(), at)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'state.sqlite')
    yield s
    s.close()


def prepare(store, value):
    with store.db:
        store.db.execute('INSERT INTO pharmacy_stories(day,bulletin,status,checked_at,last_result) VALUES(?,?,?,?,?)',
                         (value['date'], json.dumps(value, ensure_ascii=False, sort_keys=True), 'prepared',
                          value['checked_at'], 'prepared'))


def row(store):
    return store.rows('SELECT * FROM pharmacy_stories')[0]


def unreachable(monkeypatch, error):
    monkeypatch.setattr('seferihisar.pharmacy_source.fetch_bulletin', Mock(side_effect=error))


@pytest.mark.parametrize('error', [
    requests.Timeout('read timed out'),
    requests.ConnectionError('reset'),
    PublicDNSLookupError('dns'),
    requests.HTTPError('503', response=Mock(status_code=503)),
    OSError('network unreachable'),
])
def test_unreachable_source_keeps_todays_verified_list(store, monkeypatch, error):
    value = bulletin(PREPARED)
    prepare(store, value)
    unreachable(monkeypatch, error)
    module.refresh(store, FAILED_READ)
    r = row(store)
    assert r['status'] == 'prepared' and json.loads(r['bulletin']) == value
    assert r['last_result'] == 'source_unavailable'
    assert r['checked_at'] == value['checked_at']  # The next run reads the source again.


def test_kept_list_stays_publishable_for_the_whole_window(store, monkeypatch):
    value = bulletin(PREPARED)
    prepare(store, value)
    unreachable(monkeypatch, requests.Timeout('read timed out'))
    for minute in (2, 32, 56):
        module.refresh(store, FAILED_READ.replace(minute=minute))
    for at in (datetime(2026, 11, 7, 17, 0, tzinfo=TZ), datetime(2026, 11, 7, 17, 59, 59, tzinfo=TZ)):
        assert fresh(json.loads(row(store)['bulletin']), at)
    assert fresh(bulletin(datetime(2026, 11, 7, 16, 0, tzinfo=TZ)), datetime(2026, 11, 7, 17, 59, 59, tzinfo=TZ))


def test_an_answer_with_another_date_still_withdraws_the_list(store, monkeypatch):
    prepare(store, bulletin(PREPARED))
    unreachable(monkeypatch, ValueError('Official duty date is stale'))
    module.refresh(store, FAILED_READ)
    r = row(store)
    assert r['status'] == 'blocked' and r['bulletin'] is None


def test_an_unreachable_source_with_no_fresh_list_still_blocks(store, monkeypatch):
    prepare(store, bulletin(FAILED_READ - timedelta(minutes=121)))
    unreachable(monkeypatch, requests.Timeout('read timed out'))
    module.refresh(store, FAILED_READ)
    assert row(store)['status'] == 'blocked'
    with store.db:
        store.db.execute('DELETE FROM pharmacy_stories')
    module.refresh(store, FAILED_READ)
    r = row(store)
    assert r['status'] == 'blocked' and r['last_result'] == 'source_unavailable'


def test_a_later_good_read_replaces_the_kept_list(store, monkeypatch):
    prepare(store, bulletin(PREPARED))
    unreachable(monkeypatch, requests.Timeout('read timed out'))
    module.refresh(store, FAILED_READ)
    newer = bulletin(FAILED_READ + timedelta(minutes=20), name='YENİ ECZANESİ')
    monkeypatch.setattr('seferihisar.pharmacy_source.fetch_bulletin', Mock(return_value=newer))
    module.refresh(store, FAILED_READ + timedelta(minutes=20))
    r = row(store)
    assert r['status'] == 'prepared' and r['last_result'] == 'prepared' and json.loads(r['bulletin']) == newer


@pytest.mark.parametrize('status', ['publishing', 'published', 'uncertain'])
def test_a_claimed_list_is_never_touched(store, monkeypatch, status):
    prepare(store, bulletin(PREPARED))
    with store.db:
        store.db.execute('UPDATE pharmacy_stories SET status=?, published_at=?', (status, PREPARED.isoformat()))
    before = store.rows('SELECT * FROM pharmacy_stories')
    unreachable(monkeypatch, requests.Timeout('read timed out'))
    module.refresh(store, FAILED_READ)
    assert store.rows('SELECT * FROM pharmacy_stories') == before
