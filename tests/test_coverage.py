import json
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup
from seferihisar.collect import decode_document, publication_date, izmir_art_items, structured
from seferihisar.pipeline import run
from seferihisar.security import validate_state
from seferihisar.store import Store


def test_implicit_latin1_does_not_corrupt_turkish_html_or_rss():
    value='İzmir, Güzelbahçe, Seferihisar eğitim duyurusu'
    assert decode_document(('<meta charset="UTF-8">'+value).encode(), 'text/html').endswith(value)
    assert decode_document(('<?xml version="1.0" encoding="utf-8"?>'+value).encode(), 'text/xml').endswith(value)


def test_explicit_http_charset_and_bom_are_honored():
    assert decode_document('İzmir eğitim'.encode('iso-8859-9'),'text/plain; charset=iso-8859-9')=='İzmir eğitim'
    assert decode_document('İzmir'.encode('utf-8-sig'))=='İzmir'
    with pytest.raises(ValueError):decode_document(b'x','text/html; charset=unknown-charset')


def test_izsu_date_uses_own_direct_text_without_update_or_sidebar_date():
    soup=BeautifulSoup('<span class="own">12 Ekim 2026<span>Son güncellenme: 13 Ekim 2026</span></span><span>14 Ekim 2026</span>','html.parser')
    source={'published_date_selector':'.own','published_date_direct_text':True,'published_date_format':'turkish'}
    assert publication_date(soup,source).isoformat()=='2026-10-12T00:00:00+03:00'
    assert publication_date(BeautifulSoup('<span class="own">12 Ekim</span>','html.parser'),source) is None


@pytest.fixture
def art_source():
    return {'id':'izmir-art','name':'İzmir Art','url':'https://www.izmir.art/eventsContent.json'}


@pytest.fixture
def art_event():
    return {'title':'Hafifletici Sebepler','location':'Urla Sahnesi','locationAddress':'Zafer Caddesi No:80 Urla / İzmir',
            'locationDistrict':'6025437a8db21f41d5e14210','eventType':'Tiyatro','startDate':'2026-10-14T17:00:00.000Z',
            'endDate':'2026-10-14T18:30:00.000Z','eventTime':'20:00','eventPrice':'672TL','cancel':0,
            'seans':'6ac33e3a70928e850d86ba6c','eventlink':'/tr/tiyatro?seans=6ac33e3a70928e850d86ba6c'}


def test_official_session_preserves_timezone_price_and_identity(art_event,art_source):
    event=izmir_art_items(json.dumps([art_event]),art_source['url'],art_source)[0]
    assert event['start']=='2026-10-14T20:00:00+03:00'
    assert event['end']=='2026-10-14T21:30:00+03:00'
    assert event['time_known'] and event['free'] is False and event['price']=='672'
    assert '?seans=' in event['identity'] and event['organizer'] is None


@pytest.mark.parametrize('address',['Konak / İzmir','Çeşme / İzmir','', 'Buca / İzmir'])
def test_touring_session_does_not_borrow_urla_title_or_district(art_event,art_source,address):
    art_event.update(title='Urla konseri',location='Urla Sahnesi',locationAddress=address)
    assert not izmir_art_items(json.dumps([art_event]),art_source['url'],art_source)


@pytest.mark.parametrize('changes',[
    {'startDate':''},{'endDate':'2026-10-13T00:00:00Z'},{'eventTime':'21:00'},
    {'seans':'invalid'},{'eventlink':'https://other.example/tiyatro'},{'cancel':'0'},
])
def test_conflicting_or_missing_event_fields_fail_closed(art_event,art_source,changes):
    art_event.update(changes)
    assert not izmir_art_items(json.dumps([art_event]),art_source['url'],art_source)


def test_explicit_free_and_cancellation_and_unknown_time(art_event,art_source):
    art_event.update(cancel=1,eventPrice='Ücretsiz',eventTime='')
    event=izmir_art_items(json.dumps([art_event]),art_source['url'],art_source)[0]
    assert event['free'] is True and event['status']=='cancelled' and not event['time_known']


def test_source_health_records_real_failure_without_private_exception(tmp_path,at,source):
    source={**source,'enabled':True,'access':'robots','trusted':True}
    cfg=tmp_path/'sources.json';cfg.write_text(json.dumps([source]))
    with patch('seferihisar.pipeline.collect_source',side_effect=RuntimeError('PRIVATE_EXCEPTION_BODY')):
        run(tmp_path/'state.sqlite',tmp_path/'public',cfg,at)
    store=Store(tmp_path/'state.sqlite')
    check=store.rows('SELECT * FROM source_health')[0]
    assert check['status']=='failed' and check['error_count']==1 and check['parsed']==0
    validate_state(store.path);store.close()
    public=(tmp_path/'public/data.json').read_text(encoding='utf-8')
    assert 'PRIVATE_EXCEPTION_BODY' not in public
    assert json.loads(public)['source_health'][0]['status']=='failed'


def test_source_health_rejects_unknown_fields_and_impossible_counters(tmp_path,at):
    store=Store(tmp_path/'health.sqlite')
    with store.db:
        store.db.execute('INSERT INTO source_health VALUES (?,?,?,?,?,?,?)',('official',at.isoformat(),'ok',1,2,0,None))
    with pytest.raises(ValueError):validate_state(store.path)
    store.close()


def test_checked_rss_and_event_sources_are_connected():
    sources={s['id']:s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
    assert sources['izsu']['url'].startswith('https://izsu.gov.tr/')
    assert sources['izmir-art']['kind']=='izmir_art' and not sources['izmir-art']['follow_feed_details']
    for sid in ('seferihisar-life','urla-ada-haber','seferihisar-esnaf','seferihisar-mem','teosfest'):
        assert sources[sid]['enabled'] and sources[sid]['kind']=='rss'
    assert not sources['gdz']['enabled'] and not sources['biletix']['enabled']


def test_dns_failure_remains_closed_and_uses_only_one_reviewed_retry(monkeypatch,source):
    import socket
    from seferihisar.collect import Fetcher
    monkeypatch.setattr('seferihisar.collect.time.sleep',lambda _:None)
    attempts=[]
    def dns(*args,**kwargs):
        attempts.append(1)
        raise socket.gaierror('private diagnostic')
    monkeypatch.setattr('seferihisar.collect.socket.getaddrinfo',dns)
    with pytest.raises(Exception,match='Public source DNS lookup failed'):
        Fetcher([{**source,'enabled':True,'transient_retries':1}]).get(source['url'])
    assert len(attempts)==2


def test_school_reader_never_uses_related_article_date():
    source=next(s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8')) if s['id']=='seferihisar-hem')
    page='<div class="icerik"><div class="icerik-yazi"><h1 class="baslik">Seferihisar kurs duyurusu</h1><div class="ara-bar"><span class="icerik-tarihi">01.10.2026</span></div><p>Seferihisar Halk Eğitimi Merkezi yeni kurs programı açıkladı.</p></div></div><div><span class="icerik-tarihi">12.10.2026</span></div>'
    assert structured(page,source['url'],source)[0]['published_at']=='2026-10-01T00:00:00+03:00'
    assert not structured(page.replace('01.10.2026',''),source['url'],source)
