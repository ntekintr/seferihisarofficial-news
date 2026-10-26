"""Article provenance, bounded downloads and durable no-replay photo bindings."""
import io
import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from seferihisar.domain import parse_date
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.security import validate_state
from seferihisar.source_photo_data import key,validate_record
from seferihisar.source_photos import SourcePhotos,binding_reason,candidate,cleaned_photo,news_subject
from seferihisar.visual_gate import content_key,review,valid_review
from seferihisar.visual_match import MatchRejected,MatchUnavailable

AT=parse_date('2026-10-18T08:30:00+03:00')
SOURCE={'id':'local-paper','name':'Yerel gazete','url':'https://news.example/haberler','kind':'html',
        'enabled':True,'trusted':True,'access':'robots'}
NEWS={'kind':'news','category':'news','source_id':'local-paper','source_name':'Yerel gazete',
      'url':'https://news.example/seferihisar-muhtarlar','title':'Seferihisar’da muhtarlar bir araya geldi',
      'description':'Seferihisar’da muhtarlar bir araya geldi. Toplantıda mahallelerin talepleri görüşüldü.',
      'published_at':(AT-timedelta(hours=1)).isoformat(),'sources':['https://news.example/seferihisar-muhtarlar']}
PHOTO='https://news.example/uploads/meeting.jpg'


def html(item=NEWS):
    data={'@type':'NewsArticle','headline':item['title'],'description':item['description'],
          'datePublished':item['published_at']}
    return ('<link rel="canonical" href="'+item['url']+'"><meta property="og:image" content="'+PHOTO+'">'
            '<script type="application/ld+json">'+json.dumps(data)+'</script>'
            '<article><h1>'+item['title']+'</h1><p>'+item['description']+'</p>'
            '<img src="'+PHOTO+'" alt="Muhtarlar toplantısı">'
            '<aside><a href="https://news.example/other"><img src="https://news.example/other.jpg"></a></aside></article>')


def raw_photo(size=(1100,650)):
    exif=Image.Exif();exif[270]='PRIVATE_EXIF_TEST'
    stream=io.BytesIO();Image.new('RGB',size,'#92866b').save(stream,'JPEG',exif=exif)
    return stream.getvalue()


def seed(store):
    store.upsert(deepcopy(NEWS),AT.isoformat());item=store.items()[0]
    queue_item(store,item,'news',AT,AT)
    return item,store.posts()[0]


def manager(store,tmp_path,monkeypatch,at=AT):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',lambda data,expected:None)
    fetcher=Mock();fetcher.get.return_value=(html(),NEWS['url']);fetcher.image.return_value=(raw_photo(),PHOTO)
    return SourcePhotos(store,at,tmp_path,[SOURCE],fetcher=fetcher),fetcher


def test_actual_article_identity_and_primary_image_excludes_related_thumbnails():
    assert candidate(html(),NEWS['url'],NEWS,SOURCE)==PHOTO
    resized=html().replace('<img src="'+PHOTO,'<img src="'+PHOTO.replace('.jpg','-1100x650.jpg'))
    assert candidate(resized,NEWS['url'],NEWS,SOURCE)==PHOTO.replace('.jpg','-1100x650.jpg')


@pytest.mark.parametrize('change',[
    'title','date','canonical','final','archive','generated','foreign','logo','related','ambiguous','secret',
])
def test_unproven_default_archival_related_or_private_images_are_rejected(change):
    body=html();final=NEWS['url']
    if change=='title':body=body.replace(NEWS['title'],'Seferihisar’da başka bir toplantı')
    elif change=='date':body=body.replace(NEWS['published_at'],(AT-timedelta(days=3)).isoformat())
    elif change=='canonical':body=body.replace('rel="canonical" href="'+NEWS['url'],'rel="canonical" href="https://news.example/other')
    elif change=='final':final='https://news.example/login'
    elif change=='archive':body=body.replace('alt="Muhtarlar toplantısı"','alt="Arşiv görseli"')
    elif change=='generated':body=body.replace('alt="Muhtarlar toplantısı"','alt="Yapay zekâyla hazırlanmış görsel"')
    elif change=='foreign':body=body.replace(PHOTO,'https://other.example/meeting.jpg')
    elif change=='logo':body=body.replace(PHOTO,'https://news.example/logo.jpg')
    elif change=='related':body=body.replace('<img src="'+PHOTO,'<a href="https://news.example/other"><img src="'+PHOTO).replace('alt="Muhtarlar toplantısı">','alt="Muhtarlar toplantısı"></a>')
    elif change=='ambiguous':body=body.replace('property="og:image"','property="unrelated"').replace('</article>','<img src="https://news.example/second.jpg"></article>')
    else:body=body.replace(PHOTO,PHOTO+'?access_token=PRIVATE_QUERY_VALUE')
    with pytest.raises(ValueError):candidate(body,final,NEWS,SOURCE)


