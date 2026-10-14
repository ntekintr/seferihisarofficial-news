import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from seferihisar import instagram_sources as reader
from seferihisar.pipeline import run
from seferihisar.security import validate_state
from seferihisar.store import Store


@pytest.fixture
def ig_source():
    return {'id':'instagram-local','name':'Yerel haber Instagram','url':'https://www.instagram.com/local.news/',
            'kind':'instagram_api','enabled':True,'trusted':True,'access':'api','instagram_username':'local.news'}


def account(at):
    return {'username':'local.news','media':{'data':[{'id':'12345',
        'caption':'Seferihisar’da yeni otobüs güzergâhı\nSeferihisar belediyesi ulaşım hattında yeni düzenlemeyi duyurdu.',
        'permalink':'https://www.instagram.com/p/ABC123456/','timestamp':at.isoformat()}]}}


class Response:
    def __init__(self, data, status=200):
        self.body=json.dumps(data).encode();self.status_code=status;self.closed=False
    def iter_content(self,size):
        yield self.body
    def close(self):self.closed=True


class Session:
    def __init__(self,data,status=200):self.calls=[];self.response=Response(data,status)
    def get(self,*args,**kwargs):self.calls.append((args,kwargs));return self.response


def test_get_only_fixed_graph_origin_header_and_bounded_fields(ig_source,at,monkeypatch):
    monkeypatch.setattr(reader,'safe_url',lambda url,hosts:url)
    session=Session({'business_discovery':account(at)})
    result=reader.read_account(ig_source,'dummy-private-key','123456789','v26.0',session)
    assert result['username']=='local.news' and session.response.closed
    args,kw=session.calls[0]
    assert args==('https://graph.facebook.com/v26.0/123456789',)
    assert kw['allow_redirects'] is False and kw['stream'] is True
    assert kw['headers']=={'Authorization':'Bearer dummy-private-key'}
    assert set(kw['params'])=={'fields'} and 'media.limit(12)' in kw['params']['fields']
    assert 'media_url' not in kw['params']['fields'] and 'access_token' not in str(kw['params'])


@pytest.mark.parametrize('value',['seferihisarofficial','name){id}','../name','',None])
def test_unapproved_or_self_handle_never_sends_a_request(ig_source,value):
    ig_source['instagram_username']=value
    session=Session({})
    with pytest.raises(reader.SourceReadError):reader.read_account(ig_source,'key','123456789','v26.0',session)
    assert not session.calls


@pytest.mark.parametrize('code,expected',[(190,'instagram_token_expired'),(10,'instagram_permission_required'),
    (200,'instagram_permission_required'),(4,'instagram_rate_limited'),(100,'instagram_source_unavailable'),(999,'instagram_read_failed')])
def test_controlled_errors_discard_api_response(ig_source,monkeypatch,code,expected):
    monkeypatch.setattr(reader,'safe_url',lambda url,hosts:url)
    session=Session({'error':{'code':code,'message':'PRIVATE RESPONSE ACCESS_TOKEN=EAA_PRIVATE_VALUE'}},400)
    with pytest.raises(reader.SourceReadError) as exc:reader.read_account(ig_source,'key','123456789','v26.0',session)
    assert exc.value.code==expected and 'PRIVATE' not in str(exc.value) and session.response.closed


def test_redirect_and_foreign_account_are_closed(ig_source,at,monkeypatch):
    monkeypatch.setattr(reader,'safe_url',lambda url,hosts:url)
    for s in (Session({},302),Session({'business_discovery':{**account(at),'username':'other'}})):
        with pytest.raises(reader.SourceReadError):reader.read_account(ig_source,'key','123456789','v26.0',s)
        assert len(s.calls)==1 and s.response.closed


def test_caption_preserves_real_publication_time_and_public_permalink(ig_source,at):
    item=reader.caption_items(account(at),ig_source,at)[0]
    assert item['published_at']==at.isoformat() and item['identity']=='https://www.instagram.com/p/ABC123456'
    assert 'id' not in item and item['sources']==[item['url']]


