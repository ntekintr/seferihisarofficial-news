import json
from datetime import datetime
from unittest.mock import Mock

import pytest
import requests

from seferihisar.collect import collect_source, municipal_calendar_items
from seferihisar.domain import TZ
from seferihisar.editor import caption, verify


SOURCE = {'id': 'seferihisar-calendar', 'name': 'Seferihisar Belediyesi etkinlik takvimi',
          'url': 'https://seferihisar.bel.tr/Kurumsal/TakvimService.aspx',
          'kind': 'municipal_calendar', 'enabled': True, 'trusted': True, 'access': 'robots',
          'max_pages': 8}
ROW = {'title': 'Ürkmez Kültür ve Sanat Festivali', 'description': 'Ürkmez Kültür ve Sanat Festivali',
       'start': '2026-10-15', 'end': '2026-10-18', 'url': '/urkmez-festivali'}
AT = datetime(2026, 10, 13, 3, tzinfo=TZ)


def test_calendar_end_is_exclusive_and_missing_details_are_not_invented():
    item = municipal_calendar_items(json.dumps([ROW]), SOURCE['url'], SOURCE)[0]
    assert item['start'] == '2026-10-15T00:00:00+03:00'
    assert item['end'] == '2026-10-17T00:00:00+03:00'
    assert not item['time_known']
    assert item['free'] is None and item['location'] is None and item['organizer'] is None
    assert verify(item, SOURCE, AT) is None
    rendered = caption(item, 'Bölge takviminde')
    assert 'Saat açıklanmadı' in rendered and 'Ücret bilgisi açıklanmadı' in rendered
    assert ' · 00:00' not in rendered


@pytest.mark.parametrize('changes', [
    {'start': '15 Ekim'}, {'start': '2026-02-30'}, {'end': '2026-10-15'},
    {'end': '2026-10-14'}, {'end': None}, {'start': '2026-10-15T20:00:00Z'},
    {'url': '//other.example/event'}, {'url': 'https://other.example/event'},
    {'title': 'Ankara konseri'}, {'title': 'Seferihisar belediye hizmeti'},
])
def test_invalid_dates_nonlocal_news_and_external_links_are_rejected(changes):
    assert not municipal_calendar_items(json.dumps([{**ROW, **changes}]), SOURCE['url'], SOURCE)


def test_upper_case_turkish_title_is_still_an_event():
    # 9 Nov 2026 live row: casefold() made İ into i + U+0307 and the festival was dropped as news.
    row = {**ROW, 'title': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ', 'description': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ',
           'start': '2026-12-06', 'end': '2026-12-07', 'url': '/26-seferihisar-mandalina-senligi'}
    items = municipal_calendar_items(json.dumps([row]), SOURCE['url'], SOURCE)
    assert len(items) == 1 and items[0]['title'] == row['title'] and items[0]['category'] != 'news'
    assert not municipal_calendar_items(json.dumps([{**row, 'title': 'ANKARA KONSERİ'}]), SOURCE['url'], SOURCE)
    assert not municipal_calendar_items(json.dumps([{**row, 'title': 'SEFERİHİSAR BELEDİYE HİZMETİ'}]), SOURCE['url'], SOURCE)


@pytest.mark.parametrize('body', ['{}', '[null]'])
def test_wrong_collection_shape_is_a_source_failure(body):
    with pytest.raises(ValueError):
        municipal_calendar_items(body, SOURCE['url'], SOURCE)


def detail(title=ROW['title'], body=''):
    return f'<div class="col-md-9"><div class="inner"><div class="right-title">{title}</div>{body}</div></div>'


def test_calendar_requires_matching_live_detail_and_deduplicates(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    url = 'https://seferihisar.bel.tr/urkmez-festivali'
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW, ROW]), SOURCE['url']), (detail(), url)]
    items, candidates, errors = collect_source(SOURCE, fetcher, [])
    assert len(items) == 1 and not candidates and not errors
    assert fetcher.get.call_count == 2


