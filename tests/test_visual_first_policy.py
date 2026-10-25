"""The user's real examples, safe generated context and image-first delivery."""
import io

import pytest
from PIL import Image

from seferihisar.visual_subject import subject
from seferihisar.visual_topics import news_subjects, SCENES
from seferihisar.visual_policy import image_reason
from seferihisar.illustrations import scene_brief
from seferihisar.event_image_text import check_words
from seferihisar.source_photos import cleaned_photo


@pytest.mark.parametrize('title,category,photo,generated', [
    ('Gençler Cumhuriyet’in izinde yürüdü, kadınlar Çanakkale’yi keşfetti','family','hiking','hiking_gear'),
    ("KPSS Sonrası Çünür Mahallesi'nde Trafik Kilitlendi!",'transport','traffic','traffic'),
    ('Isparta’da korkutan görüntü: Yaya yolu kırık alkol şişeleriyle doldu','news','glass_litter','glass_litter'),
    ('Isparta32Spor Elazığspor’a 4-3 mağlup oldu','news','football','football_equipment'),
    ('Muhtarlarla bir araya geldi','news','meeting','meeting_room'),
    ('Yarın sel riski bekleniyor','weather',None,'rain_puddle'),
])
def test_source_and_generated_context_are_separate(title,category,photo,generated):
    item={'kind':'news','category':category,'title':title,'description':'Konser salonu ve spor tesisi yanından geçti.'}
    assert news_subjects(item)==(photo,generated)
    assert subject(item)==generated
    if generated == 'traffic':
        assert 'ordinary roadway' in scene_brief(item)
    else:
        assert scene_brief(item)==SCENES[generated]
    assert 'Çünür' not in scene_brief(item) and 'Çanakkale' not in scene_brief(item)


def test_unidentified_news_never_gets_random_scenery():
    item={'kind':'news','category':'news','title':'Önemli bir gelişme duyuruldu','description':'Tiyatro salonu yakınında.'}
    assert subject(item) is None


def test_new_cards_wait_for_actual_cover_binding_and_reviewed_pixels():
    post={'status':'prepared','visual_review':{'images':{}}}
    assert image_reason(post)=='awaiting_content_visual'
    assert image_reason({**post,'illustration_keys':{'0':'a'*24}})=='awaiting_content_visual'
    assert image_reason({**post,'visual_review':{'images':{'0':'b'*64}}})=='awaiting_content_visual'
    for field in ('source_photo_keys','illustration_keys'):
        ready={**post,field:{'0':'a'*24},'visual_review':{'images':{'0':'b'*64}}}
        assert image_reason(ready) is None
    for status in ('published','publishing','uncertain'):
        assert image_reason({**post,'status':status}) is None


def test_standard_portrait_and_square_photographs_keep_their_original_frame():
    for size in ((480,640),(640,1200),(800,800)):
        raw=io.BytesIO();Image.new('RGB',size,'#447799').save(raw,'JPEG')
        with Image.open(io.BytesIO(cleaned_photo(raw.getvalue()))) as result:
            assert abs(result.width/result.height-size[0]/size[1])<.005


def words(text):
    return [{'text':word,'confidence':95} for word in text.split()]


def test_exact_session_artwork_can_omit_date_but_cannot_contradict_it():
    item={'title':'Şahane Pazar Sahnede','start':'2026-11-07T20:30:00+03:00',
          'end':'2026-11-07T22:00:00+03:00','time_known':True}
    assert check_words([words('Şahane Pazar Sahnede'),[]],item,poster=True) is True
    for bad in ('Şahane Pazar Sahnede 07.11.2025','Şahane Pazar Sahnede 08.11.2026',
                'Şahane Pazar Sahnede 19:30','Şahane Pazar Sahnede 8 Kasım','Tamamen başka gösteri'):
        with pytest.raises(ValueError):check_words([words(bad)],item,poster=True)


def test_editorial_banner_uses_matching_headline_and_keeps_the_original_file(monkeypatch):
    import hashlib,shutil
    from seferihisar import image_safety,visual_match
    raw=io.BytesIO();Image.new('RGB',(768,432),'#337744').save(raw,'JPEG');data=raw.getvalue()
    before=hashlib.sha256(data).hexdigest()
    scan=[{'text':word,'confidence':95,'box':{'left':30,'top':240,'width':110,'height':30}}
          for word in 'KPSS sonrası trafik kilitlendi'.split()]
    monkeypatch.setattr(shutil,'which',lambda name:'synthetic-ocr')
    monkeypatch.setattr(image_safety,'_scan_words',lambda *args:scan)
    def score(images):
        assert images[0].size==(224,224)
        values={key:.1 for key in visual_match.LABELS};values.update(traffic=.30,parking=.295)
        return [values]
    monkeypatch.setattr(visual_match,'scores',score)
    assert visual_match.validate_headline_photo(data,'traffic','KPSS sonrası trafik kilitlendi')['subject']=='traffic'
    assert hashlib.sha256(data).hexdigest()==before
    with pytest.raises(ValueError):visual_match.validate_headline_photo(data,'traffic','Tamamen farklı bir toplantı')
    def wrong(images):
        values=score(images);values[0]['parking']=.31;return values
    monkeypatch.setattr(visual_match,'scores',wrong)
    with pytest.raises(ValueError):visual_match.validate_headline_photo(data,'traffic','KPSS sonrası trafik kilitlendi')


def test_future_harvest_does_not_claim_an_actual_harvest_photo():
    item={'kind':'news','category':'food','title':'Mandalina hasadı başlayacak'}
    assert news_subjects(item)==(None,'market')
    assert 'basket' in scene_brief(item) and 'No people harvesting' in scene_brief(item)
