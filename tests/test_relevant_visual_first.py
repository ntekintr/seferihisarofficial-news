"""Prefer source-bound imagery without weakening dates, subjects, limits or frozen cards."""
import io
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.collect import structured
from seferihisar.domain import parse_date
from seferihisar.event_image_text import check_words
from seferihisar.illustrations import Illustrator
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.security import validate_state
from seferihisar.source_photo_data import EVENT_VERSION,validate_record
from seferihisar.source_photos import SourcePhotos,binding_reason,candidate,cleaned_photo,photo_subject
from seferihisar.visual_gate import review,valid_review
from seferihisar.visual_policy import summary
from test_source_photos import SOURCE,raw_photo

AT=parse_date('2026-10-10T10:00:00+03:00')
URL='https://news.example/seferihisar-konser'
PHOTO='https://news.example/uploads/concert.jpg'


def event_html(*,start='2026-10-13T20:00:00+03:00',location='Seferihisar Salonu'):
    data={'@type':'Event','name':'Seferihisar Akustik Konser',
          'description':'Seferihisar’da akustik konser için güncel etkinlik duyurusu.',
          'startDate':start,'endDate':'2026-10-13T22:00:00+03:00',
          'location':{'name':location},'eventStatus':'https://schema.org/EventScheduled'}
    return (f'<link rel="canonical" href="{URL}"><meta property="og:image" content="{PHOTO}">'
            '<script type="application/ld+json">'+json.dumps(data)+'</script>'
            f'<article><h1>{data["name"]}</h1><p>{data["description"]}</p>'
            f'<img src="{PHOTO}"></article>')


def seed(store):
    item,=structured(event_html(),URL,SOURCE)
    store.upsert(item,AT.isoformat());item=store.items()[0]
    queue_item(store,item,'announcement',AT,AT)
    return item,store.posts()[0]