@pytest.mark.parametrize('page', [detail('Başka festival'), detail(body='<p>Tarih: 16.10.2026</p>')])
def test_mismatched_title_or_conflicting_detail_date_blocks_source(monkeypatch, page):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW]), SOURCE['url']), (page, 'https://seferihisar.bel.tr/urkmez-festivali')]
    items, _, errors = collect_source(SOURCE, fetcher, [])
    assert not items and errors == [{'source_id': SOURCE['id'], 'code': 'calendar_detail_check_failed'}]


def test_failed_detail_never_refreshes_stored_event(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW]), SOURCE['url']), requests.Timeout('private request body')]
    items, _, errors = collect_source(SOURCE, fetcher, [])
    assert not items and errors == [{'source_id': SOURCE['id'], 'code': 'calendar_detail_timeout'}]
    assert 'private' not in json.dumps(errors)


def test_past_events_and_far_future_do_not_consume_detail_budget(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.return_value = (json.dumps([
        {**ROW, 'start': '2026-10-12', 'end': '2026-10-13'},
        {**ROW, 'start': '2027-10-15', 'end': '2027-10-18'},
    ]), SOURCE['url'])
    assert collect_source(SOURCE, fetcher, [])[0] == []
    assert fetcher.get.call_count == 1


def test_explicit_cancellation_preserves_date_and_unknown_time(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW]), SOURCE['url']),
                              (detail(body='<p>Festival iptal edilmiştir.</p>'), 'https://seferihisar.bel.tr/urkmez-festivali')]
    item = collect_source(SOURCE, fetcher, [])[0][0]
    assert item['status'] == 'cancelled' and not item['time_known']


@pytest.mark.parametrize('row,body,location,last_day', [
    (ROW, '<p>15 Ekim Perşembe</p><p>16 Ekim Cuma</p><p>17 Ekim Cumartesi</p>'
     '<p>*15 Ekim günü Seferihisar Kapalı Pazar Yeri\'nden 18.00\'da Araç Kaldırılacaktır.</p>'
     '<p>📍 <strong>Ürkmez Hizmet Binası - Ürkmez Tiyatro Salonu</strong><br> </p>',
     'Ürkmez Hizmet Binası - Ürkmez Tiyatro Salonu', '2026-10-17'),
    ({**ROW, 'title': 'Orhanlı Köyü 3.Erkence Zeytin Festivali',
      'start': '2026-10-31', 'end': '2026-11-02'},
     '<p>📅 <strong>31 Ekim-1 Kasım 2026</strong><br>'
     '📍Orhanlı Köyü Piknik Alanı Seferihisar / İzmir<br>'
     '*Orhanlı Vadisi zeytin kültürünü kutlamak için bir araya geliyoruz.</p>',
     'Orhanlı Köyü Piknik Alanı Seferihisar / İzmir', '2026-11-01'),
])
def test_live_template_reads_event_body_and_explicit_venue_without_guessing_time(monkeypatch, row, body, location, last_day):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    page = ('<div class="col-md-9"><div class="inner pd0"><div class="right-title">'
            + row['title'] + '</div></div><div class="inner">' + body + '</div></div>'
            '<footer><p>Yer: Belediye hizmet binası, başka adres</p><p>Ücret: Ücretsiz</p></footer>')
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([row]), SOURCE['url']),
                              (page, 'https://seferihisar.bel.tr/urkmez-festivali')]
    items, _, errors = collect_source(SOURCE, fetcher, [])
    assert not errors and len(items) == 1
    item = items[0]
    assert item['location'] == location
    assert not item['time_known'] and item['free'] is None and item['organizer'] is None
    assert item['start'].endswith('T00:00:00+03:00')
    assert item['end'].startswith(last_day)


