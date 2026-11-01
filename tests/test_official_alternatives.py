import json
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.domain import TZ
from seferihisar.collect import collect_source
from seferihisar.editor import caption,verify
from seferihisar.schedule import prepare,source_current
from seferihisar.security import validate_state
from seferihisar.source_readers import collect_gdz_planned,gdz_planned_items,official_notice_items
from seferihisar.store import Store

SOURCES={s['id']:s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
AT=datetime(2026,10,14,16,0,tzinfo=TZ)

def row(**changes):
    return {'Kesinti_ID':'3838420','Durum':'Planlandı','Sehir':'İZMİR','Ilce':'URLA',
            'Mahalle':['Altıntaş','İçmeler'],'MahalleSokak':[{'Mahalle':'Altıntaş','Sokak':['1000. Sk.']}],
            'Kesinti_Nedeni':'Şebeke Bakım Çalışması',
            'Planlanan_Baslangic_Zamani':'2026-10-15 09:30:00.139',
            'Planlanan_Sona_Erme_Zamani':'2026-10-15 17:30:00.696',**changes}

def read(rows,district='URLA',known=()):
    body=json.dumps({'success':True,'level':'district_outages','city':'İZMİR','district':district,'data':rows,'count':len(rows)})
    return gdz_planned_items(body,SOURCES['gdz']['url'],SOURCES['gdz'],district,AT,known)

def response(district,rows=()):
    rows=list(rows)
    return json.dumps({'success':True,'level':'district_outages','city':'İZMİR','district':district,'data':rows,'count':len(rows)})

def gdz_collect(monkeypatch,replies):
    fetcher=Mock()
    fetcher.get.side_effect=[(body,SOURCES['gdz']['url']) for body in replies]
    naps=[]
    monkeypatch.setattr('seferihisar.source_readers.now',lambda:AT)
    monkeypatch.setattr('seferihisar.source_readers.time.sleep',naps.append)
    return collect_gdz_planned(SOURCES['gdz'],fetcher,())+(fetcher,naps)

DISTRICTS=('SEFERİHİSAR','URLA','GÜZELBAHÇE','MENDERES')

def test_gdz_broken_body_is_read_once_more_after_a_pause(monkeypatch):
    found,_,errors,fetcher,naps=gdz_collect(monkeypatch,['<html>']*4+[response('SEFERİHİSAR'),response('URLA',[row()]),response('GÜZELBAHÇE'),response('MENDERES')])
    assert len(found)==1 and errors==[] and fetcher.get.call_count==8 and naps==[20]

def test_gdz_second_read_covers_only_the_failed_district(monkeypatch):
    found,_,errors,fetcher,naps=gdz_collect(monkeypatch,[response('SEFERİHİSAR'),'<html>',response('GÜZELBAHÇE'),response('MENDERES'),response('URLA',[row()])])
    assert len(found)==1 and errors==[] and fetcher.get.call_count==5 and naps==[20]

def test_gdz_still_reports_a_district_that_stays_broken(monkeypatch):
    found,_,errors,fetcher,naps=gdz_collect(monkeypatch,[response(d) for d in DISTRICTS[:1]]+['<html>']+[response(d) for d in DISTRICTS[2:]]+['<html>'])
    assert errors==[{'source_id':'gdz','code':'detail_parse_failed'}] and fetcher.get.call_count==5 and naps==[20]

def test_gdz_healthy_read_does_not_pause(monkeypatch):
    found,_,errors,fetcher,naps=gdz_collect(monkeypatch,[response(d) for d in DISTRICTS])
    assert errors==[] and fetcher.get.call_count==4 and naps==[]

def test_future_planned_interval_has_no_invented_article_date_or_fees():
    item=read([row()])[0]
    assert item['kind']=='event' and item['category']=='outage'
    assert 'published_at' not in item
    assert item['start']=='2026-10-15T09:30:00.139000+03:00'
    assert item['valid_until']==item['end'] and verify(item,SOURCES['gdz'],AT) is None
    text=caption(item,item['title'])
    assert '09:30 – 17:30' in text and 'Altıntaş' in text
    assert 'Ücret' not in text and 'Etkinlik' not in text and '#elektrikkesintisi' in text

@pytest.mark.parametrize('changes',[
    {'Durum':'Arşivlendi'}, {'Durum':'Planlı Kesinti İptal Edildi'}, {'type':'unplanned'},
    {'Planlanan_Sona_Erme_Zamani':None}, {'Planlanan_Baslangic_Zamani':'15 Ekim'},
    {'Planlanan_Baslangic_Zamani':'2026-10-15 18:00:00'},
    {'Planlanan_Baslangic_Zamani':'2026-10-12 10:00:00','Planlanan_Sona_Erme_Zamani':'2026-10-12 17:00:00'},
    {'Sehir':'MANİSA'}, {'Ilce':'KONAK'}, {'Kesinti_ID':'../../private'},
])
def test_archives_cancellations_unknown_ends_and_foreign_rows_do_not_become_alerts(changes):
    assert not read([row(**changes)])

def test_unknown_menderes_neighborhood_is_not_ozdere_even_if_street_mentions_orhanli():
    outside=row(Ilce='MENDERES',Mahalle=['Kuyucak'],MahalleSokak=[{'Mahalle':'Kuyucak','Sokak':['Menderes Orhanlı Yolu']}])
    assert not read([outside],'MENDERES')
    assert not read([row(Ilce='MENDERES',Mahalle=['Cumhuriyet'])],'MENDERES')
    local=row(Ilce='MENDERES',Mahalle=['Çukuraltı','Görece'],MahalleSokak=[
        {'Mahalle':'Çukuraltı','Sokak':['2050. Sk.']},{'Mahalle':'Görece','Sokak':['FOREIGN STREET']}])
    item=read([local],'MENDERES')[0]
    assert 'Özdere' in item['location'] and '2050. Sk.' in item['description']
    assert 'Görece' not in item['description'] and 'FOREIGN STREET' not in item['description']

def test_outage_id_survives_date_change_and_only_existing_cancelled_record_is_updated():
    first=read([row()])[0]
    changed=read([row(Planlanan_Baslangic_Zamani='2026-10-16 09:30:00',Planlanan_Sona_Erme_Zamani='2026-10-16 17:30:00')])[0]
    assert first['identity']==changed['identity'] and first['start']!=changed['start']
    cancelled=read([row(Durum='Planlı Kesinti İptal Edildi')],known=[first])[0]
    assert cancelled['identity']==first['identity'] and cancelled['status']=='cancelled'


def test_explicit_early_completion_expires_existing_plan_without_a_new_archive_alert():
    known=read([row(Planlanan_Baslangic_Zamani='2026-10-14 10:00:00',Planlanan_Sona_Erme_Zamani='2026-10-14 17:00:00')])[0]
    archived=row(Durum='Arşivlendi',Planlanan_Baslangic_Zamani='2026-10-14 10:00:00',
                 Planlanan_Sona_Erme_Zamani='2026-10-14 17:00:00',Kesinti_Sona_Erme_Zamani='2026-10-14 10:39:45')
    assert not read([archived])
    item=read([archived],known=[known])[0]
    assert item['identity']==known['identity'] and item['valid_until']=='2026-10-14T10:39:45+03:00'
    assert not source_current({**item,'last_seen':AT.isoformat()},AT,set())
    with pytest.raises(ValueError):read([{**archived,'Kesinti_Sona_Erme_Zamani':None}],known=[known])

@pytest.mark.parametrize('body',['<html>protected</html>','{}',
    '{"success":true,"level":"cities","city":"İZMİR","district":"URLA","data":[],"count":0}',
    '{"success":true,"level":"district_outages","city":"İZMİR","district":"URLA","data":[],"count":2}'])
def test_wrong_api_shape_is_failure_not_healthy_empty(body):
    with pytest.raises(ValueError):gdz_planned_items(body,'',SOURCES['gdz'],'URLA',AT)

def test_fetches_only_four_approved_districts_and_surfaces_failure(monkeypatch):
    monkeypatch.setattr('seferihisar.source_readers.now',lambda:AT)
    f=Mock()
    import requests
    def get(url):
        from urllib.parse import parse_qs,urlsplit
        district=parse_qs(urlsplit(url).query)['district'][0]
        if district=='MENDERES':raise requests.Timeout('api_key=PRIVATE_VALUE')
        rows=[row()] if district=='URLA' else []
        return json.dumps({'success':True,'level':'district_outages','city':'İZMİR','district':district,'data':rows,'count':len(rows)}),url
    f.get.side_effect=get
    items,_,errors=collect_source(SOURCES['gdz'],f,[])
    assert len(items)==1 and f.get.call_count==4
    assert errors==[{'source_id':'gdz','code':'detail_timeout'}]

def test_service_is_one_notice_not_party_digest_or_recurring_event_reminder(tmp_path):
    item=read([row()])[0]
    db=Store(tmp_path/'state.sqlite');db.upsert(item,AT.isoformat());prepare(db,AT)
    posts=db.posts()
    assert len(posts)==1 and posts[0]['kind']=='announcement'
    assert posts[0]['formats']==['feed','story'] and '09:30 – 17:30' in posts[0]['slides'][0]['body']
    stored=db.items()[0];assert source_current(stored,AT,set())
    assert not source_current(stored,datetime(2026,10,15,17,31,tzinfo=TZ),set())
    before=deepcopy(posts[0]);prepare(db,AT+timedelta(minutes=10))
    assert len(db.posts())==1 and db.posts()[0]['id']==before['id']
    db.close();validate_state(tmp_path/'state.sqlite')

def notice(body,title='Kamu duyurusu',date='13.10.2026'):
    return '<h2 class="page-title">'+title+'</h2><div class="dateandtag"><div class="card-date">'+date+'</div></div><div class="icerik">'+body+'</div>'

def test_official_notice_uses_own_date_and_body_without_sidebar_location_or_warning_guess():
    source=SOURCES['izmir-valilik'];url='https://www.izmir.gov.tr/example'
    assert not official_notice_items(notice('Bornova ilçesinde nüfus müdürlüğü açık olacak.')+'<footer>Seferihisar</footer>',url,source)
    assert not official_notice_items(notice('Seferihisar’da fırtına uyarısı yayımlandı.',title='Fırtına uyarısı'),url,source)
    assert not official_notice_items(notice('Seferihisar kamu duyurusu.',date='')+'<footer>14.10.2026</footer>',url,source)
    items=official_notice_items(notice('Güzelbahçe ilçesinde yeni kamu duyuru hizmeti başlatıldı.'),url,source)
    assert len(items)==1 and items[0]['published_at']=='2026-10-13T00:00:00+03:00'

def test_official_alternatives_are_profile_verified_and_old_bademler_date_is_not_guessed():
    assert SOURCES['gdz']['enabled'] and SOURCES['gdz']['kind']=='gdz_planned'
    assert SOURCES['instagram-teos']['verified_profile_link']=='https://www.teoskultursanat.com/hakkimizda/iletisim/'
    catalog={e['id']:e for e in json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))}
    assert catalog['bademler']['status']=='date_missing'
    assert catalog['guzelbahce-kaymakamlik']['status']=='access_failed'
