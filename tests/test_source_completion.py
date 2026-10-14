import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from seferihisar.collect import collect_source
from seferihisar.domain import parse_date
from seferihisar.editor import verify
from seferihisar.schedule import source_current,prepare
from seferihisar.security import validate_state
from seferihisar.source_readers import (afad_items,mgm_items,ticket_items,rotary_items,hospital_items,
                                       culture_items,program_items,public_collection)

FIXTURES=Path('tests/fixtures/source_coverage')
SOURCES={s['id']:s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}


def fixture(name):return (FIXTURES/(name+'.html')).read_text(encoding='utf-8')


def test_two_festival_days_retain_real_separate_ticket_session_ids():
    items=ticket_items(fixture('bubilet-urladam'),'https://www.bubilet.com.tr/izmir/etkinlik/urladam-octoberfest',SOURCES['bubilet'])
    assert len(items)==2 and len({i['identity'] for i in items})==2
    assert {i['start'] for i in items}=={'2026-10-16T19:00:00+03:00','2026-10-17T19:00:00+03:00'}
    assert {i['price'] for i in items}=={'400'}
    assert all('/seans/' in i['identity'] and 'Urla' in i['location'] for i in items)


def test_touring_play_keeps_urla_session_and_rejects_konak_session():
    items=ticket_items(fixture('biletinial-detail'),'https://biletinial.com/tr-tr/tiyatro/hafifletici-sebepler',SOURCES['biletinial'])
    assert len(items)==1 and items[0]['start']=='2026-10-14T20:00:00+03:00'
    assert '#session-' in items[0]['identity'] and 'Urla' in items[0]['location']


def test_central_izmir_is_not_automatically_a_local_ticket_source():
    for fixture_name,sid,url in [('biletix-current','biletix','https://www.biletix.com/etkinlik/5MAK0/TURKIYE/tr'),
                                  ('biletino-detail','biletino','https://biletino.com/tr/e-jeg/show/')]:
        assert not ticket_items(fixture(fixture_name),url,SOURCES[sid])


def test_biography_urla_mention_does_not_relocate_nonlocal_show():
    body=fixture('biletix-current').replace('"name": "Cevriye Müzikali"','"name": "Urla konseri"')
    assert not ticket_items(body,'https://www.biletix.com/etkinlik/5MAK0/TURKIYE/tr',SOURCES['biletix'])


def test_ticket_session_identity_survives_changes_in_time_when_real_id_exists():
    original=ticket_items(fixture('bubilet-urladam'),'https://www.bubilet.com.tr/show',SOURCES['bubilet'])
    changed=ticket_items(fixture('bubilet-urladam').replace('16:00:00','17:00:00'),'https://www.bubilet.com.tr/show',SOURCES['bubilet'])
    assert [i['identity'] for i in changed]==[i['identity'] for i in original]
    assert original[0]['start']!=changed[0]['start']


def test_mutating_ticket_url_cannot_leave_approved_origin():
    body=fixture('bubilet-urladam').replace('https://www.bubilet.com.tr/izmir/etkinlik/','https://evil.example/izmir/etkinlik/')
    items=ticket_items(body,'https://www.bubilet.com.tr/show',SOURCES['bubilet'])
    assert all(i['url'].startswith('https://www.bubilet.com.tr/') for i in items)


def test_past_afad_microquake_is_not_republished_as_current_warning():
    assert not afad_items(fixture('afad'),SOURCES['afad']['url'],SOURCES['afad'])


def test_afad_actual_local_fields_and_occurrence_expiry_are_preserved():
    body=fixture('afad').replace('>1.3<','>4.2<') # Clearly synthetic magnitude regression.
    item=afad_items(body,SOURCES['afad']['url'],SOURCES['afad'])[0]
    assert item['published_at']=='2026-10-13T12:01:25+03:00'
    assert item['valid_until']=='2026-10-13T15:01:25+03:00'
    assert item['url']=='https://deprem.afad.gov.tr/event-detail/596249'
    assert 'hasar veya hissedilme bilgisi içermez' in item['description']
    assert verify(item,SOURCES['afad'],parse_date('2026-10-13T12:30:00+03:00')) is None
    assert verify(item,SOURCES['afad'],parse_date('2026-10-13T16:00:00+03:00'))=='expired_service_notice'


