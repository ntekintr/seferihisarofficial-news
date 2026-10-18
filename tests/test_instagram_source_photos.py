"""GET isolation, source binding, artifact tampering and publisher retention."""
import io
import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar import instagram_sources as captions
from seferihisar import instagram_source_photos as photos
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.security import validate_state
from seferihisar.source_photo_data import INSTAGRAM_VERSION,validate_record
from seferihisar.source_photos import SourcePhotos,binding_reason
from seferihisar.visual_gate import review,valid_review
from seferihisar.visual_match import MatchRejected,MatchUnavailable

SOURCE={'id':'instagram-local','name':'Yerel haber Instagram','url':'https://www.instagram.com/local.news/',
        'kind':'instagram_api','enabled':True,'trusted':True,'access':'api','instagram_username':'local.news'}
CDN='https://scontent-ams2-1.cdninstagram.com/v/t51.123/meeting.jpg?oh=EPHEMERAL_SIGNATURE&oe=abc&_nc_cat=1'


def account(at):
    return {'username':'local.news','media':{'data':[{'id':'12345678901234567','media_type':'IMAGE','media_url':CDN,
        'caption':'Seferihisar’da muhtarlar bir araya geldi\nToplantıda Seferihisar mahallelerinin ihtiyaçları görüşüldü.',
        'permalink':'https://www.instagram.com/p/ABC123456/','timestamp':at.isoformat()}]}}


def caption_file(tmp_path,at,data=None):
    items=captions.caption_items(data or account(at),SOURCE,at)
    value={'schema_version':1,'generated_at':at.isoformat(),'items':items,
           'health':[{'source_id':SOURCE['id'],'checked_at':at.isoformat(),
                      'status':'ok' if items else 'empty','code':None,'parsed':len(items)}]}
    path=tmp_path/'public.json';path.write_text(json.dumps(value),encoding='utf8');return path,items


def jpeg():
    stream=io.BytesIO();exif=Image.Exif();exif[270]='PRIVATE_METADATA'
    Image.new('RGB',(1100,650),'#938566').save(stream,'JPEG',exif=exif)
    return stream.getvalue()


def image_client(raw=None,status=200,mime='image/jpeg'):
    response=Mock();response.status_code=status;response.headers={'Content-Type':mime}
    response.iter_content.return_value=[raw if raw is not None else jpeg()]
    response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    client=Mock();client.get.return_value=response;return client


def artifact(tmp_path,at,monkeypatch,data=None):
    path,items=caption_file(tmp_path,at)
    monkeypatch.setattr(photos,'read_account',Mock(return_value=data or account(at)))
    monkeypatch.setattr(photos,'safe_url',lambda url,hosts:url)
    client=image_client()
    index,blobs=photos.build(path,[SOURCE],at,graph=Mock(),images=client)
    (tmp_path/'photos').mkdir(exist_ok=True)
    for sha,image in blobs.items():(tmp_path/'photos'/(sha.replace(':','')+'.jpg')).write_bytes(image)
    (tmp_path/'photos.json').write_text(json.dumps(index),encoding='utf8')
    return path,items,index,blobs,client


def test_optional_media_fields_use_same_fixed_get_and_keep_base_caption_query(at,monkeypatch):
    from test_instagram_sources import Session
    monkeypatch.setattr(captions,'safe_url',lambda url,hosts:url)
    session=Session({'business_discovery':account(at)})
    captions.read_account(SOURCE,'private-test-key','987654321','v26.0',session,photos=True)
    args,kw=session.calls[0]
    assert args==('https://graph.facebook.com/v26.0/987654321',)
    assert kw['headers']=={'Authorization':'Bearer private-test-key'} and not kw['allow_redirects']
    assert 'media_url' in kw['params']['fields'] and 'media_type' in kw['params']['fields']
    assert 'children' not in kw['params']['fields']


def test_single_photo_has_no_cdn_signature_metadata_or_credential_in_artifact(tmp_path,at,monkeypatch):
    path,items,index,blobs,client=artifact(tmp_path,at,monkeypatch)
    assert index['checks']==[{'source_id':SOURCE['id'],'status':'available'}]
    assert len(blobs)==1 and b'PRIVATE_METADATA' not in next(iter(blobs.values()))
    serialized=json.dumps(index)
    assert 'EPHEMERAL_SIGNATURE' not in serialized and 'cdninstagram' not in serialized and 'media_url' not in serialized
    args,kw=client.get.call_args
    assert args==(CDN,) and kw=={'timeout':(8,15),'stream':True,'allow_redirects':False}
    found,checks=photos.consume_photos(path,[SOURCE],at)
    assert checks['available']==1 and found[items[0]['url']][0]['version']==INSTAGRAM_VERSION
    assert photos.read_account.call_args.kwargs=={'photos':True}


