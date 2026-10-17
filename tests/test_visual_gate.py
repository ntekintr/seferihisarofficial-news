import hashlib
import io
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from seferihisar.domain import digest
from seferihisar.editor import event_type_label, news_body
from seferihisar.illustrations import Illustrator, clean_image, image_key, scene_brief
from seferihisar.instagram import publish_one
from seferihisar.facebook import publish_recent
from seferihisar.render import render_post
from seferihisar.schedule import prepare, queue_item
from seferihisar.story_identity import repeat
from seferihisar.visual_subject import subject
from seferihisar.visual_match import MatchRejected, MatchUnavailable, LABELS, accepted, validate_match
from seferihisar.visual_gate import content_key, deployed, record_assets, review


def jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (512, 512), '#f0c98a').save(buf, 'PNG')
    return clean_image(buf.getvalue())


@pytest.mark.parametrize('kind,category,title', [
    ('news','news','AK Parti Seferihisar İlçe Başkanı, 23 muhtarla bir araya geldi'),
    ('news','transport','Seferihisar Tepecik mahallesi yağmurdan göle döndü'),
    ('news','municipality','Yeni otopark projesi'),
    ('event','outage','Urla’da planlı elektrik kesintisi'),
    ('event','outage','Seferihisar su kesintisi'),
    ('event','event','Konser salonunda buluşma'),
])
def test_unsupported_or_actual_incident_requires_information_card(kind,category,title):
    assert subject(dict(kind=kind,category=category,title=title)) is None


def test_outage_is_not_a_theatre_or_an_event_badge(event):
    item={**event,'category':'outage','title':'Urla elektrik kesintisi'}
    assert 'electrical utility' in scene_brief(item)
    assert 'seats' not in scene_brief(item)
    assert event_type_label('outage',item['title'])=='Elektrik kesintisi'


def test_information_card_does_not_repeat_exact_source_headline_or_its_emoji():
    item={'kind':'news','title':'Seferihisar’da 23 muhtar bir araya geldi',
          'description':'Seferihisar’da 23 muhtar bir araya geldi! 🤝 Toplantıda mahallelerin talepleri görüşüldü.'}
    assert news_body(item)=='Toplantıda mahallelerin talepleri görüşüldü.'
    item['description']='Seferihisar’da 24 muhtar bir araya geldi. Ayrıntılar duyuruldu.'
    assert '24 muhtar' in news_body(item)


def test_visual_similarity_abstains_on_ties_low_score_and_invalid_numbers():
    scores={label:0.1 for label in LABELS}
    scores['theatre']=.32
    assert accepted(scores,'theatre')
    assert not accepted(scores,'yoga')
    scores['empty_hall']=.315
    assert not accepted(scores,'theatre')
    scores['empty_hall']=float('nan')
    assert not accepted(scores,'theatre')


def test_both_actual_wide_crops_must_match_not_only_source_square(monkeypatch):
    values={label:0.1 for label in LABELS};values['theatre']=.32
    bad={**values,'empty_hall':.4}
    seen=[]
    def check(images):
        seen.extend(image.size for image in images)
        return [values,bad,values]
    monkeypatch.setattr('seferihisar.visual_match.scores',check)
    with pytest.raises(MatchRejected):validate_match(jpeg(),'theatre')
    assert seen==[(1080,436),(1080,506),(1080,586)]


@pytest.mark.parametrize('error',[MatchRejected,MatchUnavailable])
def test_cached_mismatch_or_unavailable_vision_keeps_frozen_bytes_but_never_assigns(store,event,at,tmp_path,monkeypatch,error):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setattr('seferihisar.illustrations.ocr_available',lambda:True)
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',lambda data:None)
    monkeypatch.setattr('seferihisar.illustrations.validate_match',Mock(side_effect=error('untrusted diagnostic')))
    store.upsert(event,at.isoformat());item=store.items()[0]
    with store.db:
        store.db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',(image_key(item),item['id'],'ready',jpeg(),1,at.isoformat(),at.isoformat()))
    before=store.rows('SELECT * FROM illustrations')
    generator=Illustrator(store,at,tmp_path,session=Mock())
    assert generator.image(item,True) is None
    assert store.rows('SELECT * FROM illustrations')==before
    assert not store.rows('SELECT * FROM illustration_days')
    generator.session.post.assert_not_called()


