"""The caption hint belongs below first-card content, never in an extra frame."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import ImageDraw

from seferihisar import render
from seferihisar.card_layout import VERSION,CAPTION_NOTE,prepare
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.security import validate_state
from seferihisar.visual_gate import content_key,review,valid_review


def post(kind='announcement'):
    return {'id':'a'*24,'kind':kind,'category':'theatre','status':'prepared',
            'title':'Urla’da tiyatro akşamı',
            'slides':[{'title':'Urla’da tiyatro akşamı',
                       'body':'24.10.2026 · 20:00\n\nUrla Kültür Merkezi\n\nÜcret: 250 TL'}]}


@pytest.mark.parametrize('kind',['news','announcement','reminder_3d','reminder_day','update','cancellation','weekly','monthly'])
def test_all_new_content_has_one_hint_on_first_card_without_extra_asset(tmp_path,monkeypatch,kind):
    p=post(kind);calls=[]
    if kind in ('weekly','monthly'):
        p['slides'].insert(0,{'title':'Etkinlik takvimi','body':'Bu haftanın etkinlikleri'})
    monkeypatch.setattr(render,'card',lambda *a,**kw:calls.append((a,kw)))
    assets=render.render_post(p,tmp_path)
    assert len(assets['feed'])==len(assets['story'])==len(p['slides'])
    for offset in (0,len(p['slides'])):
        group=calls[offset:offset+len(p['slides'])]
        assert [kw['caption_note'] for _,kw in group]==[True]+[False]*(len(p['slides'])-1)
        assert not any(args[0]=='Ayrıntılar açıklamada' for args,_ in group)


@pytest.mark.parametrize('state',['published','publishing','uncertain'])
def test_old_claims_keep_legacy_frame_indexes_and_policy(state,tmp_path,monkeypatch):
    p=post();p['status']=state;p['visual_review']={'version':'content-visual-v3','edition':'b'*24}
    original=deepcopy(p);prepare(p);assert p==original
    calls=[];monkeypatch.setattr(render,'card',lambda *a,**kw:calls.append((a,kw)))
    assets=render.render_post(p,tmp_path)
    assert len(assets['feed'])==len(assets['story'])==2
    assert all(not kw['caption_note'] for _,kw in calls)
    assert [a[0] for a,_ in calls].count('Ayrıntılar açıklamada')==2


def test_new_claim_keeps_its_inline_policy_after_publication(tmp_path,monkeypatch):
    p=post();prepare(p);p['status']='published'
    calls=[];monkeypatch.setattr(render,'card',lambda *a,**kw:calls.append(kw))
    assets=render.render_post(p,tmp_path)
    assert len(assets['feed'])==len(assets['story'])==1
    assert all(c['caption_note'] for c in calls)


@pytest.mark.parametrize('story',[False,True])
@pytest.mark.parametrize('scene',['news','event','photo_event','outage','long_news'])
def test_hint_follows_visible_content_and_stays_above_brand_footer(tmp_path,monkeypatch,story,scene):
    captured=[];original=ImageDraw.ImageDraw.text
    def track(draw,xy,text,**kw):
        if text:captured.append((text,draw.textbbox(xy,text,font=kw['font'],anchor=kw.get('anchor'))))
        return original(draw,xy,text,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',track)
    title='Seferihisar’da kültür ve sanat buluşması'
    body='Etkinliğe ilişkin güncel bilgiler ve program duyuruldu.'
    kwargs={'compact':True,'text_review':True,'caption_note':True,'story':story}
    category='news'
    if scene in ('event','photo_event','outage'):
        title='Canan Tutal ile Hatha Yoga';category='event'
        body='24.10.2026 · 20:00\n\nUrla Kültür Merkezi\n\nDüzenleyen: Kültür Topluluğu\n\nÜcret: 250 TL'
        kwargs.update(event_details=True,story_details=True)
        if scene=='outage':
            category='outage';title='Urla’da planlı elektrik kesintisi'
            body='24.10.2026 · 09:00 – 17:00\n\nEtkilenen bölge: Urla\n\nMahalle ayrıntıları için açıklamaya bakın.'
        if scene=='photo_event':kwargs['illustration']=Path('tests/fixtures/visual-match/yoga-accepted.jpg')
    elif scene=='long_news':body='Seferihisar’da kültür etkinlikleriyle ilgili güncel program açıklandı. '*50
    render.card(title,body,category,tmp_path/'card.jpg',**kwargs)
    hints=[box for text,box in captured if text==CAPTION_NOTE]
    assert len(hints)==1
    box=hints[0];hint_index=next(i for i,(t,_) in enumerate(captured) if t==CAPTION_NOTE)
    prior_bottom=max(b[3] for _,b in captured[:hint_index])
    assert box[1]>prior_bottom and box[1]-prior_bottom<65
    assert box[3]<((1600 if story else 1260)-70-8)
    for _,(left,top,right,bottom) in captured:
        assert 0<=left<right<=1080 and (260 if story else 0)<=top<bottom<=(1600 if story else 1260)
    if scene in ('event','photo_event'):
        visible=' '.join(text for text,_ in captured)
        for value in ('24 Ekim 2026','20:00','Urla Kültür Merkezi','250 TL'):
            assert value in visible


def test_layout_marker_changes_edition_but_not_legacy_hashes():
    p=post();old=deepcopy(p);old_key=content_key(p);old_review=review(p,{})
    p['visual_review']=old_review;prepare(p)
    assert p['card_layout']==VERSION and content_key(p)!=old_key and not valid_review(p)
    p['visual_review']=review(p,{})
    assert valid_review(p) and p['visual_review']['edition']!=old_review['edition']
    assert content_key(old)==old_key


def test_pipeline_binds_new_policy_and_preserves_it_in_no_generation_export(store,event,source,at,tmp_path,monkeypatch):
    store.upsert(event,at.isoformat());item=store.items()[0]
    queue_item(store,item,'announcement',at,at)
    _export(store,tmp_path/'first',[source],at)
    p=store.posts()[0]
    assert p['card_layout']==VERSION and valid_review(p)
    first=json.loads((tmp_path/'first/data.json').read_text(encoding='utf8'))['posts'][0]
    assert len(first['assets']['feed'])==len(first['assets']['story'])==1
    queue_item(store,item,'announcement',at,at)
    assert store.posts()[0]['card_layout']==VERSION
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','false')
    _export(store,tmp_path/'publisher',[source],at)
    assert store.posts()[0]==p
    validate_state(store.path)


def test_unknown_layout_is_rejected_at_standard_library_state_boundary(store,event,at):
    store.upsert(event,at.isoformat());item=store.items()[0];queue_item(store,item,'announcement',at,at)
    p=store.posts()[0];p['card_layout']='unsafe-layout'
    with store.db:store.db.execute('UPDATE posts SET payload=? WHERE id=?',(json.dumps(p),p['id']))
    with pytest.raises(ValueError,match='card layout'):validate_state(store.path)