@pytest.mark.parametrize('changes',[
    {'permalink':'https://evil.example/p/ABC123456/'},
    {'permalink':'https://www.instagram.com/p/ABC123456/?access_token=private'},
    {'caption':'#seferihisar\nİstanbul ulaşım hattında yeni düzenleme açıklaması yapıldı.'},
    {'caption':'Seferihisar konserine katılın! Saat: 20:00. Tarih ayrıca duyurulacak.'},
    {'timestamp':''},
])
def test_unknown_location_event_date_or_private_links_withheld(ig_source,at,changes):
    data=account(at);data['media']['data'][0].update(changes)
    assert not reader.caption_items(data,ig_source,at)


def test_event_timestamp_is_never_used_as_show_date(ig_source,at):
    data=account(at);data['media']['data'][0]['caption']='Urla tiyatro gösterisine katılın! Tarih: 14.10.2026\nSaat: 20:00\nYer: Urla Kültür Merkezi'
    item=reader.caption_items(data,ig_source,at)[0]
    assert item['kind']=='event' and item['start']=='2026-10-14T20:00:00+03:00'
    assert 'published_at' not in item and item['location']=='Urla Kültür Merkezi'


def public_manifest(source,at):
    return {'schema_version':1,'generated_at':at.isoformat(),'items':reader.caption_items(account(at),source,at),
            'health':[{'source_id':source['id'],'checked_at':at.isoformat(),'status':'ok','code':None,'parsed':1}]}


@pytest.mark.parametrize('mutation',['stale','unknown_field','foreign_source','unknown_code','bad_count','private_url','login_url','credential'])
def test_manifest_validation_rejects_tampering(tmp_path,ig_source,at,mutation):
    data=public_manifest(ig_source,at)
    if mutation=='stale':data['generated_at']=(at-timedelta(hours=2)).isoformat()
    elif mutation=='unknown_field':data['access_token']='PRIVATE_VALUE'
    elif mutation=='foreign_source':data['items'][0]['source_id']='other'
    elif mutation=='unknown_code':data['health'][0]['code']='PRIVATE_RESPONSE'
    elif mutation=='bad_count':data['health'][0]['parsed']=12
    elif mutation=='private_url':data['items'][0]['url']='https://graph.facebook.com/123456'
    elif mutation=='login_url':data['items'][0]['url']='https://www.instagram.com/login/'
    elif mutation=='credential':data['items'][0]['description']='access_token=PRIVATE_SECRET'
    path=tmp_path/'manifest.json';path.write_text(json.dumps(data))
    items,health=reader.consume(path,[ig_source],at)
    assert not items and health[0]['code']=='instagram_manifest_invalid'


def test_valid_manifest_integrates_health_without_api_credentials(tmp_path,ig_source,at):
    cfg=tmp_path/'sources.json';cfg.write_text(json.dumps([ig_source]))
    path=tmp_path/'manifest.json';path.write_text(json.dumps(public_manifest(ig_source,at)))
    with patch('seferihisar.pipeline.collect_source') as web:
        run(tmp_path/'db.sqlite',tmp_path/'public',cfg,at,instagram_manifest=path)
    assert not web.called
    store=Store(tmp_path/'db.sqlite')
    assert len(store.items())==1
    health=store.rows('SELECT * FROM source_health')[0]
    assert health['status']=='ok' and health['accepted']==1
    validate_state(store.path);store.close()


def test_missing_manifest_records_failure_without_crawling_instagram(tmp_path,ig_source,at):
    cfg=tmp_path/'sources.json';cfg.write_text(json.dumps([ig_source]))
    with patch('seferihisar.pipeline.collect_source') as web:
        run(tmp_path/'db.sqlite',tmp_path/'public',cfg,at)
    assert not web.called
    store=Store(tmp_path/'db.sqlite')
    assert not store.items() and store.rows('SELECT * FROM source_health')[0]['status']=='failed'
    assert 'instagram_manifest_missing' in store.rows('SELECT errors FROM runs')[0]['errors']
    store.close()


def test_global_permission_error_stops_further_calls(ig_source,at,monkeypatch):
    monkeypatch.setattr(reader,'now',lambda:at)
    other={**ig_source,'id':'second','instagram_username':'second','url':'https://www.instagram.com/second/'}
    with patch.object(reader,'read_account',side_effect=reader.SourceReadError('instagram_permission_required')) as read:
        result=reader.manifest([ig_source,other],at,Session({}))
    assert read.call_count==1 and len(result['health'])==2 and not result['items']
    assert {r['code'] for r in result['health']}=={'instagram_permission_required'}