def test_new_rejected_scene_is_not_rerolled_or_bound(store,event,at,tmp_path,monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','SYNTHETIC_CREDENTIAL_ONLY')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','a'*32)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available',lambda:True)
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',lambda data:None)
    monkeypatch.setattr('seferihisar.illustrations.validate_match',Mock(side_effect=MatchRejected()))
    store.upsert(event,at.isoformat());item=store.items()[0]
    generator=Illustrator(store,at,tmp_path,session=Mock())
    generator.generate=Mock(return_value=jpeg())
    assert generator.image(item,True) is None
    assert generator.image(item,True) is None
    assert generator.generate.call_count==1
    assert store.rows('SELECT attempts FROM illustration_days')[0]['attempts']==1
    assert store.rows('SELECT status,image FROM illustrations')==[{'status':'failed','image':None}]


def test_compact_information_card_has_no_empty_hero_or_duplicate_category(tmp_path,monkeypatch):
    seen=[];original=ImageDraw.ImageDraw.text
    def track(draw,xy,text,**kwargs):
        seen.append((xy,text));return original(draw,xy,text,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',track)
    post={'id':'a'*24,'kind':'announcement','category':'outage','status':'prepared',
          'slides':[{'title':'Urla’da planlı elektrik kesintisi','body':'17.10.2026 · 09:30 – 17:30\n\nAltıntaş, İçmeler'}]}
    render_post(post,tmp_path)
    title=next(xy for xy,text in seen if text.startswith('URLA'))
    assert title[1]<350
    assert any(text=='ELEKTRİK KESİNTİSİ' for _,text in seen)
    assert not any(text=='ETKİNLİK' for _,text in seen)


class Response:
    def __init__(self,data,kind):self.data,self.status_code,self.headers=data,200,{'Content-Type':kind}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,size):yield self.data


def reviewed_post(store,event,at,tmp_path):
    store.upsert(event,at.isoformat());item=store.items()[0]
    queue_item(store,item,'announcement',at,at)
    post=store.posts()[0]
    post['illustration_keys']={}
    post['visual_review']=review(post,{})
    assets=render_post(post,tmp_path)
    record_assets(post,assets,tmp_path)
    with store.db:store.db.execute('UPDATE posts SET payload=? WHERE id=?',(json.dumps({k:v for k,v in post.items() if k not in ('status','container_id','media_id')}),post['id']))
    visible={k:post[k] for k in ('id','title','caption','category','visual_review')};visible['assets']=assets
    return post,assets,{'demo':False,'posts':[visible]}


@pytest.mark.parametrize('problem',['none','old-manifest','old-bytes','changed-copy','changed-source','wrong-format','oversize','missing-review'])
def test_deployed_gate_binds_actual_bytes_copy_and_format(store,event,at,tmp_path,problem):
    post,assets,manifest=reviewed_post(store,event,at,tmp_path)
    paths=assets['feed']
    changed=deepcopy(post)
    if problem=='old-manifest':manifest['posts'][0]['visual_review']={}
    if problem=='changed-copy':changed['caption']+=' Değişti'
    if problem=='missing-review':changed.pop('visual_review')
    if problem=='wrong-format':paths=assets['story']
    if problem=='changed-source':
        with store.db:store.db.execute('UPDATE items SET revision=revision+1')
    def get(url,**kwargs):
        if url.endswith('data.json'):return Response(json.dumps(manifest).encode(),'application/json')
        body=(tmp_path / url.split('https://example.org/')[1]).read_bytes()
        if problem=='old-bytes':body=b'old jpeg'
        if problem=='oversize':body=b'x'*(4*1024*1024+1)
        return Response(body,'image/jpeg')
    client=SimpleNamespace(get=get)
    result=deployed(store,changed,'https://example.org/',paths,client)
    assert (result is None)==(problem=='none')


def test_calendar_review_binds_each_source_revision_even_without_photos(store,event,at,tmp_path):
    store.upsert(event,at.isoformat());item=store.items()[0]
    post={'id':'a'*24,'kind':'weekly','title':'Takvim','source_urls':[item['url']],
          'slides':[{'title':'Takvim','body':'Tarih bilgileri'}],'category':'event'}
    post['visual_review']=review(post,{}, {item['id']:item})
    assert post['visual_review']['references']=={item['id']:item['revision']}
    assets=render_post(post,tmp_path);record_assets(post,assets,tmp_path)
    with store.db:store.db.execute('UPDATE items SET revision=revision+1')
    assert deployed(store,post,'https://example.org/',assets['feed'],Mock())=='visual_review_stale'


