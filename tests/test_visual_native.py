"""Real CPU-model regression, independent of mock-based pipeline tests."""
import io
import json
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from seferihisar.editorial_stock import DIRECTORY
from seferihisar.visual_match import MatchRejected, _validate_occasion, validate_match,validate_news_photo,validate_event_photo

pytestmark=pytest.mark.skipif(os.getenv('RUN_VISUAL_NATIVE')!='true',reason='Explicit pinned CPU visual model job')
ROOT=Path('tests/fixtures/visual-match')
STOCK=json.loads((DIRECTORY/'manifest.json').read_text())['scenes']


@pytest.mark.parametrize('file,expected',[
    ('traffic-meeting','theatre'),('hall-outage','theatre'),('dry-road-flood','festival'),
    ('yoga','yoga'),('theatre','theatre'),('tile-art','tile_art'),
    ('tile_art-accepted','tile_art'),
])
def test_observed_unrelated_scenes_are_rejected(file,expected):
    with pytest.raises(MatchRejected):validate_match((ROOT/(file+'.jpg')).read_bytes(),expected)


@pytest.mark.parametrize('expected',['festival','concert','yoga'])
def test_reviewed_current_matching_scenes_pass_both_crops(expected):
    proof=validate_match((ROOT/(expected+'-accepted.jpg')).read_bytes(),expected)
    assert proof['subject']==expected


def test_article_bound_meeting_source_passes_all_full_frame_news_formats():
    proof=validate_news_photo((ROOT/'news-meeting-source.jpg').read_bytes(),'meeting')
    assert proof['subject']=='meeting'


@pytest.mark.parametrize('file,expected',[
    ('traffic-meeting','meeting'),('dry-road-flood','flood'),('hall-outage','meeting'),
])
def test_observed_unrelated_source_news_images_are_rejected(file,expected):
    with pytest.raises(MatchRejected):validate_news_photo((ROOT/(file+'.jpg')).read_bytes(),expected)


@pytest.mark.parametrize('expected',['festival','concert','yoga'])
def test_source_event_images_keep_subject_in_all_full_frame_formats(expected):
    assert validate_event_photo((ROOT/(expected+'-accepted.jpg')).read_bytes(),expected)['subject']==expected


def test_traffic_does_not_become_a_source_event_concert():
    with pytest.raises(MatchRejected):validate_event_photo((ROOT/'traffic-meeting.jpg').read_bytes(),'concert')


def flyer(background,foreground,lines):
    image=Image.new('RGB',(1200,800),background);draw=ImageDraw.Draw(image)
    for index,line in enumerate(lines):
        draw.text((80,120+index*170),line,fill=foreground,font=ImageFont.load_default(72))
    buffer=io.BytesIO();image.save(buffer,'JPEG',quality=90)
    return buffer.getvalue()


@pytest.mark.parametrize('background,foreground,lines',[
    ('#b3122a','white',['3. ZEYTIN FESTIVALI','31 EKIM - 1 KASIM','ORHANLI KOYU']),
    ('white','#112233',['DUYURU','BELEDIYE MECLIS','TOPLANTISI 14:00']),
])
def test_text_flyer_is_not_a_real_occasion_photograph(background,foreground,lines):
    with pytest.raises(MatchRejected):validate_news_photo(flyer(background,foreground,lines),'festival')


@pytest.mark.parametrize('row',STOCK,ids=lambda r:r['subject'])
def test_empty_reviewed_stock_scene_is_not_a_real_occasion_photograph(row):
    with pytest.raises(MatchRejected):_validate_occasion((DIRECTORY/row['file']).read_bytes(),row['subject'])