@pytest.mark.parametrize('size',[(100,100),(500,280),(400,1200),(2100,2000)])
def test_tiny_extreme_aspect_and_oversized_sources_are_rejected(size):
    with pytest.raises(ValueError):cleaned_photo(raw_photo(size))


def test_cleaned_pixels_have_no_original_metadata_and_state_writer_needs_no_pillow(store,tmp_path,monkeypatch):
    item,post=seed(store);photos,fetcher=manager(store,tmp_path,monkeypatch)
    assert b'PRIVATE_EXIF_TEST' in raw_photo()
    assignments=photos.for_post(post,{item['id']:item})
    assert list(assignments)==[0] and post['source_photo_keys']
    row=store.rows('SELECT * FROM source_photos')[0]
    assert b'PRIVATE_EXIF_TEST' not in row['image']
    value=validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
    assert value['source_url']==item['url'] and value['image_url']==PHOTO
    with Image.open(io.BytesIO(row['image'])) as image:
        assert image.size==(768,454) and not image.getexif()
    # Writer validation uses only the stdlib JPEG parser; block runtime imports.
    import builtins
    original=builtins.__import__
    def import_module(name,*args,**kwargs):
        if name.startswith(('PIL','torch','transformers','requests')):raise AssertionError('Runtime import in state writer')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',import_module)
    validate_state(store.path)
    assert not store.rows('SELECT * FROM illustration_days')
    assert fetcher.get.call_count==1 and fetcher.image.call_count==1


@pytest.mark.parametrize('error',[MatchRejected(),MatchUnavailable(),requests.Timeout('PRIVATE_PROVIDER_TEXT')])
def test_mismatch_model_missing_and_source_failure_assign_no_image_or_claim(store,tmp_path,monkeypatch,error):
    item,post=seed(store);photos,fetcher=manager(store,tmp_path,monkeypatch)
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',Mock(side_effect=error))
    if isinstance(error,requests.RequestException):fetcher.get.side_effect=error
    before=store.rows('SELECT * FROM posts')
    assert photos.for_post(post,{item['id']:item})=={}
    assert store.rows('SELECT * FROM posts')==before and not store.rows('SELECT * FROM source_photos')
    assert b'PRIVATE_PROVIDER_TEXT' not in store.path.read_bytes()


@pytest.mark.parametrize('state',['publishing','published','uncertain'])
def test_frozen_source_photo_payload_and_pixels_are_never_fetched_or_changed(store,tmp_path,monkeypatch,state):
    item,post=seed(store);photos,fetcher=manager(store,tmp_path,monkeypatch)
    assignments=photos.for_post(post,{item['id']:item});post['visual_review']=review(post,assignments,{item['id']:item})
    with store.db:store.db.execute('UPDATE posts SET payload=?,status=?',(json.dumps(post),state))
    before_posts=store.rows('SELECT * FROM posts');before_photos=store.rows('SELECT * FROM source_photos')
    later=SourcePhotos(store,AT+timedelta(days=2),tmp_path/'later',[SOURCE],fetcher=Mock())
    frozen=store.posts()[0];result=later.for_post(frozen,{item['id']:{**item,'revision':2,'title':'Changed'}})
    assert result[0].read_bytes()==assignments[0].read_bytes()
    later.fetcher.get.assert_not_called();later.fetcher.image.assert_not_called()
    assert store.rows('SELECT * FROM posts')==before_posts and store.rows('SELECT * FROM source_photos')==before_photos


