"""An uncertain Facebook claim that never reached a publish call (16 Nov 2026)."""
import requests

from seferihisar.facebook import publish_recent
from seferihisar.operations import facebook_never_sent, summary
from seferihisar.ops_watch import evaluate
from tests.test_facebook_publication import api, setup_content


def test_failed_first_upload_is_not_sent_and_never_retried(store, at):
    assets, key = setup_content(store, at)
    adapter = api()
    adapter.upload.side_effect = requests.Timeout('must not reach logs')
    assert publish_recent(store, at, 'https://example.org/', assets, adapter)['status'] == 'uncertain'
    [row] = store.rows('SELECT status,photo_ids,media_id FROM facebook_deliveries')
    assert facebook_never_sent(row)
    result = summary(store, at)
    assert result['unresolved']['facebook'] == 0 and result['not_sent']['facebook'] == 1
    # The claim keeps its key: no second upload, no publish call.
    assert publish_recent(store, at, 'https://example.org/', assets, adapter)['status'] == 'awaiting_resolution'
    assert adapter.upload.call_count == 1
    adapter.publish.assert_not_called()


def test_failure_after_an_upload_stays_unresolved(store, at):
    assets, key = setup_content(store, at)
    adapter = api()
    adapter.publish.side_effect = requests.Timeout('must not reach logs')
    assert publish_recent(store, at, 'https://example.org/', assets, adapter)['status'] == 'uncertain'
    [row] = store.rows('SELECT status,photo_ids,media_id FROM facebook_deliveries')
    assert not facebook_never_sent(row)
    result = summary(store, at)
    assert result['unresolved']['facebook'] == 1 and result['not_sent']['facebook'] == 0


def test_in_flight_or_published_rows_are_never_called_not_sent():
    assert not facebook_never_sent({'status': 'publishing', 'photo_ids': '[]', 'media_id': None})
    assert not facebook_never_sent({'status': 'published', 'photo_ids': '["1"]', 'media_id': '2'})
    assert not facebook_never_sent({'status': 'uncertain', 'photo_ids': 'not json', 'media_id': None})


def test_operations_watch_no_longer_alarms_on_a_not_sent_claim(store, at):
    assets, key = setup_content(store, at)
    adapter = api()
    adapter.upload.side_effect = requests.Timeout('must not reach logs')
    publish_recent(store, at, 'https://example.org/', assets, adapter)
    snapshot = {'demo': False, 'publishing_enabled': True,
                'runs': [{'finished_at': at.isoformat()}], 'operations': summary(store, at)}
    assert 'unresolved_delivery' not in evaluate(snapshot, at)