def test_gate_failure_precedes_claim_checkpoint_and_every_meta_call(store,event,at,tmp_path):
    post,assets,manifest=reviewed_post(store,event,at,tmp_path)
    api=Mock();api.enabled.return_value=True
    api.session.get.return_value=Response(b'{"posts":[]}','application/json')
    checkpoint=Mock()
    result=publish_one(store,at,'https://example.org/',{post['id']:assets},adapter=api,checkpoint=checkpoint,require_visual_review=True)
    assert result['status']=='visual_review_stale'
    api.container.assert_not_called();api.call.assert_not_called();checkpoint.assert_not_called()
    assert all(p['status']=='prepared' for p in store.posts())


def test_reviewed_deployed_feed_story_and_facebook_pair_use_the_same_edition(store,event,at,tmp_path):
    post,assets,manifest=reviewed_post(store,event,at,tmp_path)
    def get(url,**kwargs):
        if url.endswith('data.json'):return Response(json.dumps(manifest).encode(),'application/json')
        return Response((tmp_path/url.split('https://example.org/')[1]).read_bytes(),'image/jpeg')
    api=Mock();api.enabled.return_value=True;api.account='synthetic-account'
    api.session.get.side_effect=get
    api.session.head.return_value=SimpleNamespace(status_code=200,headers={'Content-Type':'image/jpeg'})
    api.container.return_value='synthetic-container';api.call.return_value={'id':'synthetic-media'}
    mapping={post['id']:assets}
    assert publish_one(store,at,'https://example.org/',mapping,adapter=api,target_id=post['id'],require_visual_review=True)['status']=='published'
    child_id=digest(post['id']+':story:0')
    assert publish_one(store,at,'https://example.org/',mapping,story=True,adapter=api,target_id=child_id,paired_story=True,require_visual_review=True)['status']=='published'
    api.page='123456';api.check_identity.return_value=True
    api.upload.return_value='synthetic-photo';api.publish.return_value='synthetic-fb-media'
    result=publish_recent(store,at,'https://example.org/',mapping,adapter=api,require_visual_review=True)
    assert result=={'status':'complete','feed':'published','story':'published'}
    assert len(store.rows('SELECT * FROM facebook_deliveries'))==2
    assert api.container.call_count==2 and api.publish.call_count==2
    assert all(post['visual_review']['edition'] in url for call in api.container.call_args_list for url in call.args[0])


def test_same_meeting_across_instagram_web_is_held_without_merging_sources(store,event,at):
    common={k:v for k,v in event.items() if k in ('url','sources','source_id','source_name')}
    titles=['AK Parti Seferihisar İlçe Başkanı Serdar Kısaağa, 23 Mahalle Muhtarıyla Bir Araya Geldi',
            'AK Parti Seferihisar İlçe Başkanı Serdar Kısaağa, 23 mahalle muhtarıyla buluştu']
    for i,title in enumerate(titles):
        item={**common,'kind':'news','category':'news','title':title,'description':'Seferihisar mahallelerinin sorunları görüşüldü.',
              'url':f'https://example.org/{i}','sources':[f'https://example.org/{i}'],'identity':f'https://example.org/{i}',
              'published_at':at.isoformat()}
        store.upsert(item,at.isoformat())
    items=store.items()
    queue_item(store,items[0],'news',at,at)
    old=store.posts()[0];old['published_at']=at.isoformat()
    with store.db:store.db.execute("UPDATE posts SET payload=?,status='published',media_id='synthetic' WHERE id=?",(json.dumps(old),old['id']))
    frozen=store.rows("SELECT * FROM posts WHERE status='published'")
    raw=store.rows('SELECT * FROM items')
    queue_item(store,items[1],'news',at,at)
    pending=next(p for p in store.posts() if p['status']=='prepared')
    assert repeat(store,pending)
    for suffix in (' 24 mahalle',' farklı bir toplantı'):
        candidate=deepcopy(pending);candidate['title']+=suffix
        assert not repeat(store,candidate)
    prepare(store,at)
    assert next(p for p in store.posts() if p['id']==pending['id'])['status']=='blocked_source'
    assert store.rows("SELECT * FROM posts WHERE status='published'")==frozen
    assert store.rows('SELECT * FROM items')==raw