def test_preparation_retains_binding_and_publisher_checks_evidence_freshness_and_pixels(store,tmp_path,monkeypatch):
    item,post=seed(store);photos,_=manager(store,tmp_path,monkeypatch)
    assignments=photos.for_post(post,{item['id']:item});post['visual_review']=review(post,assignments,{item['id']:item})
    with store.db:store.db.execute('UPDATE posts SET payload=?',(json.dumps(post),))
    before=deepcopy(post)
    queue_item(store,item,'news',AT,AT+timedelta(minutes=1))
    refreshed=store.posts()[0]
    assert refreshed['source_photo_keys']==before['source_photo_keys'] and valid_review(refreshed)
    assert binding_reason(store,refreshed,{item['id']:item},AT) is None
    assert binding_reason(store,refreshed,{item['id']:item},AT+timedelta(minutes=61))=='visual_review_stale'
    assert binding_reason(store,refreshed,{item['id']:{**item,'revision':2}},AT)=='visual_review_stale'
    changed=deepcopy(refreshed);changed['source_photo_keys']={}
    assert content_key(changed)!=content_key(refreshed) and not valid_review(changed)
    row=store.rows('SELECT * FROM source_photos')[0]
    with store.db:store.db.execute('UPDATE source_photos SET image=?',(cleaned_photo(raw_photo((1000,600))),))
    assert binding_reason(store,refreshed,{item['id']:item},AT)=='visual_review_stale'
    with pytest.raises(ValueError):validate_state(store.path)


def test_each_refresh_is_separate_evidence_and_network_budget_is_bounded(store,tmp_path,monkeypatch):
    item,post=seed(store);photos,fetcher=manager(store,tmp_path,monkeypatch)
    first=photos.for_post(post,{item['id']:item});old_key=post['source_photo_keys']['0']
    with store.db:store.db.execute('UPDATE posts SET payload=?',(json.dumps(post),))
    cache,unused=manager(store,tmp_path/'cached',monkeypatch,AT+timedelta(minutes=45))
    again=cache.for_post(post,{item['id']:item});unused.get.assert_not_called()
    assert again[0].read_bytes()==first[0].read_bytes() and post['source_photo_keys']['0']==old_key
    later,fetcher=manager(store,tmp_path/'new',monkeypatch,AT+timedelta(minutes=46))
    later.for_post(post,{item['id']:item})
    assert post['source_photo_keys']['0']!=old_key
    for index in range(3):
        other={**item,'id':str(index)*24}
        later.image(other)
    assert fetcher.get.call_count==2 and later.stats['deferred']==2


def test_no_generation_demo_or_instagram_media_fetch_in_the_publisher(store,tmp_path,monkeypatch):
    item,post=seed(store);monkeypatch.delenv('ILLUSTRATIONS_ENABLED',raising=False)
    unused=Mock();photos=SourcePhotos(store,AT,tmp_path,[SOURCE],fetcher=unused)
    assert photos.for_post(post,{item['id']:item})=={}
    unused.get.assert_not_called()
    assert not SourcePhotos(store,AT,tmp_path,[SOURCE],demo=True).enabled
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    instagram={**item,'source_id':'instagram-life','url':'https://www.instagram.com/p/example/'}
    assert photos.image(instagram) is None
    unused.get.assert_not_called()


def test_only_explicit_news_topics_can_use_real_photos_and_never_promote_generated_scenes():
    for title,expected in [('Seferihisar’da toplantı','meeting'),('Seferihisar yağmurdan göle döndü','flood'),
                           ('Seferihisar’ın trafik düğümü çözülüyor','traffic')]:
        assert news_subject({**NEWS,'title':title})==expected
    assert news_subject({**NEWS,'title':'Seferihisar için önemli açıklama'}) is None
    assert news_subject({**NEWS,'kind':'event','category':'outage'}) is None


def test_research_and_publisher_exports_keep_the_same_photo_edition_and_source_binding(store,tmp_path,monkeypatch):
    item,post=seed(store);_,fetcher=manager(store,tmp_path,monkeypatch)
    monkeypatch.setattr('seferihisar.source_photos.Fetcher',lambda sources:fetcher)
    _export(store,tmp_path/'research',[SOURCE],AT)
    frozen=store.rows('SELECT * FROM source_photos');draft=store.posts()[0]
    assert draft['source_photo_keys'] and valid_review(draft) and draft['visual_review']['images']
    assert not store.rows('SELECT * FROM illustration_days')
    validate_state(store.path)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','false')
    fetcher.reset_mock()
    _export(store,tmp_path/'publisher',[SOURCE],AT+timedelta(minutes=1))
    assert store.posts()[0]==draft and store.rows('SELECT * FROM source_photos')==frozen
    fetcher.get.assert_not_called();fetcher.image.assert_not_called()
    from seferihisar.visual_gate import deployed
    monkeypatch.setattr('seferihisar.visual_gate.now',lambda:AT+timedelta(minutes=61))
    session=Mock()
    assert deployed(store,draft,'https://public.example/',[],session=session)=='visual_review_stale'
    session.get.assert_not_called()


