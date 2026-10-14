import json
import socket
import ssl
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NameResolutionError, SSLError

from seferihisar.collect import Fetcher, PublicDNSLookupError, collect_source, detail_error_code, safe_url
from seferihisar.pipeline import run, source_error_code
from seferihisar.source_catalog import public_catalog
from seferihisar.store import Store

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
CATALOG = {s['id']: s for s in json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))}
PRIVATE = 'access_token=PRIVATE_VALUE'


def http_error(status):
    response = requests.Response(); response.status_code = status
    return requests.HTTPError(PRIVATE, response=response)


def wp_item():
    return json.dumps([{'status':'publish', 'date_gmt':'2026-10-10T06:00:00',
                       'link':'https://menderes.bel.tr/ozdere-programi/',
                       'title':{'rendered':'Özdere için yeni konser programı'},
                       'content':{'rendered':'Özdere ve Menderes mahallelerinde belediyenin yeni konser programı açıklandı. ' * 3}}])


@pytest.mark.parametrize('bad_first', [True, False])
def test_one_broken_list_does_not_discard_the_other_reviewed_list(bad_first):
    source = SOURCES['menderes-belediye']
    good = (wp_item(), source['listing_urls'][1])
    fetcher = Mock()
    fetcher.get.side_effect = [http_error(503), good] if bad_first else [good, http_error(503)]
    items, _, errors = collect_source(source, fetcher, [])
    assert len(items) == 1 and items[0]['url'] == 'https://menderes.bel.tr/ozdere-programi/'
    assert fetcher.get.call_args_list == [call(url) for url in source['listing_urls']]
    assert errors == [{'source_id':source['id'], 'code':'listing_http_503'}]
    assert PRIVATE not in json.dumps(errors)


def test_all_broken_lists_remain_a_source_failure():
    first = http_error(503)
    fetcher = Mock(); fetcher.get.side_effect = [first, http_error(500)]
    with pytest.raises(requests.HTTPError) as failure:
        collect_source(SOURCES['menderes-belediye'], fetcher, [])
    assert failure.value is first and fetcher.get.call_count == 2


def test_bad_json_list_is_not_a_healthy_empty_result():
    source = SOURCES['menderes-belediye']
    fetcher = Mock(); fetcher.get.side_effect = [('<html>Unavailable</html>', source['url']), (wp_item(), source['url'])]
    items, _, errors = collect_source(source, fetcher, [])
    assert len(items) == 1 and errors[0]['code'] == 'listing_parse_failed'


def test_unreviewed_listing_still_fails_before_any_request():
    source = deepcopy(SOURCES['menderes-belediye'])
    source['listing_urls'].append('https://unreviewed.example/list')
    fetcher = Mock()
    with pytest.raises(ValueError, match='Listing must belong'):
        collect_source(source, fetcher, [])
    fetcher.get.assert_not_called()


def test_partial_lists_export_real_health_and_no_private_error_text(tmp_path, at, monkeypatch):
    source = SOURCES['menderes-belediye']
    sources = tmp_path / 'sources.json'; sources.write_text(json.dumps([source]))
    fetcher = Mock(); fetcher.get.side_effect = [http_error(503), (wp_item(), source['url'])]
    monkeypatch.setattr('seferihisar.pipeline.Fetcher', lambda _: fetcher)
    state, public = tmp_path / 'state.sqlite', tmp_path / 'public'
    run(state, public, sources, at)
    db = Store(state)
    assert len(db.items()) == 1
    check = db.rows('SELECT * FROM source_health')[0]
    assert (check['status'], check['parsed'], check['accepted'], check['error_count']) == ('partial', 1, 1, 1)
    db.close()
    text = (public / 'data.json').read_text()
    assert 'listing_http_503' in text and 'PRIVATE_VALUE' not in text


def test_menderes_recovers_one_503_then_preserves_shared_retry_budget(monkeypatch):
    source = SOURCES['menderes-belediye']
    fetcher = Fetcher([source])
    monkeypatch.setattr('seferihisar.collect.time.sleep', lambda _: None)
    get = Mock(side_effect=[http_error(503), (wp_item(), source['url']), http_error(503)])
    monkeypatch.setattr(fetcher, '_get', get)
    items, _, errors = collect_source(source, fetcher, [])
    assert len(items) == 1 and get.call_count == 3
    assert fetcher.retries['menderes.bel.tr'] == 0
    assert errors == [{'source_id':source['id'], 'code':'listing_http_503'}]


def test_dns_failure_is_typed_and_never_contains_resolver_text(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.socket.getaddrinfo', Mock(side_effect=socket.gaierror(PRIVATE)))
    with pytest.raises(PublicDNSLookupError) as failure:
        safe_url('https://www.urla.gov.tr/', {'www.urla.gov.tr'})
    assert PRIVATE not in str(failure.value)
    assert source_error_code(failure.value) == 'source_dns_failed'
    assert detail_error_code(failure.value) == 'detail_dns_failed'


def test_requests_wrapped_dns_failure_has_specific_code():
    reason = NameResolutionError('www.urla.gov.tr', None, socket.gaierror(PRIVATE))
    error = requests.ConnectionError(MaxRetryError(None, '/?' + PRIVATE, reason=reason))
    assert source_error_code(error) == 'source_dns_failed'


def test_real_typed_hostname_mismatch_is_distinct_and_never_retried(monkeypatch):
    reason = ssl.SSLCertVerificationError(1, PRIVATE); reason.verify_code = 62
    error = requests.exceptions.SSLError(MaxRetryError(None, '/?' + PRIVATE, reason=SSLError(reason)))
    assert source_error_code(error) == 'source_tls_name_mismatch'
    assert detail_error_code(error) == 'detail_tls_name_mismatch'
    fetcher = Fetcher([SOURCES['menderes-belediye']])
    get = Mock(side_effect=error); monkeypatch.setattr(fetcher, '_get', get)
    with pytest.raises(requests.exceptions.SSLError):
        fetcher.get(SOURCES['menderes-belediye']['url'])
    assert get.call_count == 1
    assert source_error_code(requests.exceptions.SSLError('Hostname mismatch ' + PRIVATE)) == 'source_tls_failed'


@pytest.mark.parametrize('status,age,enabled,shown', [('ok', 0, True, True), ('empty', 0, True, True),
    ('failed', 0, True, False), ('partial', 0, True, False), ('ok', 2, True, False), ('ok', 0, False, False)])
def test_alternative_health_does_not_hide_direct_source_failure(at, status, age, enabled, shown):
    entry = CATALOG['instagram-gundem']
    source = {**SOURCES['seferihisar-gundem'], 'enabled':enabled}
    check = {'source_id':source['id'], 'checked_at':(at-timedelta(hours=age)).isoformat(),
             'status':status, 'parsed':0, 'accepted':0, 'error_count':0}
    result = public_catalog([entry], [source], [check], at)[0]
    assert result['status'] == 'access_failed'
    assert ('son kontrolde okunabildi' in result['note']) is shown
    assert 'yalnız Instagram’da' in result['note']
