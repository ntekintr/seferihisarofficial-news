import json
import io
from datetime import timezone
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from unittest.mock import Mock

from seferihisar.editor import caption, event_activity, event_title, event_type_label, excerpt, hashtags, headline, news_body, news_title, news_type_label
from seferihisar.illustrations import ACTIVITY_SCENE_VERSION, SCENE_VERSION, MODEL, Illustrator, image_key, illustration_prompt, scene_version, topic
from seferihisar.domain import digest
from seferihisar.image_safety import validate_jpeg
from seferihisar.render import card, graphic_title, readable_date_line
from seferihisar.schedule import card_location, queue_item, slide_body


@pytest.mark.parametrize('title,category,activity,label,cue', [
    ('Canan Tutal İle Hatha Yoga','event','yoga','Yoga etkinliği','yoga mat'),
    ('Ayşin Koruk ile Yetişkin Çini Etkinliği','event','tile_art','Çini etkinliği','ceramic tile'),
    ('Ebeveyn & Çocuk Çini Etkinliği','family','tile_art','Çini etkinliği','ceramic tile'),
    ('Urla tasarım atölyesi','culture','workshop','Atölye','craft workshop'),
])
def test_explicit_activity_controls_type_tags_and_generic_scene(event,title,category,activity,label,cue):
    item={**event,'category':category,'title':title,'location':'Urla', 'description':'Kaynak açıklaması'}
    before=deepcopy(item)
    assert event_activity(category,title)==activity
    assert event_type_label(category,title)==label
    assert event_title(item)==title
    assert cue in illustration_prompt(item)
    assert title not in illustration_prompt(item)
    assert scene_version(item)==ACTIVITY_SCENE_VERSION
    assert {'yoga':'#yoga','tile_art':'#cini','workshop':'#atolye'}[activity] in hashtags(item)
    assert all(tag==tag.lower() for tag in hashtags(item))
    assert item==before


@pytest.mark.parametrize('category,title',[('theatre','Yoga adlı oyun'),('concert','Çini salonunda konser'),
    ('event','Konser salonunda buluşma'),('event','Yoga merkezinde buluşma'),('event','Yogacı ile söyleşi')])
def test_activity_is_not_guessed_from_plot_venue_or_word_fragment(event,category,title):
    assert event_activity(category,title) is None
    assert scene_version({**event,'category':category,'title':title})==SCENE_VERSION


@pytest.mark.parametrize('category,title',[('concert','Başbaşa Band Konseri'),('festival','Ürkmez Kültür ve Sanat Festivali')])
def test_explicit_event_type_is_not_repeated_in_title(event,category,title):
    assert event_title({**event,'category':category,'title':title})==title
    assert event_title({**event,'category':'theatre','title':'Hafifletici Sebepler'})=='Hafifletici Sebepler — Tiyatro oyunu'


def test_ticket_caption_avoids_duplicate_link_and_template_description_without_losing_facts(event):
    event.update(title='Canan Tutal İle Hatha Yoga',category='event',location='Bademler Sanat Köyü · Urla',
                 ticket_url=event['url'],description='Etkinlik duyurusu. Canan Tutal İle Hatha Yoga',
                 free=False,price='560',currency='TRY')
    value=caption(event,headline(event,'announcement'))
    assert value.count(event['url'])==1 and 'Bilet:' not in value
    assert 'Etkinlik duyurusu.' not in value
    assert '560 TL' in value and 'TRY' not in value
    assert event['location'] in value and 'Kaynak: '+event['source_name'] in value
    event['ticket_url']='https://example.org/bilet'
    event['description']='Yoga sonrası soru-cevap oturumu yapılacak.'
    value=caption(event,headline(event,'announcement'))
    assert 'Bilet: '+event['ticket_url'] in value and event['description'] in value