@pytest.mark.parametrize('url',[
    'http://scontent.cdninstagram.com/a.jpg','https://scontent.cdninstagram.com.evil.example/a.jpg',
    'https://cdninstagram.com/a.jpg','https://127.0.0.1/a.jpg',
    'https://scontent.cdninstagram.com:444/a.jpg','https://user@ scontent.cdninstagram.com/a.jpg',
    'https://scontent.cdninstagram.com/a.mp4','https://scontent.cdninstagram.com/a.jpg#fragment',
    'https://scontent.cdninstagram.com/a.jpg?access_token=private',
])
def test_unapproved_media_destination_never_downloads(url):
    client=Mock()
    with pytest.raises(ValueError):photos.download(url,client)
    client.get.assert_not_called()


def test_cdn_still_uses_global_dns_check(monkeypatch):
    monkeypatch.setattr('seferihisar.collect.socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(ValueError):photos.cdn_url(CDN)


@pytest.mark.parametrize('status,mime,raw',[(302,'image/jpeg',b''),(403,'image/jpeg',b''),
    (200,'text/html',b'<html>'),(200,'video/mp4',b'x'),(200,'image/jpeg',b'x'*2_000_001)],
    ids=['redirect','forbidden','html','video','oversized'])
def test_redirect_mime_and_size_rejected_without_retry(status,mime,raw,monkeypatch):
    monkeypatch.setattr(photos,'safe_url',lambda url,hosts:url)
    client=image_client(raw,status,mime)
    with pytest.raises(ValueError):photos.download(CDN,client)
    assert client.get.call_count==1


@pytest.mark.parametrize('change',['video','carousel','changed_caption','changed_date','duplicate','bad_id','missing_url','archival'])
def test_unbound_ambiguous_nonimage_or_archival_media_stays_information_card(tmp_path,at,monkeypatch,change):
    data=account(at);row=data['media']['data'][0]
    if change in ('video','carousel'):row['media_type']='VIDEO' if change=='video' else 'CAROUSEL_ALBUM'
    elif change=='changed_caption':row['caption']=row['caption'].replace('ihtiyaçları','yeni talepleri')
    elif change=='changed_date':row['timestamp']=(at-timedelta(hours=1)).isoformat()
    elif change=='duplicate':data['media']['data'].append(deepcopy(row))
    elif change=='bad_id':row['id']='../123'
    elif change=='missing_url':del row['media_url']
    else:row['caption']+=' Arşiv fotoğrafı.'
    path,items,index,blobs,client=artifact(tmp_path,at,monkeypatch,data)
    assert not index['photos'] and not blobs
    client.get.assert_not_called()
    assert captions.consume(path,[SOURCE],at)[0]==items


def test_optional_permission_failure_keeps_caption_manifest_and_makes_no_download(tmp_path,at,monkeypatch):
    path,items=caption_file(tmp_path,at)
    monkeypatch.setattr(photos,'read_account',Mock(side_effect=captions.SourceReadError('instagram_permission_required')))
    client=Mock()
    index,blobs=photos.build(path,[SOURCE],at,graph=Mock(),images=client)
    assert index['checks'][0]['status']=='api_unavailable' and not blobs
    assert captions.consume(path,[SOURCE],at)[0]==items
    client.get.assert_not_called()


def test_at_most_two_photo_candidates_and_one_graph_call_for_same_account(tmp_path,at,monkeypatch):
    data=account(at);first=data['media']['data'][0]
    data['media']['data']=[{**first,'id':str(12345678901234567+i),
        'permalink':'https://www.instagram.com/p/ABC12345'+str(i)+'/'} for i in range(5)]
    path,items=caption_file(tmp_path,at,data)
    monkeypatch.setattr(photos,'read_account',Mock(return_value=data))
    monkeypatch.setattr(photos,'safe_url',lambda url,hosts:url)
    client=image_client()
    index,blobs=photos.build(path,[SOURCE],at,graph=Mock(),images=client)
    assert len(index['checks'])==2 and photos.read_account.call_count==1 and client.get.call_count==2
    # Identical pixels are not exported as two distinct events.
    assert len(blobs)==len(index['photos'])==1


def test_no_extra_graph_read_when_caption_source_failed(tmp_path,at,monkeypatch):
    path,items=caption_file(tmp_path,at)
    manifest=json.loads(path.read_text(encoding='utf8'));manifest['items']=[]
    manifest['health'][0].update(status='failed',code='instagram_source_unavailable',parsed=0)
    path.write_text(json.dumps(manifest),encoding='utf8')
    graph=Mock();images=Mock();read=Mock();monkeypatch.setattr(photos,'read_account',read)
    result,blobs=photos.build(path,[SOURCE],at,graph=graph,images=images)
    assert not result['photos'] and not result['checks'] and not blobs
    read.assert_not_called();images.get.assert_not_called()


def test_unavailable_instagram_artifact_does_not_consume_web_photo_budget(store,tmp_path,at,monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    item=captions.caption_items(account(at),SOURCE,at)[0]
    item.update(id='a'*24,revision=1)
    fetcher=Mock();manager=SourcePhotos(store,at,tmp_path/'materialized',[SOURCE],fetcher=fetcher)
    assert manager.image(item) is None and manager.reads==0
    fetcher.get.assert_not_called()


@pytest.mark.parametrize('mutation',['stale','other_run','wrong_title','wrong_source','wrong_hash','extra_secret','missing_jpeg','changed_jpeg','unknown_field'])
def test_bad_artifact_never_affects_captions(tmp_path,at,monkeypatch,mutation):
    path,items,index,blobs,_=artifact(tmp_path,at,monkeypatch)
    photo=index['photos'][0];image_path=next((tmp_path/'photos').iterdir())
    if mutation=='stale':photo['checked_at']=(at-timedelta(hours=2)).isoformat()
    elif mutation=='other_run':index['generated_at']=(at-timedelta(minutes=1)).isoformat()
    elif mutation=='wrong_title':photo['title']='Seferihisar’da farklı bir toplantı'
    elif mutation=='wrong_source':photo['source_id']='foreign'
    elif mutation=='wrong_hash':photo['sha256']='ab:'*31+'ab'
    elif mutation=='extra_secret':photo['media_url']=CDN
    elif mutation=='missing_jpeg':image_path.unlink()
    elif mutation=='changed_jpeg':image_path.write_bytes(jpeg())
    else:index['path']='../../private'
    (tmp_path/'photos.json').write_text(json.dumps(index),encoding='utf8')
    found,checks=photos.consume_photos(path,[SOURCE],at)
    assert not found and checks['status']=='unavailable'
    assert captions.consume(path,[SOURCE],at)[0]==items


def test_photo_reaches_existing_gate_and_frozen_publisher_never_refetches(store,tmp_path,at,monkeypatch):
    path,raw_items,_,_,client=artifact(tmp_path,at,monkeypatch)
    found,checks=photos.consume_photos(path,[SOURCE],at)
    store.upsert(raw_items[0],at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at);post=store.posts()[0]
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    match=Mock();monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',match)
    manager=SourcePhotos(store,at,tmp_path/'materialized',[SOURCE],instagram_photos=found,instagram_checks=checks)
    assignments=manager.for_post(post,{item['id']:item})
    assert list(assignments)==[0] and match.call_count==1
    row=store.rows('SELECT * FROM source_photos')[0]
    value=validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
    assert value['media_id']=='12345678901234567' and 'image_url' not in value
    post['visual_review']=review(post,assignments,{item['id']:item})
    assert valid_review(post)
    assert binding_reason(store,post,{item['id']:item},at) is None
    assert binding_reason(store,post,{item['id']:item},at+timedelta(hours=2))=='visual_review_stale'
    post['status']='published'
    with store.db:store.db.execute('UPDATE posts SET payload=?,status=? WHERE id=?',(json.dumps(post),'published',post['id']))
    frozen=store.rows('SELECT * FROM source_photos')
    monkeypatch.delenv('ILLUSTRATIONS_ENABLED')
    publisher=SourcePhotos(store,at+timedelta(days=1),tmp_path/'publisher',[SOURCE])
    assert publisher.for_post(post,{item['id']:item})
    assert store.rows('SELECT * FROM source_photos')==frozen and client.get.call_count==1
    # Includes the stdlib-only validation used by the credentialed state writer.
    import builtins
    original=builtins.__import__
    def no_runtime(name,*args,**kwargs):
        if name.startswith(('PIL','requests','torch','transformers')):raise AssertionError('Runtime import in state writer')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',no_runtime)
    validate_state(store.path)


@pytest.mark.parametrize('error',[MatchRejected(),MatchUnavailable()])
def test_model_reject_or_missing_never_assigns_source_photo(store,tmp_path,at,monkeypatch,error):
    path,items,_,_,_=artifact(tmp_path,at,monkeypatch)
    found,_=photos.consume_photos(path,[SOURCE],at)
    store.upsert(items[0],at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at);post=store.posts()[0]
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',Mock(side_effect=error))
    manager=SourcePhotos(store,at,tmp_path/'materialized',[SOURCE],instagram_photos=found)
    assert not manager.for_post(post,{item['id']:item}) and not post.get('source_photo_keys')
    assert not store.rows('SELECT * FROM source_photos')


def test_pipeline_imports_artifact_without_meta_or_cdn_calls(store,tmp_path,at,monkeypatch):
    path,items,_,_,_=artifact(tmp_path,at,monkeypatch)
    store.upsert(items[0],at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',Mock())
    monkeypatch.setattr('requests.Session.get',Mock(side_effect=AssertionError('Unexpected network')))
    _export(store,tmp_path/'public',[SOURCE],at,instagram_manifest=path)
    result=json.loads((tmp_path/'public/data.json').read_text(encoding='utf8'))
    assert result['source_photos']['instagram']['available']==1
    post=store.posts()[0]
    assert post['source_photo_keys'] and valid_review(post)
