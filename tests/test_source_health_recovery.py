import json
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from seferihisar.collect import Fetcher, collect_source, feed_items
from seferihisar.pipeline import export
from seferihisar.source_catalog import public_catalog
from seferihisar.source_readers import ticket_items

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}


def test_gdz_recovers_one_500_but_second_district_failure_stays_visible(monkeypatch):
    fetcher = Fetcher([SOURCES['gdz']])
    monkeypatch.setattr('seferihisar.collect.time.sleep', lambda _: None)
    attempts = []
    def get(url):
        district = parse_qs(urlsplit(url).query)['district'][0]
        attempts.append(district)
        if (district == 'URLA' and attempts.count(district) == 1) or district == 'MENDERES':
            response = requests.Response(); response.status_code = 500
            raise requests.HTTPError(response=response)
        return json.dumps({'success': True, 'level': 'district_outages', 'city': 'İZMİR',
                           'district': district, 'data': [], 'count': 0}), url
    monkeypatch.setattr(fetcher, '_get', get)
    _, _, errors = collect_source(SOURCES['gdz'], fetcher, [])
    assert attempts == ['SEFERİHİSAR', 'URLA', 'URLA', 'GÜZELBAHÇE', 'MENDERES']
    assert errors == [{'source_id': 'gdz', 'code': 'detail_http_500'}]
    assert fetcher.retries['www.gdzelektrik.com.tr'] == 0


@pytest.mark.parametrize('error', [requests.exceptions.SSLError(), requests.HTTPError(response=None),
                                  ValueError('robots.txt disallows this path')])
def test_gdz_does_not_retry_certificate_or_explicit_policy_failure(monkeypatch, error):
    fetcher = Fetcher([SOURCES['gdz']])
    get = Mock(side_effect=error)
    monkeypatch.setattr(fetcher, '_get', get)
    with pytest.raises(type(error)):
        fetcher.get(SOURCES['gdz']['url'])
    assert get.call_count == 1


@pytest.mark.parametrize('body', ['<html><body>Verify your browser</body></html>',
                                 '<rss/>', '<collection><entry/></collection>'])
def test_rss_protection_or_wrong_document_is_not_a_healthy_empty_feed(source, body):
    with pytest.raises(ET.ParseError):
        feed_items(body, source['url'], source)


@pytest.mark.parametrize('body', ['<rss version="2.0"><channel/></rss>',
                                 '<feed xmlns="http://www.w3.org/2005/Atom"/>',
                                 '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                                 'xmlns="http://purl.org/rss/1.0/"><channel/></rdf:RDF>'])
def test_real_empty_rss_atom_and_rdf_remain_readable(source, body):
    assert feed_items(body, source['url'], source) == []


def test_bademler_ticket_reader_keeps_each_verified_session_without_guessing_year():
    source = SOURCES['bubilet-bademler']
    body = Path('tests/fixtures/source_coverage/bademler-sessions.html').read_text(encoding='utf-8')
    items = ticket_items(body, source['url'], source)
    assert len(items) == 6
    assert len({item['identity'] for item in items}) == 6
    assert items[0]['start'] == '2026-10-14T19:30:00+03:00'
    assert items[1]['start'] == '2026-10-17T10:00:00+03:00'
    assert all('Bademler Sanat Köyü' in i['location'] and 'Urla' in i['location'] for i in items)
    # A matching town is insufficient for this venue-specific reader; a title
    # or event biography must not supply a different session's location.
    assert not ticket_items(body.replace('Bademler Sanat Köyü', 'Başka Urla Salonu'), source['url'], source)
    assert not ticket_items(body.replace('Bademler Caddesi No:8 Bademler Mahallesi Urla İzmir', 'Konak İzmir'), source['url'], source)


def catalog_entry(status='access_failed'):
    return {'id': 'instagram-sehayder', 'name': 'SEHAYDER', 'url': SOURCES['instagram-sehayder']['url'],
            'group': 'oda_dernek', 'status': status, 'note': 'Eski izin gerekli notu'}


def health(at, status):
    return {'source_id': 'instagram-sehayder', 'checked_at': at.isoformat(), 'status': status,
            'parsed': 6 if status == 'ok' else 0, 'accepted': 6 if status == 'ok' else 0,
            'error_count': 1 if status in ('failed', 'partial') else 0}


@pytest.mark.parametrize('status', ['ok', 'empty'])
def test_live_catalog_recovery_removes_stale_permission_note_without_changing_config(at, status):
    entry = catalog_entry(); before = deepcopy(entry)
    result = public_catalog([entry], [SOURCES['instagram-sehayder']], [health(at, status)], at)[0]
    assert result['status'] == 'connected'
    assert 'Eski izin gerekli' not in result['note']
    assert entry == before


@pytest.mark.parametrize('status,expected', [('failed', 'access_failed'), ('partial', 'partial')])
def test_latest_failure_overrides_old_connected_catalog(at, status, expected):
    result = public_catalog([catalog_entry('connected')], [SOURCES['instagram-sehayder']], [health(at, status)], at)[0]
    assert result['status'] == expected


@pytest.mark.parametrize('age', [timedelta(hours=2), timedelta(minutes=-10)])
def test_stale_or_future_health_cannot_claim_working_source(at, age):
    result = public_catalog([catalog_entry('connected')], [SOURCES['instagram-sehayder']], [health(at-age, 'ok')], at)[0]
    assert result['status'] == 'check_pending'


def test_disabled_missing_health_and_alias_are_reported_honestly(at):
    reader = SOURCES['instagram-sehayder']
    assert public_catalog([catalog_entry('connected')], [{**reader, 'enabled': False}], [health(at, 'ok')], at)[0]['status'] == 'reader_pending'
    assert public_catalog([catalog_entry('connected')], [reader], [], at)[0]['status'] == 'check_pending'
    alias = {**catalog_entry(), 'id': 'sehayder-social', 'reader_id': 'instagram-sehayder'}
    assert public_catalog([alias], [reader], [health(at, 'ok')], at)[0]['status'] == 'connected'


def test_alternative_reader_never_erases_undated_page_or_certificate_limitation(at):
    undated = {**catalog_entry('date_missing'), 'note': 'Etkinlik yılı yok'}
    tls = {'id': 'guzelbahce-kaymakamlik', 'name': 'Kaymakamlık', 'url': 'https://guzelbahce.gov.tr/',
           'group': 'kamu', 'status': 'access_failed', 'note': 'Sertifika hatası'}
    result = public_catalog([undated, tls], [SOURCES['instagram-sehayder']], [health(at, 'ok')], at)
    assert result == [undated, tls]


def test_every_reviewed_connected_catalog_entry_has_an_explicit_reader_binding():
    entries = json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))
    for entry in entries:
        if entry['status'] == 'connected':
            assert entry.get('reader_id', entry['id']) in SOURCES


def test_export_uses_completion_time_for_health_of_late_crawl_sources(store, at, tmp_path, monkeypatch):
    checked = at + timedelta(minutes=7)
    with store.db:
        store.db.execute('INSERT INTO source_health VALUES (?,?,?,?,?,?,?)',
                         ('sehayder', checked.isoformat(), 'empty', 0, 0, 0, None))
    monkeypatch.setattr('seferihisar.pipeline.now', lambda: checked + timedelta(minutes=1))
    public = tmp_path / 'public'
    export(store, public, list(SOURCES.values()), at)
    data = json.loads((public / 'data.json').read_text(encoding='utf-8'))
    entry = next(e for e in data['source_catalog'] if e['id'] == 'sehayder')
    assert entry['status'] == 'connected'