def test_bademler_card_uses_verified_venue_and_caption_preserves_address(event):
    event.update(source_id='bubilet-bademler',location='Bademler Sanat Köyü Bademler Caddesi No:8 Bademler Mahallesi Urla İzmir İzmir')
    assert card_location(event)=='Bademler Sanat Köyü'
    assert 'Caddesi' not in slide_body(event)
    assert event['location'] in caption(event,headline(event,'announcement'))
    event['source_id']='other'
    assert card_location(event)==event['location']


def test_excerpts_are_short_marked_and_keep_full_caption_copy():
    text='Seferihisar Belediyesi yeni çalışma programını açıkladı. '*15
    item={'kind':'news','title':'Yeni çalışma programı','description':text,'source_id':'other'}
    value=slide_body(item)
    assert len(value)<=360 and value.endswith('.')
    assert value.split()[-1] in text.split()
    assert len(excerpt(text,1000))>len(value)
    assert excerpt('uzunkelime'*10,12)=='…'


def test_hospital_title_is_shortened_only_for_the_reviewed_source():
    item={'kind':'news','source_id':'seferihisar-hastane',
          'title':'Seferihisar Necat Hepkon Devlet Hastanesi: Çalışan Memnuniyeti ve Sürekli İyileştirme Toplantısı'}
    assert news_title(item)=='Seferihisar Devlet Hastanesi’nde çalışan memnuniyeti toplantısı'
    assert news_title({**item,'source_id':'other'})==item['title']
    item['description']=('Çalışma ortamımızı sürekli iyileştirmek amacıyla aylık çalışan memnuniyeti toplantılarımızı sürdürüyoruz. '
                         'Çalışanlarımızın görüş ve önerilerini değerlendiriyor, karşılaşılan sorunlara çözüm üretiyoruz.')
    before=deepcopy(item)
    assert 'aylık toplantılar düzenleniyor' in news_body(item)
    assert 'hastanemiz' not in news_body(item).lower() and 'sürdürüyoruz' not in news_body(item)
    assert item==before
    item['description']='Aylık toplantı yapılması planlanıyor.'
    assert news_body(item)==item['description']


def test_adult_support_story_uses_relevant_label_and_tags_without_changing_source_item(event):
    item={**event,'kind':'news','category':'family',
          'title':'İzmir’de engelli gençlere bağımsız yaşam ve istihdam desteği'}
    before=deepcopy(item)
    title=headline(item,'news')
    assert title.startswith('Sosyal destek: ')
    assert graphic_title(title,'family')[0]==item['title']
    assert '#sosyaldestek' in hashtags(item) and '#istihdam' in hashtags(item)
    assert '#ailevecocuk' not in hashtags(item)
    assert news_type_label('family','Çocuklar için çini etkinliği')=='Aile & Çocuk'
    assert item==before


def test_same_month_visual_date_range_remains_explicit_without_repeating_month():
    assert readable_date_line('15.10.2026 – 17.10.2026 · Saat açıklanmadı')=='15–17 Ekim 2026 · Saat açıklanmadı'
    assert readable_date_line('31.12.2026 – 01.01.2027')=='31 Aralık 2026 – 1 Ocak 2027'


