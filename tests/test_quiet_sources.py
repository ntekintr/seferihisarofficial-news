import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.ops_watch import evaluate, notify, quiet
from seferihisar.operations import quiet_sources

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}


def item(store, sid, first, last=None, n=0):
    store.db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?)',
                     (f'{sid}-{n}', 'news', f'fp-{sid}-{n}', json.dumps({'source_id': sid}), 1,
                      first.isoformat(), (last or first).isoformat()))


def health(store, sid, status, at):
    store.db.execute('INSERT OR REPLACE INTO source_health VALUES (?,?,?,?,?,?,?)',
                     (sid, at.isoformat(), status, int(status == 'ok'), 0, int(status == 'failed'), None))


def runs(store, at, *failing):
    for n, ids in enumerate(failing):
        started = at - timedelta(minutes=30 * (len(failing) - n))
        store.db.execute('INSERT INTO runs(started_at,finished_at,errors) VALUES (?,?,?)',
                         (started.isoformat(), (started + timedelta(minutes=10)).isoformat(),
                          json.dumps([{'source_id': sid, 'code': 'source_timeout'} for sid in ids])))


def test_previously_productive_reader_is_quiet_only_after_its_own_window(store, at):
    sources = [{'id': 'broken', 'enabled': True}, {'id': 'fresh', 'enabled': True},
               {'id': 'working', 'enabled': True}, {'id': 'never', 'enabled': True},
               {'id': 'seasonal', 'enabled': True, 'quiet_after_hours': 720},
               {'id': 'finished-request', 'enabled': True, 'requested_until': '2026-10-01T00:00:00+03:00'},
               {'id': 'blocked', 'enabled': True, 'quiet_acknowledged': 'Bulut 403'},
               {'id': 'disabled', 'enabled': False}]
    # A merged duplicate refreshes last_seen; it is not this reader's own new item.
    item(store, 'broken', at - timedelta(hours=100), last=at)
    item(store, 'broken', at - timedelta(hours=80), n=1)
    item(store, 'fresh', at - timedelta(hours=10))
    item(store, 'working', at - timedelta(days=9))
    for sid in ('seasonal', 'finished-request', 'blocked', 'disabled'):
        item(store, sid, at - timedelta(days=5))
    for sid in ('broken', 'fresh', 'never', 'seasonal', 'finished-request', 'disabled'):
        health(store, sid, 'empty', at)
    health(store, 'blocked', 'failed', at)
    health(store, 'working', 'ok', at)
    runs(store, at, *[('blocked',)] * 4)
    store.db.commit()
    assert quiet_sources(store, sources, at) == [
        {'source_id': 'blocked', 'status': 'failed', 'last_new_item_at': (at - timedelta(days=5)).isoformat(), 'acknowledged': True},
        {'source_id': 'broken', 'status': 'empty', 'last_new_item_at': (at - timedelta(hours=80)).isoformat(), 'acknowledged': False}]


def test_failed_reader_counts_only_when_it_failed_in_each_recent_run(store, at):
    sources = [{'id': 'blip', 'enabled': True}, {'id': 'down', 'enabled': True}]
    for sid in ('blip', 'down'):
        item(store, sid, at - timedelta(days=10))
        health(store, sid, 'failed', at)
    # A network blip fails many readers in one run; it must not toggle the alert.
    runs(store, at, ('down', 'blip'), ('down',), ('down', 'blip'), ('down', 'blip'))
    store.db.commit()
    assert [r['source_id'] for r in quiet_sources(store, sources, at)] == ['down']


def test_failure_history_shorter_than_the_window_is_not_enough(store, at):
    item(store, 'down', at - timedelta(days=10))
    health(store, 'down', 'failed', at)
    runs(store, at, ('down',), ('down',))
    store.db.commit()
    assert quiet_sources(store, [{'id': 'down', 'enabled': True}], at) == []


def test_partial_reader_still_yields_and_is_not_quiet(store, at):
    item(store, 'partial', at - timedelta(days=4))
    health(store, 'partial', 'partial', at)
    store.db.commit()
    assert quiet_sources(store, [{'id': 'partial', 'enabled': True}], at) == []


def snapshot(at, rows):
    return {'demo': False, 'runs': [{'finished_at': at.isoformat()}], 'source_health': [{'status': 'ok'}] * 10,
            'publishing_enabled': False, 'quiet_sources': rows}


def test_only_unacknowledged_valid_rows_raise_an_incident(at):
    rows = [{'source_id': 'izmir-belediye', 'status': 'empty', 'last_new_item_at': '2026-10-06T09:19:00+03:00', 'acknowledged': False},
            {'source_id': 'bubilet', 'status': 'failed', 'last_new_item_at': '2026-10-01T01:19:00+03:00', 'acknowledged': True},
            {'source_id': 'Provider <b>text</b>', 'status': 'empty', 'last_new_item_at': '2026-10-06T09:19:00+03:00', 'acknowledged': False},
            {'source_id': 'ege-telgraf', 'status': 'ok', 'last_new_item_at': '2026-10-06T09:19:00+03:00', 'acknowledged': False}]
    assert quiet(snapshot(at, rows)) == [('izmir-belediye', 'empty', '2026-10-06')]
    assert evaluate(snapshot(at, rows), at) == ['source_silent']
    assert evaluate(snapshot(at, rows[1:2]), at) == []
    assert quiet({'quiet_sources': 'not a list'}) == [] and quiet(None) == []


def test_issue_lists_silent_readers_and_updates_when_the_set_changes(at):
    api = Mock()
    api.call.return_value = []
    first = [('izmir-belediye', 'empty', '2026-10-26')]
    assert notify(api, ['source_silent'], at, first) == 'opened'
    body = api.call.call_args.kwargs['json']['body']
    assert '`izmir-belediye`: boş, son yeni kayıt 2026-10-26' in body
    previous = {'number': 7, 'body': body, 'user': {'login': 'github-actions[bot]'}, 'state': 'open'}
    api.reset_mock()
    api.call.return_value = [previous]
    assert notify(api, ['source_silent'], at, first) == 'unchanged'
    assert notify(api, ['source_silent'], at, first + [('seferihisar-hem', 'failed', '2026-10-19')]) == 'updated'
    assert '`seferihisar-hem`: okunamıyor' in api.call.call_args.kwargs['json']['body']
    with pytest.raises(ValueError):
        notify(api, ['source_silent'], at, [('<script>', 'empty', '2026-10-26')])


def test_known_cloud_blocks_and_seasonal_reader_are_configured():
    assert SOURCES['bubilet']['quiet_acknowledged'] and SOURCES['bubilet-bademler']['quiet_acknowledged']
    assert SOURCES['izmir-kultur']['quiet_after_hours'] == 720
    # Regional feed filtered to Seferihisar: 290 h between local items in October.
    assert SOURCES['izmir-belediye']['quiet_after_hours'] == 720
    assert all(isinstance(s.get('quiet_after_hours', 72), int) for s in SOURCES.values())