@pytest.mark.parametrize('replacement',['nan','-4.2','40.2','unknown'])
def test_bad_afad_magnitude_never_accepted(replacement):
    assert not afad_items(fixture('afad').replace('>1.3<','>'+replacement+'<'),SOURCES['afad']['url'],SOURCES['afad'])


def test_northern_izmir_warning_is_not_a_seferihisar_warning():
    assert not mgm_items(fixture('mgm'),'https://www.mgm.gov.tr/tahmin/uyari-goster.aspx?sN=26010510y',SOURCES['mgm'])


def test_mgm_legacy_table_layout_reads_explicit_date_and_area():
    body='''<div id="divUyari"><h2>Meteorolojik Uyarı</h2><table><tr>
      <th>Tarih:</th><td>12 Ekim 2026 Pazartesi</td><th>Saat:</th><td>11.30</td></tr></table>
      <h3>Beklenen Meteorolojik Hadise</h3><p>Seferihisar kuvvetli yağış uyarısı</p>
      <h3>Başlama-Bitiş Zamanı</h3><p>13.10.2026 17:00 - 14.10.2026 18:00</p>
      <h3>Genel Durum</h3><p>Seferihisar ve Urla ilçelerinde kuvvetli yağış bekleniyor.</p></div>'''
    item=mgm_items(body,SOURCES['mgm']['url'],SOURCES['mgm'])[0]
    assert item['published_at']=='2026-10-12T11:30:00+03:00' and item['valid_until']=='2026-10-14T18:00:00+03:00'
    assert not mgm_items(body.replace('Seferihisar ve Urla ilçelerinde','İzmir’in kuzeyinde'),SOURCES['mgm']['url'],SOURCES['mgm'])


def test_local_mgm_full_year_validity_is_explicit_and_expires():
    body=fixture('mgm').replace('İzmir ve Manisa’nın kuzeyinde','Seferihisar ve Urla ilçelerinde')
    item=mgm_items(body,'https://www.mgm.gov.tr/tahmin/uyari-goster.aspx?sN=26010510y',SOURCES['mgm'])[0]
    assert item['published_at']=='2026-10-13T15:10:00+03:00'
    assert item['valid_until']=='2026-10-15T18:00:00+03:00'
    before=parse_date('2026-10-14T10:00:00+03:00');after=parse_date('2026-10-15T18:01:00+03:00')
    assert verify(item,SOURCES['mgm'],before) is None
    assert verify(item,SOURCES['mgm'],after)=='expired_service_notice'
    item['last_seen']=after.isoformat()
    assert not source_current(item,after,set())


@pytest.mark.parametrize('old,new',[('15.10.2026','15.10.'),('18.00','25.00'),('14.10.2026','16.10.2026')])
def test_mgm_missing_year_invalid_hour_or_reversed_period_fail_closed(old,new):
    body=fixture('mgm').replace('İzmir ve Manisa’nın kuzeyinde','Seferihisar ve Urla ilçelerinde').replace(old,new)
    with pytest.raises(ValueError):mgm_items(body,SOURCES['mgm']['url'],SOURCES['mgm'])


def test_expired_notice_cannot_refresh_prepared_posts_even_when_seen_now(store,at):
    item={'kind':'news','identity':'https://www.mgm.gov.tr/warning','url':'https://www.mgm.gov.tr/warning',
          'source_id':'mgm','source_name':'MGM','title':'Seferihisar fırtına uyarısı',
          'description':'Resmî meteoroloji uyarısı.', 'published_at':(at-timedelta(hours=2)).isoformat(),
          'valid_until':(at-timedelta(minutes=1)).isoformat(),'category':'weather','sources':['https://www.mgm.gov.tr/warning']}
    store.upsert(item,at.isoformat());prepare(store,at)
    assert not store.posts();validate_state(store.path)


