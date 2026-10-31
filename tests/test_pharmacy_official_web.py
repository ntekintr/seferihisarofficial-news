"""Transport fallback must retain actual source, region and duty interval."""
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from seferihisar import domain, pharmacy_source as source
from seferihisar.pharmacy_data import IZMIR_WEB, validate_bulletin
from test_pharmacy_story import AT


def html():
    return (Path(__file__).parent/'fixtures/pharmacy-izmir-web.html').read_text(encoding='utf-8')


def test_official_web_preserves_interval_and_actual_source():
    value = source.parse_izmir_web(html(),AT)
    assert value['source_url']==IZMIR_WEB
    assert len(value['entries'])==2
    assert {e['region'] for e in value['entries']}=={'SEFERİHİSAR','SIĞACIK'}
    assert any('23:00' in e['note'] and '22.10' in e['note'] for e in value['entries'])
    validate_bulletin(value)


@pytest.mark.parametrize('old,new',[
    ('22-10-2026','21-10-2026'),
    ('23-10-2026 09:00:00','22-10-2026 08:00:00'),
    ('NO:2 SEFERİHİSAR','NO:2 MENDERES'),
    ('<strong>Başlangıç : </strong>','<strong>Site tarihi : </strong>'),
    ('<option selected>SEFERİHİSAR','<option selected>URLA'),
])
def test_stale_wrong_scope_or_ambiguous_dates_cannot_be_used(old,new):
    original=html(); assert old in original
    with pytest.raises(ValueError):source.parse_izmir_web(original.replace(old,new),AT)


def test_truncated_pagination_is_not_a_complete_list():
    with pytest.raises(ValueError):source.parse_izmir_web(html()+'<a href="?page=2">2</a>',AT)


def test_transport_fallback_is_single_and_uses_actual_official_url(monkeypatch):
    fetcher=Mock();fetcher.get.side_effect=[requests.ConnectTimeout(),(html(),'text/html')]
    monkeypatch.setattr(domain,'now',lambda:AT)
    value=source.fetch_bulletin(AT,fetcher)
    assert value['source_url']==IZMIR_WEB
    assert [c.args[0] for c in fetcher.get.call_args_list]==[source.profile()['source_url'],IZMIR_WEB]


@pytest.mark.parametrize('api',['[]', json.dumps([{'Bolge':'URLA','Adi':'Başka Eczanesi','Adres':'Urla',
                                                   'Tarih':'2026-10-22T00:00:00','Telefon':'','BolgeAciklama':''}])])
def test_empty_api_list_falls_back_once_to_the_official_page(monkeypatch,api):
    # 30 Oct: the open API answered [] for all of İzmir; the page listed the day's pharmacies.
    fetcher=Mock();fetcher.get.side_effect=[(api,'application/json'),(html(),'text/html')]
    monkeypatch.setattr(domain,'now',lambda:AT)
    value=source.fetch_bulletin(AT,fetcher)
    assert value['source_url']==IZMIR_WEB and len(value['entries'])==2
    assert [c.args[0] for c in fetcher.get.call_args_list]==[source.profile()['source_url'],IZMIR_WEB]


def test_stale_api_rows_are_never_hidden_by_the_page(monkeypatch):
    row={'Bolge':'SEFERİHİSAR','Adi':'Eski Eczanesi','Adres':'Camikebir Mah. Seferihisar',
         'Tarih':'2026-10-21T00:00:00','Telefon':'','BolgeAciklama':''}
    fetcher=Mock();fetcher.get.side_effect=[(json.dumps([row]),'application/json'),(html(),'text/html')]
    monkeypatch.setattr(domain,'now',lambda:AT)
    with pytest.raises(ValueError,match='stale'):source.fetch_bulletin(AT,fetcher)
    assert fetcher.get.call_count==1


@pytest.mark.parametrize('error',[requests.exceptions.SSLError(),requests.HTTPError(),PermissionError()])
def test_tls_http_or_robots_denial_is_never_redirected_to_another_source(error):
    fetcher=Mock();fetcher.get.side_effect=error
    with pytest.raises(type(error)):source.fetch_bulletin(AT,fetcher)
    assert fetcher.get.call_count==1


def test_duty_day_cannot_change_during_fallback(monkeypatch):
    fetcher=Mock();fetcher.get.side_effect=[requests.ConnectTimeout(),(html(),'text/html')]
    monkeypatch.setattr(domain,'now',lambda:AT+timedelta(days=1))
    with pytest.raises(ValueError):source.fetch_bulletin(AT,fetcher)


def test_source_cannot_be_replaced_with_unreviewed_third_party():
    value=source.parse_izmir_web(html(),AT)
    value['source_url']='https://example.invalid/pharmacy'
    with pytest.raises(ValueError):validate_bulletin(value)
