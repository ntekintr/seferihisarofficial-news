from pathlib import Path

from PIL import ImageDraw

from seferihisar.render import render_post
from seferihisar.visual_gate import review


def concert():
    title='İlker ÖZDEMİR Konseri - Polio ve Kız Çocukları Yararına'
    return {'id':'c'*24,'kind':'announcement','category':'concert','status':'prepared',
            'title':title,'slides':[{'title':title,'body':
                '24.10.2026 · 20:30\n\nGüzelbahçe Kültür Merkezi\n\nDüzenleyen: Urla Rotary Kulübü\n\nÜcret: 500.00 TL'}]}


def test_live_long_concert_story_retains_date_venue_price_and_organizer(tmp_path,monkeypatch):
    captured=[];original=ImageDraw.ImageDraw.text
    def track(draw,xy,text,**kwargs):
        if text:captured.append((text,draw.textbbox(xy,text,font=kwargs['font'],anchor=kwargs.get('anchor'))))
        return original(draw,xy,text,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',track)
    post=concert();photo={0:Path('tests/fixtures/visual-match/concert-accepted.jpg')}
    post['visual_review']=review(post,photo)
    render_post(post,tmp_path,photo)
    # Separate feed and story text by the safe top inset; a fee visible only
    # in the feed must not satisfy the story regression.
    # The actual story begins with the second brand header.
    headers=[i for i,(text,_) in enumerate(captured) if text=='SEFERİHİSAR']
    assert len(headers)==4  # Measured, then drawn, once per format; no caption-only appendix.
    story=captured[headers[3]:]
    value=' '.join(text for text,_ in story)
    for expected in ('24 Ekim 2026','20:30','Güzelbahçe Kültür Merkezi','Ücret: 500.00 TL','Urla Rotary Kulübü'):
        assert expected in value
    for _,(left,top,right,bottom) in story:
        assert 0<=left<right<=1080 and 260<=top<bottom<=1600


def test_claimed_v1_photo_and_info_layout_are_not_reframed(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr('seferihisar.render.card',lambda *a,**kw:calls.append(kw))
    post=concert();post['status']='published'
    post['visual_review']={'version':'content-visual-v1','edition':'a'*24}
    render_post(post,tmp_path,{0:Path('old-frozen.jpg')})
    assert all(not call['story_details'] for call in calls)
