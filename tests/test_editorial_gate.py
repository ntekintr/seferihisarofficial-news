"""Actual screenshot regression and destination-level fail-closed checks."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import ImageDraw

from seferihisar.domain import parse_date
from seferihisar.editor import headline, news_body
from seferihisar.facebook import publish_recent
from seferihisar.instagram import publish_one
from seferihisar.pipeline import _export
from seferihisar.quality import news_editorial_reason
from seferihisar.render import card, render_post
from seferihisar.schedule import prepare, queue_item
from seferihisar.text_quality import TextRenderError, plain_display, source_body
from seferihisar.visual_gate import deployed, review


@pytest.fixture
def children():
    return json.loads(Path('tests/fixtures/news-children-source.json').read_text(encoding='utf-8'))


def test_actual_children_post_is_held_not_rewritten_with_invented_facts(children):
    before=deepcopy(children)
    assert news_editorial_reason(children)=='editorial_headline_required'
    body=news_body(children)
    assert 'kedi evleri yapmışlar' in body and 'annelerinin de yardımıyla' in body
    assert all(word not in body for word in ('🙏','SEHAYDER','SEFERİHİSAR','İyi ki','kucaklıyoruz','Böyle çocuklar'))
    assert 'Seferihisar’da' not in body and '17 Ekim' not in body
    assert children==before


def test_better_headline_alone_cannot_turn_source_signature_into_event_location(children):
    children['title']='Çocuklar kediler için yuva yaptı'
    children['description']=children['description'].split('\n',1)[1]
    assert news_editorial_reason(children)=='editorial_context_required'
    children['description']='Seferihisar’da çocuklar annelerinin yardımıyla kediler için kedi evleri yaptı.'
    assert news_editorial_reason(children) is None


@pytest.mark.parametrize('title',['Müjde!','DİKKAT⚠ DİKKAT⚠','Böyle dostluklar hep olsun 🙏','İyi ki varsınız', 'X'*180])
def test_other_uninformative_or_truncated_social_headlines_are_held(children,title):
    children['title']=title
    assert news_editorial_reason(children)=='editorial_headline_required'


@pytest.mark.parametrize('destination',['feed','story','facebook'])
def test_actual_legacy_draft_cannot_reach_any_social_destination(store,children,destination):
    at=parse_date('2026-10-17T12:30:00+03:00')
    store.upsert(children,at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at)
    post=store.posts()[0]
    assets={post['id']:{fmt:[f"media/{post['id']}/{fmt}-1.jpg"] for fmt in ('feed','story')}}
    api=Mock();api.enabled.return_value=api.check_identity.return_value=True
    if destination=='facebook':
        post['published_at']=at.isoformat()
        with store.db:
            store.db.execute("UPDATE posts SET status='published',payload=?,media_id='synthetic'",(json.dumps(post),))
        before=store.rows('SELECT * FROM posts')
        assert publish_recent(store,at,'https://example.org/',assets,api)['status']=='blocked_source'
        assert store.rows('SELECT * FROM posts')==before
    else:
        assert publish_one(store,at,'https://example.org/',assets,story=destination=='story',adapter=api)['status']=='empty'
        assert store.rows('SELECT reason FROM withheld')==[{'reason':'editorial_headline_required'}]
    api.container.assert_not_called();api.call.assert_not_called()
    api.upload.assert_not_called();api.publish.assert_not_called()
    assert not store.rows('SELECT * FROM facebook_deliveries')


def valid_news(source,at):
    url=source['url'].rstrip('/')+'/synthetic-park'
    return {'kind':'news','category':'news','title':'Seferihisar’da yeni park açıldı',
            'description':'Seferihisar’da yeni parkın açıldığı belediye tarafından duyuruldu. Park vatandaşların kullanımına açıldı.',
            'source_id':source['id'],'source_name':source['name'],'url':url,'sources':[url],'published_at':at.isoformat()}


def test_old_bad_copy_cannot_be_approved_just_by_hashing_its_jpeg(store,source,at):
    store.upsert(valid_news(source,at),at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at);post=store.posts()[0]
    post['slides'][0]['body']='İyi ki varsınız sevgili çocuklar 🙏🙏'
    post['visual_review']=review(post,{})
    client=Mock()
    assert deployed(store,post,'https://example.org/',['media/x/feed-1.jpg'],client)=='editorial_copy_stale'
    client.get.assert_not_called()


def test_export_cannot_approve_stale_copy_even_when_source_is_valid(store,source,at,tmp_path):
    store.upsert(valid_news(source,at),at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at);post=store.posts()[0]
    post['caption']='İyi ki varsınız sevgili çocuklar 🙏'
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?',(json.dumps(post),post['id']))
    _export(store,tmp_path/'public',[source],at)
    current=store.posts()[0]
    assert current['status']=='blocked_source' and not current.get('visual_review')
    assert store.rows('SELECT reason FROM withheld')==[{'reason':'editorial_copy_stale'}]


def test_cleanup_keeps_unrecognized_commitments_numbers_and_quoted_words():
    item={'title':'Yeni destek programı','source_name':'Yerel kurum','description':
          'Destekleriniz için teşekkürler. 21 Ekim’de 23 aileye destek ulaştırılacak.\n'
          'Destekleriniz için teşekkürler ve 24 Ekim’de 7 aileye daha yardım edeceğiz.\n'
          'Başkan, “İyi ki varsınız” dedi.'}
    value=source_body(item)
    assert not value.startswith('Destekleriniz için teşekkürler.')
    assert '21 Ekim’de 23 aileye' in value and '24 Ekim’de 7 aileye' in value
    assert 'yardım edeceğiz' in value and '“İyi ki varsınız”' in value


def test_new_card_emoji_cleanup_preserves_actual_numbers_names_and_currency(tmp_path,monkeypatch):
    value='📅 17.10.2026 ⚡ 09:30–17:30 20° 400 ₺ Çığlı, Özdere 5️⃣'
    assert plain_display(value)=='17.10.2026 09:30–17:30 20° 400 ₺ Çığlı, Özdere 5'
    assert plain_display('Çocuklar🙏kediler')=='Çocuklar kediler'
    observed=[];original=ImageDraw.ImageDraw.text
    def capture(draw,xy,text,**kwargs):
        observed.append(text);return original(draw,xy,text,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    card('Seferihisar’da çocuklardan kedilere yuva 🙏🙏',value,'family',tmp_path/'safe.jpg',compact=True,text_review=True)
    text=' '.join(observed)
    assert '🙏' not in text and '📅' not in text and '□' not in text
    for fact in ('17.10.2026','09:30–17:30','400','Çığlı','Özdere'):
        assert fact in text


@pytest.mark.parametrize('problem',['glyph','title_overflow','empty'])
def test_new_cards_with_unrenderable_factual_characters_or_cut_heading_are_held(tmp_path,problem):
    title={'glyph':'Seferihisar’da yeni park \U0010ffff','title_overflow':'Seferihisar kültür ve sanat '*100,'empty':'🙏🙏'}[problem]
    with pytest.raises(TextRenderError):
        card(title,'Park vatandaşların kullanımına açıldı.','news',tmp_path/'bad.jpg',compact=True,text_review=True)
    assert not (tmp_path/'bad.jpg').exists()


def test_bad_font_card_does_not_abort_other_sources_or_get_ready_assets(store,source,at,tmp_path):
    good=valid_news(source,at)
    bad={**good,'url':good['url']+'-bad','sources':[good['url']+'-bad'],
         'title':'Seferihisar’da park çalışması tamamlandı',
         'description':'Seferihisar’da \U0010ffff parkın açıldığı belediye tarafından duyuruldu. Park vatandaşların kullanımına açıldı.'}
    for item in (good,bad):store.upsert(item,at.isoformat())
    prepare(store,at)
    _export(store,tmp_path/'public',[source],at)
    snapshot=json.loads((tmp_path/'public/data.json').read_text(encoding='utf-8'))
    posts={p['title']:p for p in snapshot['posts']}
    assert posts[headline(good,'news')]['assets']['feed']
    assert posts[headline(bad,'news')]['status']=='blocked_source'
    assert posts[headline(bad,'news')]['assets']=={}
    assert store.rows("SELECT reason FROM withheld WHERE reason='unrenderable_card_text'")


@pytest.mark.parametrize('version',['content-visual-v1','content-visual-v2'])
def test_claimed_old_layouts_are_frozen_even_with_unsupported_emoji(tmp_path,monkeypatch,version):
    calls=[];monkeypatch.setattr('seferihisar.render.card',lambda *a,**kw:calls.append(kw))
    p={'id':'a'*24,'kind':'news','status':'published','category':'family',
       'visual_review':{'version':version,'edition':'b'*24},
       'slides':[{'title':'Böyle çocuklar hep olsun 🙏🙏','body':'Eski dondurulmuş metin.'}]}
    render_post(p,tmp_path)
    assert all(not call['text_review'] for call in calls)