def manager(store,tmp_path,monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.setattr('seferihisar.event_image_text.validate',lambda *a,**k:None)
    monkeypatch.setattr('seferihisar.visual_match.validate_event_photo',lambda *a:None)
    fetcher=Mock();fetcher.get.return_value=(event_html(),URL);fetcher.image.return_value=(raw_photo(),PHOTO)
    return SourcePhotos(store,AT,tmp_path,[SOURCE],fetcher=fetcher),fetcher


def test_exact_event_source_image_binds_start_end_revision_and_durable_pixels(store,tmp_path,monkeypatch):
    item,post=seed(store);photos,_=manager(store,tmp_path,monkeypatch)
    assignments=photos.for_post(post,{item['id']:item});assert assignments
    row=store.rows('SELECT * FROM source_photos')[0];e=validate_record(**dict(
        photo_id=row['id'],item_id=row['item_id'],revision=row['revision'],payload=row['payload'],image=row['image']))
    assert e['version']==EVENT_VERSION and e['start']==item['start'] and e['end']==item['end']
    assert 'published_at' not in e
    post['visual_review']=review(post,assignments,{item['id']:item})
    assert binding_reason(store,post,{item['id']:item},AT) is None
    assert binding_reason(store,post,{item['id']:{**item,'end':'2026-10-14T22:00:00+03:00'}},AT)=='visual_review_stale'
    validate_state(store.path)


@pytest.mark.parametrize('change',['date','venue','title','image_host'])
def test_source_poster_cannot_belong_to_another_event_date_venue_title_or_host(store,change):
    item,_=seed(store);body=event_html()
    if change=='date':body=event_html(start='2026-10-14T20:00:00+03:00')
    if change=='venue':body=event_html(location='Urla Başka Salon')
    if change=='title':body=body.replace(item['title'],'Seferihisar Başka Konser')
    if change=='image_host':body=body.replace(PHOTO,'https://unreviewed.example/a.jpg')
    with pytest.raises(ValueError):candidate(body,URL,item,SOURCE)


def words(text):
    return [{'text':w,'confidence':95} for w in text.split()]


@pytest.mark.parametrize('text',[
    'Seferihisar Akustik Konser 13.10.2026 20:00',
    'Seferihisar Akustik Konser 13 Ekim 2026 20:00',
])
def test_source_poster_needs_readable_title_full_date_and_matching_time(store,text):
    item,_=seed(store);check_words([words(text),words(text)],item,poster=True)


@pytest.mark.parametrize('text',[
    'Seferihisar Akustik Konser 13.10.2025 20:00',
    'Seferihisar Akustik Konser 12.10.2026 20:00',
    'Seferihisar Akustik Konser 13.10.2026 19:00',
    'Başka Festival 13.10.2026 20:00',
    'Seferihisar Akustik Konser 13 Ekim 20:00',
    'Seferihisar Akustik Konser 13.10.2026',
    '',
])
def test_wrong_or_unreadable_poster_facts_are_rejected_in_either_scan(store,text):
    item,_=seed(store)
    with pytest.raises(ValueError):check_words([words('Seferihisar Akustik Konser 13.10.2026 20:00'),words(text)],item,poster=True)


def test_plain_source_photo_can_have_no_lettering_but_cannot_show_a_conflicting_date(store):
    item,_=seed(store);check_words([[],[]],item)
    with pytest.raises(ValueError):check_words([words('12.10.2026'),[]],item)
    with pytest.raises(ValueError):check_words([words('Başka Festival 13.10.2026 20:00')]*2,item)


def test_portrait_is_only_allowed_for_event_source_path_and_never_cropped(tmp_path):
    stream=io.BytesIO();Image.new('RGB',(640,900),'#aa7788').save(stream,'JPEG')
    with pytest.raises(ValueError):cleaned_photo(stream.getvalue())
    data=cleaned_photo(stream.getvalue(),poster=True)
    with Image.open(io.BytesIO(data)) as im:assert im.width<im.height


@pytest.mark.parametrize('reason',['ocr','subject'])
def test_rejected_source_event_image_does_not_silently_replace_checks(store,tmp_path,monkeypatch,reason):
    from seferihisar.visual_match import MatchRejected
    item,post=seed(store);photos,_=manager(store,tmp_path,monkeypatch)
    name='seferihisar.event_image_text.validate' if reason=='ocr' else 'seferihisar.visual_match.validate_event_photo'
    monkeypatch.setattr(name,Mock(side_effect=MatchRejected('Mismatch')))
    assert photos.for_post(post,{item['id']:item})=={}
    assert not store.rows('SELECT * FROM source_photos')


def test_source_image_prevents_a_generation_request_for_the_same_slide(store,tmp_path,monkeypatch):
    item,post=seed(store);monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    generator=Illustrator(store,AT,tmp_path);generator.image=Mock()
    assert generator.for_post(post,{item['id']:item},skip_indices={0})=={}
    generator.image.assert_not_called()


def test_missing_ocr_uses_fallback_without_storing_unchecked_source_pixels(store,tmp_path,monkeypatch):
    from seferihisar.image_safety import IllustrationCheckUnavailable
    item,post=seed(store);photos,_=manager(store,tmp_path,monkeypatch)
    monkeypatch.setattr('seferihisar.event_image_text.validate',Mock(side_effect=IllustrationCheckUnavailable()))
    assert photos.for_post(post,{item['id']:item})=={} and photos.stats['unavailable']==1


def test_native_poster_ocr_reads_title_date_and_time_before_acceptance(store):
    from PIL import ImageDraw
    from seferihisar.image_safety import ocr_available
    from seferihisar.event_image_text import validate
    from seferihisar.render import font
    if not ocr_available():pytest.skip('Native OCR/language runtime unavailable')
    item,_=seed(store)
    image=Image.new('RGB',(640,900),'white');draw=ImageDraw.Draw(image)
    for y,text in [(100,'Seferihisar'),(210,'Akustik Konser'),(400,'13 Ekim 2026'),(510,'20:00')]:
        draw.text((40,y),text,font=font(58,True),fill='black')
    output=io.BytesIO();image.save(output,'JPEG')
    validate(cleaned_photo(output.getvalue(),poster=True),item,poster=True)


def test_pipeline_attempts_nearest_editorial_content_before_old_distant_queue(store,tmp_path,monkeypatch):
    old,_=seed(store)
    other={**old,'url':'https://news.example/tonight','identity':'https://news.example/tonight',
           'title':'Seferihisar Bu Akşam Konseri','start':'2026-10-10T20:00:00+03:00','end':'2026-10-10T22:00:00+03:00'}
    store.upsert(other,AT.isoformat());near=next(i for i in store.items() if i['url']==other['url'])
    queue_item(store,near,'announcement',AT+timedelta(hours=1),AT)
    seen=[]
    monkeypatch.setattr(SourcePhotos,'for_post',lambda self,p,items:seen.append(p['item_id']) or {})
    _export(store,tmp_path/'public',[SOURCE],AT)
    assert seen[0]==near['id']


def test_public_policy_does_not_count_an_unverified_binding_or_later_calendar_picture(store):
    _,post=seed(store)
    assert summary(store)['pending_covers']=={'source_photo':0,'topic_visual':0,'information_card':1}
    assert summary(store)['unrelated_filler_allowed'] is False


def test_cancelled_outage_or_unclassified_event_has_no_source_scene():
    for item in [{'kind':'event','category':'outage','status':'scheduled'},
                 {'kind':'event','category':'concert','status':'cancelled'},
                 {'kind':'event','category':'event','status':'scheduled'}]:
        assert photo_subject(item) is None