def test_rotary_uses_visible_turkish_date_and_time_not_bad_utc_schema():
    item=rotary_items(fixture('rotary'),'https://rotary2440.org/etkinlikler/concert',SOURCES['rotary2440'])[0]
    assert item['start']=='2026-10-24T20:30:00+03:00' and item['end']==item['start']
    assert item['organizer']=='Urla Rotary Kulübü' and 'Güzelbahçe' in item['location']


def test_rotary_event_cannot_be_located_from_organizer_name_only():
    body=fixture('rotary').replace('Yalı, İstikbal Cd. No:51, 35310 Güzelbahçe/İzmir','Konak / İzmir').replace('Güzelbahçe Kültür Merlezi','Konak Sahnesi')
    assert not rotary_items(body,'https://rotary2440.org/etkinlikler/concert',SOURCES['rotary2440'])


def test_hospital_uses_own_title_date_and_article_body():
    body=fixture('hospital')+'<span class="sidebar">14 Ekim 2026</span>'
    item=hospital_items(body,'https://seferihisardh.saglik.gov.tr/TR-1611076/news.html',SOURCES['seferihisar-hastane'])[0]
    assert item['published_at']=='2026-10-07T00:00:00+03:00' and item['title'].startswith('Seferihisar Necat Hepkon')
    assert 'sidebar' not in item['description']
    assert not hospital_items(body.replace('07  Ekim  2026','Ekim'),item['url'],SOURCES['seferihisar-hastane'])


def culture_data():
    return ([{'id':'6720218a-cfb9-4090-96ab-696db02398ee','entityStatus':0,'event':{'id':'event'},
              'venue':{'id':'venue'},'eventDate':'2026-10-22T20:00:00','eventEndDate':'2026-10-22T22:00:00',
              'categories':[{'name':'Konser'}]}],
            [{'id':'event','entityStatus':0,'name':'Urla müzik konseri','longDescription':'Konser programı.'}],
            [{'id':'venue','entityStatus':0,'name':'Sahne','address':'Urla / İzmir'}])


def test_official_city_api_links_true_session_venue_and_curated_web_origin():
    item=culture_items(*culture_data(),SOURCES['izmir-kultur'])[0]
    assert item['start']=='2026-10-22T20:00:00+03:00' and item['category']=='concert'
    assert item['url'].startswith('https://kultursanat.izmir.bel.tr/event/session/')
    assert verify(item,SOURCES['izmir-kultur'],parse_date('2026-10-14T10:00:00+03:00')) is None


@pytest.mark.parametrize('mutate',['outside','missing_venue','bad_id','reversed','inactive','date_only','bad_status'])
def test_city_api_does_not_borrow_locality_from_title_or_accept_bad_session(mutate):
    sessions,events,venues=culture_data()
    if mutate=='outside':venues[0]['address']='Konak / İzmir'
    elif mutate=='missing_venue':venues=[]
    elif mutate=='bad_id':sessions[0]['id']='private?id=123'
    elif mutate=='reversed':sessions[0]['eventEndDate']='2026-10-21T20:00:00'
    elif mutate=='inactive':sessions[0]['entityStatus']=1
    elif mutate=='date_only':sessions[0]['eventDate']='2026-10-22'
    elif mutate=='bad_status':sessions[0]['entityStatus']=False
    assert not culture_items(sessions,events,venues,SOURCES['izmir-kultur'])


def test_official_session_identity_survives_title_and_time_changes():
    before=culture_items(*culture_data(),SOURCES['izmir-kultur'])[0]
    sessions,events,venues=culture_data();sessions[0]['eventDate']='2026-10-22T21:00:00';events[0]['name']='Yeni konser başlığı'
    after=culture_items(sessions,events,venues,SOURCES['izmir-kultur'])[0]
    assert before['identity']==after['identity'] and before['url']!=after['url'] and before['start']!=after['start']


def test_extra_content_origin_is_not_a_general_origin_bypass(at,event):
    source={**SOURCES['seferihisar-belediye'],'content_origin':'https://evil.example'}
    event={**event,'url':'https://evil.example/show','source_id':source['id'],'sources':['https://evil.example/show']}
    assert verify(event,source,at)=='unverified_origin'