@pytest.mark.parametrize('failure',['robots','redirect','mime','large'])
def test_image_download_retains_robots_size_mime_and_no_redirect_boundaries(monkeypatch,failure):
    from urllib.robotparser import RobotFileParser
    from seferihisar.collect import Fetcher
    monkeypatch.setattr('seferihisar.collect.safe_url',lambda url,hosts:url)
    session=Mock();fetcher=Fetcher([SOURCE],session)
    robots=RobotFileParser();robots.parse(['User-agent: *','Disallow: /uploads' if failure=='robots' else 'Allow: /'])
    fetcher.robots['news.example']=robots
    response=Mock(is_redirect=failure=='redirect',headers={'Content-Type':'text/html' if failure=='mime' else 'image/jpeg','Location':'http://127.0.0.1/private'})
    response.iter_content.return_value=[b'x'*2_000_001 if failure=='large' else raw_photo()]
    session.get.return_value=response
    with pytest.raises(ValueError):fetcher.image(PHOTO)
    assert session.get.call_count==(0 if failure=='robots' else 1)
    if failure!='robots':response.close.assert_called_once()


@pytest.mark.parametrize('story',[False,True])
def test_source_photo_keeps_top_and_bottom_subjects_instead_of_cutting_faces(tmp_path,story):
    from seferihisar.render import card
    photo=Image.new('RGB',(1100,650),'gray')
    photo.paste('red',(0,0,1100,80));photo.paste('blue',(0,570,1100,650))
    source=tmp_path/'source.jpg';photo.save(source)
    target=tmp_path/'card.jpg'
    card(NEWS['title'],'Toplantıda mahallelerin talepleri görüşüldü.','news',target,
         story=story,illustration=source,source_photo=True,text_review=True)
    top=404 if story else 144;bottom=990 if story else 580
    with Image.open(target) as image:
        red=image.getpixel((540,top+10));blue=image.getpixel((540,bottom-10))
        assert red[0]>200 and red[1]<30 and blue[2]>200 and blue[0]<30


def test_same_photo_from_another_article_is_not_assigned_as_a_new_event(store,tmp_path,monkeypatch):
    item,post=seed(store);photos,fetcher=manager(store,tmp_path,monkeypatch)
    assert photos.for_post(post,{item['id']:item})
    other={**item,'id':'b'*24,'title':'Seferihisar’da başka muhtarlar toplantısı',
           'url':'https://news.example/another-meeting'}
    fetcher.get.return_value=(html(other),other['url'])
    assert photos.image(other) is None
    assert len(store.rows('SELECT * FROM source_photos'))==1 and photos.stats['rejected']==1


@pytest.mark.parametrize('frozen',[False,True])
def test_prune_removes_revoked_draft_pixels_and_preserves_frozen_records(store,tmp_path,monkeypatch,frozen):
    item,post=seed(store);photos,_=manager(store,tmp_path,monkeypatch)
    assert photos.for_post(post,{item['id']:item})
    with store.db:store.db.execute('UPDATE posts SET payload=?,status=?',(json.dumps(post),'published' if frozen else 'prepared'))
    before=store.rows('SELECT * FROM source_photos')
    photos.prune(set())
    assert store.rows('SELECT * FROM source_photos')==(before if frozen else [])


@pytest.mark.parametrize('title',[
    'Seferihisar için sel uyarısı',
    'Seferihisar’da su baskını önlenecek',
    'Seferihisar muhtarlar toplantısı iptal edildi',
    'Seferihisar’da yarın muhtarlar toplantısı yapılacak',
    'Seferihisar’da planlanan çevre yolu hakkında açıklama',
])
def test_warning_cancellation_and_future_plan_never_become_an_occurrence_photo(title):
    assert news_subject({**NEWS,'title':title}) is None
