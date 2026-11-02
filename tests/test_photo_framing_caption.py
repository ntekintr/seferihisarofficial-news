from copy import deepcopy
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.editor import caption, event_description_repeats_title
from seferihisar.render import render_post


@pytest.mark.parametrize('description', [
    'Etkinlik duyurusu. Ebeveyn–Çocuk Çini EtkinliğiEbeveyn & Çocuk Çini Etkinliği',
    'Ebeveyn & Çocuk Çini Etkinliği',
    'Ebeveyn & Çocuk Çini Etkinliği Ebeveyn & Çocuk Çini Etkinliği',
])
def test_glued_or_punctuation_variant_title_only_copy_is_not_repeated_in_caption(event, description):
    event.update(title='Ebeveyn & Çocuk Çini Etkinliği', description=description)
    before=deepcopy(event)
    result=caption(event,event['title'])
    assert 'Kaynak duyurusundan:' not in result
    assert event['url'] in result and 'Kaynak: '+event['source_name'] in result
    assert event==before


@pytest.mark.parametrize('description', [
    'Etkinlik duyurusu. Ebeveyn & Çocuk Çini Etkinliği. Malzemeler ücrete dahildir.',
    'Ebeveyn & Çocuk Çini Etkinliği iptal edildi.',
    'Ebeveyn & Çocuk Çini Etkinliği sonrası sergi açılacak.',
])
def test_real_program_cancellation_and_price_details_remain(event, description):
    event.update(title='Ebeveyn & Çocuk Çini Etkinliği', description=description)
    assert not event_description_repeats_title(description,event['title'])
    assert description in caption(event,event['title'])


@pytest.mark.parametrize('status,center', [('prepared',(0.5,1.0)), ('published',(0.5,0.5)),
    ('publishing',(0.5,0.5)), ('uncertain',(0.5,0.5))])
def test_yoga_floor_subject_is_visible_without_changing_claimed_photo_frames(tmp_path,status,center):
    # A representative square photo: floor/mat at the bottom, wall above.
    photo=Image.new('RGB',(768,768),'white')
    for y in range(600,768):
        for x in range(768):photo.putpixel((x,y),(200,0,0))
    source=tmp_path/'source.png';photo.save(source)
    post={'id':'a'*24,'kind':'announcement','category':'event','status':status,
          'slides':[{'title':'Hatha Yoga','body':'16.10.2026 · 18:00\nUrla'}]}
    render_post(post,tmp_path/'public',{0:source})
    # Bottom anchoring retains the mat in feed and story. Centered frames
    # exclude it; published media retains that established crop unchanged.
    for fmt,point in [('feed',(500,560)),('story',(500,960))]:
        with Image.open(tmp_path/'public/media'/post['id']/(fmt+'-1.jpg')) as card:
            # A prepared card's picture also grows into any unused text space.
            if center[1]==1.0:
                assert any(r>150 and g<30 for r,g,_ in (card.getpixel((500,y)) for y in range(point[1]-400,point[1]+400,10)))
            else:assert min(card.getpixel(point))>220


def test_theatre_named_yoga_keeps_centered_frame_and_branding(tmp_path,monkeypatch):
    card=Mock();monkeypatch.setattr('seferihisar.render.card',card)
    post={'id':'b'*24,'kind':'announcement','category':'theatre','status':'prepared',
          'slides':[{'title':'Yoga adlı tiyatro oyunu','body':'16.10.2026 · 18:00'}]}
    render_post(post,tmp_path)
    assert all(call.kwargs['photo_centering']==(0.5,0.5) for call in card.call_args_list)