@pytest.mark.parametrize('body,expected',[
 ('Urla Ot Bayramı 27 Mart 2026 Cuma 28 Mart 2026 Cumartesi 29 Mart 2026 Pazar',('2026-03-27','2026-03-29')),
 ('Barbaros Oyuk Festivali 21, 22 ve 23 Ağustos 2026',('2026-08-21','2026-08-23'))])
def test_explicit_festival_days_and_years_are_preserved(body,expected):
    sid='urla-ot' if body.startswith('Urla') else 'barbaros-oyuk'
    item=program_items('<main>'+body+'</main>',SOURCES[sid]['url'],SOURCES[sid])[0]
    assert item['start'].startswith(expected[0]) and item['end'].startswith(expected[1]) and not item['time_known']


@pytest.mark.parametrize('body',['Urla Ot Bayramı 25 Aralık','Urla Ot Bayramı 27 Mart 2025 ve 28 Mart 2026',
                                'Urla Ot Bayramı 1 Mart 2026 ve 29 Mart 2026'])
def test_yearless_or_ambiguous_programs_are_not_invented(body):
    with pytest.raises(ValueError):program_items(body,SOURCES['urla-ot']['url'],SOURCES['urla-ot'])


def test_collection_wrapper_requires_real_success_and_bounded_list():
    assert public_collection('{"ok":true,"data":[]}')==[]
    for value in ('{"ok":false,"data":[]}','{"data":[]}','[]','<html>challenge</html>'):
        with pytest.raises(ValueError):public_collection(value)


def test_mobile_warning_list_uses_reviewed_desktop_detail_without_borrowing_list_date():
    source=SOURCES['mgm']
    body=fixture('mgm').replace('İzmir ve Manisa’nın kuzeyinde','Seferihisar ve Urla ilçelerinde')
    detail='https://www.mgm.gov.tr/tahmin/uyari-goster.aspx?sN=26010510y'
    class Fetcher:
        def __init__(self):self.calls=[]
        def get(self,url):
            self.calls.append(url)
            return ('<a href="tahmin-uyari-goster.aspx?sN=26010510y">Uyarı</a>',url) if url==source['url'] else (body,url)
    fetcher=Fetcher();items,_,errors=collect_source(source,fetcher,[])
    assert not errors and len(items)==1 and fetcher.calls==[source['url'],detail]
    assert items[0]['published_at']=='2026-10-13T15:10:00+03:00'


def test_reviewed_local_source_links_are_checked_before_unrelated_card_budget():
    source={**SOURCES['rotary2440'],'max_pages':1}
    local_url=source['reviewed_local_prefixes'][0]
    source_body='<li>Urla konseri<a href="https://rotary2440.org/etkinlikler/other">Konser</a></li>'
    source_body+='<a href="'+local_url+'">İlker ÖZDEMİR Konseri</a>'
    class Fetcher:
        def __init__(self):self.calls=[]
        def get(self,url):
            self.calls.append(url)
            return (source_body,url) if url==source['url'] else (fixture('rotary'),url)
    fetcher=Fetcher();items,_,errors=collect_source(source,fetcher,[])
    assert not errors and len(items)==1 and fetcher.calls==[source['url'],local_url]


def test_new_sources_are_connected_and_unreadable_catalogue_entries_are_explicit():
    for sid in ('afad','mgm','biletix','biletinial','bubilet','biletino','rotary2440','seferihisar-hastane','izmir-kultur','urla-ot','barbaros-oyuk'):
        assert SOURCES[sid]['enabled'] and SOURCES[sid]['trusted']
    assert not SOURCES['gdz']['enabled']
    catalogue=json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))
    assert not [r for r in catalogue if r['status']=='reader_pending']


def test_web_crawler_does_not_approve_social_hosts_from_api_source_profiles():
    from seferihisar.collect import Fetcher
    reader=Fetcher([SOURCES['seferihisar-belediye'],SOURCES['instagram-gundem']])
    assert reader.hosts=={'seferihisar.bel.tr'}
    assert 'www.instagram.com' not in reader.hosts and 'graph.facebook.com' not in reader.hosts
