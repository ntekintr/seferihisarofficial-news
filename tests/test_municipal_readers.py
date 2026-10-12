import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from seferihisar.collect import Fetcher, collect_source, publication_date, structured, wordpress_items
from seferihisar.domain import local


def configured(name):
    return next(s for s in json.loads(Path('config/sources.json').read_text()) if s['id']==name)


def test_kaymakamlik_reads_dated_detail_without_schema_or_h1():
    src=configured('seferihisar-kaymakamlik')
    html='''<h2 class="page-title">Seferihisar kültür programı</h2>
    <div class="dateandtag"><div class="card-date">10.10.2026</div></div>
    <div class="icerik"><p>Seferihisar ilçesinin kültür programı resmî kaynakta açıklandı.</p></div>'''
    item=structured(html,'https://www.seferihisar.gov.tr/program',src)[0]
    assert item['published_at']=='2026-10-10T00:00:00+03:00'
    assert item['title']=='Seferihisar kültür programı'
    assert 'resmî kaynakta' in item['description']
    assert item['kind']=='news'


def test_kaymakamlik_listing_follows_actual_news_cards():
    src=configured('seferihisar-kaymakamlik')
    fetcher=Mock()
    fetcher.get.side_effect=[('<a class="news-card-horizontal" href="/program">Program</a><a href="/iletisim">İletişim</a>',src['url']),('', 'https://www.seferihisar.gov.tr/program')]
    collect_source(src,fetcher,[])
    assert [c.args[0] for c in fetcher.get.call_args_list]==[src['url'],'https://www.seferihisar.gov.tr/program']


def test_urla_uses_article_parent_timestamp_and_scoped_div_body():
    src=configured('urla-belediye')
    html='''<div class="content"><div><h1>Urla kitap tanıtım günleri</h1>
    1.10.2026 14:54:00 <div id="printableArea"><div>Urla kitap tanıtım günleri için etkinlik programı açıklandı.</div>
    <div>Tarih: 30 Ekim 2026</div><div>Saat: 18.00</div><div>Yer: Urla Kültür Merkezi</div></div></div>
    <aside><h1>SON HABERLER</h1><div class="date fr">12.10.2026 09:00</div><p>Seferihisar başka haber</p></aside></div>'''
    item=structured(html,'https://www.urla.bel.tr/HaberDetay/1/program',src)[0]
    assert item['kind']=='event' and item['start']=='2026-10-30T18:00:00+03:00'
    assert item['title']=='Urla kitap tanıtım günleri'
    assert item['location']=='Urla Kültür Merkezi'
    assert 'başka haber' not in item['description']


@pytest.mark.parametrize('stamp',['','32.10.2026','10.10.26','10.10.2026 25:00'])
def test_bad_or_missing_publication_date_cannot_borrow_sidebar_date(stamp):
    src=configured('urla-belediye')
    html=f'''<div class="content"><div><h1>Urla dans atölyesi</h1>{stamp}
    <div id="printableArea"><div>Urla dans atölyesi ile ilgili açıklamalar kaynakta yayımlandı.</div></div></div>
    <div class="date fr">10.10.2026 12:00</div></div>'''
    assert not structured(html,'https://www.urla.bel.tr/HaberDetay/1/program',src)


def test_urla_news_keeps_real_publication_time_instead_of_related_story_time():
    src=configured('urla-belediye')
    html='''<div class="content"><div><h1>Urla dans atölyesi</h1>5.10.2026 10:01:00
    <div id="printableArea"><div>Urla dans atölyesi programı resmî kaynakta açıklandı.</div></div></div>
    <aside><div class="date fr">01.10.2026 02:55</div></aside></div>'''
    assert structured(html,'https://www.urla.bel.tr/HaberDetay/1/program',src)[0]['published_at']=='2026-10-05T10:01:00+03:00'


def test_missing_source_specific_title_does_not_use_unrelated_heading():
    src=configured('seferihisar-kaymakamlik')
    html='''<h1>Seferihisar başka bir bölüm</h1><div class="dateandtag"><div class="card-date">10.10.2026</div></div>
    <div class="icerik"><p>Seferihisar kültür programı ve etkinlik duyurusu açıklandı.</p></div>'''
    assert not structured(html,'https://www.seferihisar.gov.tr/program',src)


@pytest.mark.parametrize('status,retry_after',[(503,None),(429,'2')])
def test_reviewed_transient_http_failure_retries_once(monkeypatch,status,retry_after):
    src=configured('haberturk'); fetcher=Fetcher([src])
    response=requests.Response(); response.status_code=status
    if retry_after:response.headers['Retry-After']=retry_after
    monkeypatch.setattr('seferihisar.collect.time.sleep',lambda _:None)
    monkeypatch.setattr(fetcher,'_get',Mock(side_effect=[requests.HTTPError(response=response),('public',src['url'])]))
    assert fetcher.get(src['url'])[0]=='public' and fetcher._get.call_count==2