def test_target_unavailable_error_does_not_stop_other_sources(ig_source,at,monkeypatch):
    monkeypatch.setattr(reader,'now',lambda:at)
    monkeypatch.setattr(reader,'safe_url',lambda url,hosts:url)
    monkeypatch.setenv('IG_SOURCE_ACCESS_TOKEN','dummy-private-key')
    monkeypatch.setenv('IG_SOURCE_USER_ID','123456789')
    other={**ig_source,'id':'second','instagram_username':'second','url':'https://www.instagram.com/second/'}
    responses=[Response({'error':{'code':110,'error_subcode':2207013,
                                  'message':'PRIVATE_RESPONSE target account unavailable'}},400),
               Response({'business_discovery':{**account(at),'username':'second'}})]
    session=Session({})
    session.get=lambda *args,**kwargs:responses.pop(0)
    result=reader.manifest([ig_source,other],at,session)
    assert not responses
    assert result['health'][0]['code']=='instagram_source_unavailable'
    assert result['health'][0]['status']=='failed'
    assert result['health'][1]['status']=='ok'
    assert len(result['items'])==1 and result['items'][0]['source_id']=='second'
    assert 'PRIVATE_RESPONSE' not in json.dumps(result)


def test_unknown_110_subcode_keeps_generic_read_failure(ig_source,monkeypatch):
    monkeypatch.setattr(reader,'safe_url',lambda url,hosts:url)
    session=Session({'error':{'code':110,'error_subcode':999}},400)
    with pytest.raises(reader.SourceReadError) as exc:
        reader.read_account(ig_source,'key','123456789','v26.0',session)
    assert exc.value.code=='instagram_read_failed'


@pytest.mark.parametrize('caption',[
 'Seferihisar elektrik kesintisi duyurusu. Tarih: 10.10.2026 Saat: 08:00–09:00',
 'Seferihisar elektrik kesintisi duyurusu. Tarih: 10 Ekim Saat: 10:00–13:00',
 'Seferihisar fırtına uyarısı. Tarih: 10 Ekim 2026. Uyarının bitişi açıklanmadı.',
 'Seferihisar elektrik kesintisi duyurusu. Tarih: 10 Ekim 2026. Saat: 23:00–02:00',
 'Seferihisar elektrik kesintisi duyurusu. 10 Ekim 2026 ve 11 Ekim 2026. Saat: 10:00–13:00',
])
def test_expired_yearless_or_ambiguous_service_caption_is_not_published(ig_source,at,caption):
    data=account(at);data['media']['data'][0]['caption']=caption
    assert not reader.caption_items(data,ig_source,at)


def test_explicit_service_end_is_preserved_in_public_manifest(ig_source,at):
    data=account(at);data['media']['data'][0]['caption']='Seferihisar elektrik kesintisi duyurusu\nTarih: 10 Ekim 2026\nSaat: 10:00–13:00\nPlanlı bakım çalışması.'
    item=reader.caption_items(data,ig_source,at)[0]
    assert item['valid_until']=='2026-10-10T13:00:00+03:00' and item['kind']=='news'
    manifest={'schema_version':1,'generated_at':at.isoformat(),'items':[item],
              'health':[{'source_id':ig_source['id'],'checked_at':at.isoformat(),'status':'ok','code':None,'parsed':1}]}
    reader.validate_manifest(manifest,[ig_source],at)


def test_old_official_instagram_earthquake_update_expires_even_if_api_read_is_fresh(ig_source,at):
    source={**ig_source,'id':'instagram-afad'}
    data=account(at);data['media']['data'][0].update(caption='AFAD kaydı: Seferihisar yakınlarında deprem. Resmî açıklama yayımlandı.',timestamp=(at-timedelta(hours=4)).isoformat())
    assert not reader.caption_items(data,source,at)
    data['media']['data'][0]['timestamp']=(at-timedelta(hours=1)).isoformat()
    item=reader.caption_items(data,source,at)[0]
    assert item['valid_until']==(at+timedelta(hours=2)).isoformat()