def test_municipal_detail_labels_do_not_require_a_labelled_date(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW]), SOURCE['url']),
                              (detail(body='<p>Konum: Ürkmez Salonu</p><p>Düzenleyen: Kültür Derneği</p>'
                                      '<p>Ücret: Ücretsiz</p>'), 'https://seferihisar.bel.tr/urkmez-festivali')]
    item = collect_source(SOURCE, fetcher, [])[0][0]
    assert item['location'] == 'Ürkmez Salonu' and item['organizer'] == 'Kültür Derneği'
    assert item['free'] is True and not item['time_known']


MANDALINA = {**ROW, 'title': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ', 'description': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ',
             'start': '2026-12-06', 'end': '2026-12-07', 'url': '/26-seferihisar-mandalina-senligi'}
MANDALINA_BODY = ('<p>26.SEFERİHİSAR MANDALİNA ŞENLİĞİ</p><p>İkramlar-Yarışmalar-Etkinlikler</p>'
                  '<p>📅 6 Aralık Pazar<br/>\n📍 Seferihisar Kapalı Pazar yeri<br/>\n🕒 14:00</p>')


def collect_detail(monkeypatch, row, body):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    page = ('<div class="col-md-9"><div class="inner pd0"><div class="right-title">' + row['title']
            + '</div></div><div class="inner">' + body + '</div></div>')
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([row]), SOURCE['url']),
                              (page, 'https://seferihisar.bel.tr' + row['url'])]
    items, _, errors = collect_source(SOURCE, fetcher, [])
    assert not errors and len(items) == 1
    return items[0]


def test_clock_emoji_line_is_the_start_time(monkeypatch):
    # 10 Nov 2026 live page: "🕒 14:00" was ignored and the card said "Saat açıklanmadı".
    item = collect_detail(monkeypatch, MANDALINA, MANDALINA_BODY)
    assert item['time_known'] and item['start'] == '2026-12-06T14:00:00+03:00'
    assert item['end'] == item['start'] and item['location'] == 'Seferihisar Kapalı Pazar yeri'
    assert verify(item, SOURCE, AT) is None
    rendered = caption(item, 'Bölge takviminde')
    assert '06.12.2026 · 14:00' in rendered and 'Saat açıklanmadı' not in rendered


def test_labelled_time_of_a_multi_day_event_is_its_first_start(monkeypatch):
    item = collect_detail(monkeypatch, ROW, '<p>Saat: 19.30 - 23.00</p>')
    assert item['time_known'] and item['start'] == '2026-10-15T19:30:00+03:00'
    assert item['end'].startswith('2026-10-17')
    assert 'Başlangıç 19:30' in caption(item, 'Bölge takviminde')


@pytest.mark.parametrize('body', [
    '<p>🕒 14:00</p><p>Saat: 16:00</p>',                  # contradictory labels
    '<p>Kortej 13.00\'te Kapalı Pazar Yeri\'nden çıkacak.</p>',  # time inside a sentence
    '<p>🕒 14:00 ve 20:00</p>',                            # more than one time on the line
    '<p>🕒 25:00</p>',
])
def test_unclear_times_stay_unannounced(monkeypatch, body):
    item = collect_detail(monkeypatch, MANDALINA, body)
    assert not item['time_known'] and item['start'] == '2026-12-06T00:00:00+03:00'
    assert 'Saat açıklanmadı' in caption(item, 'Bölge takviminde')


def test_conflicting_venue_labels_reject_detail(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.now', lambda: AT)
    fetcher = Mock()
    fetcher.get.side_effect = [(json.dumps([ROW]), SOURCE['url']),
                              (detail(body='<p>Yer: Birinci Salon</p><p>📍İkinci Salon</p>'),
                               'https://seferihisar.bel.tr/urkmez-festivali')]
    items, _, errors = collect_source(SOURCE, fetcher, [])
    assert not items and errors == [{'source_id': SOURCE['id'], 'code': 'calendar_detail_check_failed'}]