@pytest.mark.parametrize('story',[False,True])
def test_compact_yoga_details_keep_venue_and_price_visible(tmp_path,monkeypatch,story):
    text=[]
    original=ImageDraw.ImageDraw.text
    def record(draw,xy,value,**kwargs):
        text.append(value)
        return original(draw,xy,value,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',record)
    card('Canan Tutal İle Hatha Yoga','16.10.2026 · 18:00\n\nBademler Sanat Köyü\n\nDüzenleyen: Bubilet\n\nÜcret: 560 TL',
         'event',tmp_path/'card.jpg',story=story,event_details=True)
    assert 'Ücret: 560 TL' in text and 'Bademler Sanat Köyü' in text


@pytest.mark.parametrize('prefix,notice',[('Etkinlik bilgisi güncellendi: ','GÜNCELLENDİ'),
    ('İptal duyurusu: ','İPTAL'),('Bugün yakınınızda: ','BUGÜN'),('2 gün kaldı: ','2 GÜN KALDI')])
@pytest.mark.parametrize('story',[False,True])
def test_state_moves_to_badge_without_hiding_event_name_or_verified_date(tmp_path,monkeypatch,prefix,notice,story):
    title=prefix+'Hafifletici Sebepler — Tiyatro oyunu'
    assert graphic_title(title,'theatre',True)==('Hafifletici Sebepler',notice)
    observed=[]
    original=ImageDraw.ImageDraw.text
    def record(draw,xy,text,**kwargs):
        observed.append((text,draw.textbbox(xy,text,font=kwargs['font'],anchor=kwargs.get('anchor'))))
        return original(draw,xy,text,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',record)
    card(title,'24.10.2026 · 20:00\n\nUrla kültür merkezi','theatre',tmp_path/'card.jpg',story=story,event_details=True)
    text='\n'.join(x[0] for x in observed)
    assert notice in text and 'HAFİFLETİCİ SEBEPLER' in text
    assert '24 Ekim 2026 · 20:00' in text and 'Urla kültür merkezi' in text
    assert 'Kaynak:' not in text and '@seferihisarofficial' in text
    assert prefix.upper() not in text
    for _,(left,top,right,bottom) in observed:
        assert 0<=left<right<=1080
        assert (260 if story else 0)<=top<bottom<=(1600 if story else 1260)


@pytest.mark.parametrize('status',['published','publishing','uncertain'])
def test_new_activity_copy_and_scene_key_do_not_rewrite_claimed_payload(store,event,at,status):
    event.update(title='Canan Tutal İle Hatha Yoga',category='event')
    store.upsert(event,at.isoformat()); item=store.items()[0]
    queue_item(store,item,'announcement',at,at)
    key=store.posts()[0]['id']
    row=store.rows('SELECT payload FROM posts WHERE id=?',(key,))[0]
    payload=json.loads(row['payload']); payload['illustration_keys']={'0':'a'*24}
    with store.db:
        store.db.execute('UPDATE posts SET payload=?,status=? WHERE id=?',(json.dumps(payload),status,key))
    before=store.rows('SELECT * FROM posts WHERE id=?',(key,))[0]
    queue_item(store,item,'announcement',at,at)
    assert store.rows('SELECT * FROM posts WHERE id=?',(key,))[0]==before


def test_activity_refresh_respects_quota_and_keeps_only_published_old_binding(store,event,at,tmp_path,monkeypatch):
    event.update(title='Canan Tutal İle Hatha Yoga',category='event')
    store.upsert(event,at.isoformat()); item=store.items()[0]
    previous=digest(MODEL+':editorial-photo-v5:'+item['id']+':'+str(item['revision'])+':'+topic(item))
    assert previous!=image_key(item)
    buffer=io.BytesIO(); Image.new('RGB',(768,768),'#d8e7eb').save(buffer,format='JPEG')
    with store.db:
        store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                         (previous,item['id'],'ready',buffer.getvalue(),1,at.isoformat(),at.isoformat()))
        store.db.execute('INSERT INTO illustration_days VALUES (?,?)',(at.astimezone(timezone.utc).date().isoformat(),20))
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN','SYNTHETIC_CREDENTIAL_0123456789')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID','a'*32)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available',lambda:True)
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',validate_jpeg)
    client=Mock(); generator=Illustrator(store,at,tmp_path,session=client)
    assert generator.image(item,True) is None
    frozen={'status':'published','item_id':item['id'],'slides':[{}],'illustration_keys':{'0':previous}}
    assert generator.for_post(frozen,{item['id']:item})[0].name==previous+'.jpg'
    client.post.assert_not_called()
    assert store.rows('SELECT attempts FROM illustration_days')[0]['attempts']==20