def test_haberturk_search_cards_are_read_but_navigation_and_videos_are_excluded():
    src=configured('haberturk')
    search=src['listing_urls'][-1]
    assert search=='https://www.haberturk.com/arama/ozdere?tr=%C3%96zdere'
    # Isolate the observed alternative search template from the other districts.
    src={**src,'listing_urls':[search]}
    fetcher=Mock()
    fetcher.get.side_effect=[('''<a class="block" href="/ozdere-konseri-1234">Özdere konseri</a>
    <a class="block" href="/gundem">Gündem</a><a class="block" href="/video/izle/1234">Video</a>''',search),('', 'https://www.haberturk.com/ozdere-konseri-1234')]
    collect_source(src,fetcher,[])
    assert fetcher.get.call_args.args[0]=='https://www.haberturk.com/ozdere-konseri-1234'
    assert fetcher.get.call_count==2


def wp_post(**extra):
    return {'status':'publish','date_gmt':'2026-10-10T07:00:00',
            'link':'https://menderes.bel.tr/haberler/ozdere-konser/',
            'title':{'rendered':'Özdere konser programı'},
            'content':{'rendered':'<p>Özdere konser programı resmî kaynakta açıklandı.</p>'},**extra}


def test_menderes_public_api_news_uses_gmt_not_server_local_clock():
    src=configured('menderes-belediye')
    item=wordpress_items(json.dumps([wp_post()]),src['url'],src)[0]
    assert item['published_at']=='2026-10-10T10:00:00+03:00'
    assert item['url']=='https://menderes.bel.tr/haberler/ozdere-konser/'
    assert item['kind']=='news'


@pytest.mark.parametrize('extra',[
    {'status':'draft'}, {'status':'private'}, {'date_gmt':''}, {'date_gmt':'0000-00-00T00:00:00'},
    {'title':{'rendered':'Tekeli esnaf ziyareti'},'content':{'rendered':'Belediye ziyareti'}},
])
def test_menderes_drafts_missing_dates_and_out_of_scope_towns_are_not_collected(extra):
    src=configured('menderes-belediye')
    assert not wordpress_items(json.dumps([wp_post(**extra)]),src['url'],src)


def test_menderes_event_date_is_explicit_and_not_news_publication_date():
    src=configured('menderes-belediye')
    value=wp_post(content={'rendered':'<p>Özdere konser programı açıklandı.</p><p>Tarih: 30.10.2026</p><p>Saat: 20:30</p><p>Yer: Özdere</p>'})
    item=wordpress_items(json.dumps([value]),src['url'],src)[0]
    assert item['kind']=='event' and item['start']=='2026-10-30T20:30:00+03:00'


def test_menderes_api_lists_share_same_detail_budget_and_revisit_future_events(event):
    src=configured('menderes-belediye')
    fetcher=Mock()
    fetcher.get.side_effect=lambda url:(json.dumps([wp_post()]) if '/wp-json/' in url else '',url)
    items,_,errors=collect_source(src,fetcher,[])
    assert len(items)==2 and not errors and fetcher.get.call_count==2
    tracked={**event,'source_id':src['id'],'url':'https://menderes.bel.tr/haberler/ozdere-konser/'}
    fetcher.get.reset_mock()
    collect_source(src,fetcher,[tracked])
    assert fetcher.get.call_count==3 and fetcher.get.call_args.args[0]==tracked['url']


def test_transient_read_retry_is_bounded_per_host_and_never_bypasses_robots(monkeypatch):
    src={**configured('haberturk')}
    fetcher=Fetcher([src])
    monkeypatch.setattr('seferihisar.collect.time.sleep',lambda _:None)
    monkeypatch.setattr(fetcher,'_get',Mock(side_effect=[requests.Timeout(),('public','https://www.haberturk.com/ok'),requests.Timeout()]))
    assert fetcher.get(src['url'])[0]=='public'
    with pytest.raises(requests.Timeout):fetcher.get(src['url'])
    assert fetcher._get.call_count==3
    blocked=Fetcher([src])
    monkeypatch.setattr(blocked,'_get',Mock(side_effect=ValueError('robots.txt disallows this path')))
    with pytest.raises(ValueError):blocked.get(src['url'])
    assert blocked._get.call_count==1


@pytest.mark.parametrize('status,retry_after',[(403,None),(404,None),(429,'120'),(429,None)])
def test_explicit_denials_and_long_retry_after_do_not_trigger_retry(monkeypatch,status,retry_after):
    fetcher=Fetcher([configured('haberturk')])
    response=requests.Response(); response.status_code=status
    if retry_after:response.headers['Retry-After']=retry_after
    monkeypatch.setattr(fetcher,'_get',Mock(side_effect=requests.HTTPError(response=response)))
    with pytest.raises(requests.HTTPError):fetcher.get('https://www.haberturk.com/')
    assert fetcher._get.call_count==1


def test_expanded_cultural_topics_keep_routine_nearby_visits_out():
    assert local('Urla kitap tanıtım günleri')
    assert local('Güzelbahçe dans atölyesi')
    assert not local('Urla esnaf ziyareti')
