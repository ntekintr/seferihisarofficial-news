import os
from pathlib import Path
import pytest
from seferihisar.source_photos import news_subject,cleaned_photo
from seferihisar.visual_subject import subject
from seferihisar.visual_match import validate_news_photo,validate_headline_photo,MatchRejected

@pytest.mark.parametrize('title',[
    'Sütçüler’in Endemik Kekiği Altın Değerinde',
    'Sütçüler kekiğinin hasadı başladı',
    'Kekik üretimi ilçeye değer katıyor',
])
def test_explicit_thyme_crop_has_specific_visual(title):
    item={'kind':'news','category':'news','title':title}
    assert news_subject(item)==subject(item)=='thyme_herbs'

@pytest.mark.parametrize('title',[
    'Lavanta hasadı başladı',
    'Kekik restoranında yeni menü',
    'Sütçüler’de yeni yol açıldı',
    'Başkan üreticilerle bir araya geldi',
])
def test_other_plants_venues_and_meetings_never_get_thyme(title):
    item={'kind':'news','category':'news','title':title}
    assert news_subject(item)!='thyme_herbs'
    assert subject(item)!='thyme_herbs'

@pytest.mark.skipif(os.getenv('RUN_VISUAL_NATIVE')!='true',reason='Real source photograph subject model')
def test_actual_source_herbs_match_but_official_visit_does_not():
    folder=Path('tests/fixtures/visual-followup')
    data=cleaned_photo((folder/'thyme-article.jpg').read_bytes())
    with pytest.raises(MatchRejected):
        validate_news_photo(data,'thyme_herbs')
    assert validate_headline_photo(data,'thyme_herbs','Sütçüler’in Endemik Kekiği Altın Değerinde')['subject']=='thyme_herbs'
    with pytest.raises(MatchRejected):
        validate_news_photo(cleaned_photo((folder/'official-visit-exif-zero.jpg').read_bytes()),'thyme_herbs')

@pytest.mark.parametrize('side',['left','right'])
def test_side_banner_requires_title_and_independent_picture(side,monkeypatch):
    import hashlib,io,shutil
    from PIL import Image
    from seferihisar import image_safety,visual_match
    b=io.BytesIO();Image.new('RGB',(1000,600),'green').save(b,'JPEG');data=b.getvalue()
    original=hashlib.sha256(data).hexdigest()
    scan=[{'text':word,'confidence':95,'box':{'left':450 if side=='right' else 20,'top':i*70+20,'width':450,'height':50}}
          for i,word in enumerate('Sütçüler endemik kekiği altın değerinde'.split())]
    monkeypatch.setattr(shutil,'which',lambda *args:'synthetic-ocr')
    monkeypatch.setattr(image_safety,'_scan_words',lambda *args:scan)
    def valid(images):
        return [{key:(.32 if key=='thyme_herbs' else .1) for key in visual_match.LABELS} for image in images]
    monkeypatch.setattr(visual_match,'scores',valid)
    assert validate_headline_photo(data,'thyme_herbs','Sütçüler endemik kekiği altın değerinde')['subject']=='thyme_herbs'
    assert hashlib.sha256(data).hexdigest()==original
    with pytest.raises(MatchRejected):validate_headline_photo(data,'thyme_herbs','Başka bir toplantı haberi')
    monkeypatch.setattr(visual_match,'scores',lambda images:[{key:(.4 if key=='traffic' else .1) for key in visual_match.LABELS} for image in images])
    with pytest.raises(MatchRejected):validate_headline_photo(data,'thyme_herbs','Sütçüler endemik kekiği altın değerinde')
    # A central text overlay is not a bounded side panel.
    for word in scan:word['box'].update(left=300,width=400)
    monkeypatch.setattr(visual_match,'scores',valid)
    with pytest.raises(MatchRejected):validate_headline_photo(data,'thyme_herbs','Sütçüler endemik kekiği altın değerinde')
