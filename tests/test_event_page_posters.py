"""14 Nov: the 26th Mandalina Şenliği went out with a generated food table.

The municipality's own event page carried the official poster, and İzmir Art
pages name each show's poster; neither source had a poster reader.
"""
import io
import json
from contextlib import closing
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from seferihisar.domain import digest, parse_date
from seferihisar.source_photo_data import event_page_source, same_event_artwork
from seferihisar.source_photos import NoArticleImage, SourcePhotos, candidate_urls
from seferihisar.store import Store

AT = parse_date('2026-11-13T12:00:00+03:00')
CALENDAR = {'id': 'seferihisar-calendar', 'name': 'Seferihisar Belediyesi etkinlik takvimi',
            'url': 'https://seferihisar.bel.tr/Kurumsal/TakvimService.aspx', 'kind': 'municipal_calendar',
            'enabled': True, 'trusted': True, 'access': 'robots', 'allow_missing_robots': True}
ART = {'id': 'izmir-art', 'name': 'İzmir Art etkinlik takvimi',
       'url': 'https://www.izmir.art/eventsContent.json?eventLocation=1', 'kind': 'izmir_art',
       'enabled': True, 'trusted': True, 'access': 'robots'}
FESTIVAL = 'https://seferihisar.bel.tr/26-seferihisar-mandalina-senligi'
POSTER = 'https://seferihisar.bel.tr/assets/img/sayfalar/buyuk/26-seferihisar-mandalina-senligi.webp'
SHOW = 'https://www.izmir.art/tr/kurk-mantolu-madonna-yJiPE6gdk?seans=6af17a57989273de48df8a33'
ART_POSTER = 'https://www.izmir.art/1024/1024/img/uploads/image-d3dcac5454778aecb8d6b8be7948b70c9e070fd4.png'


def municipal_page(title='26. SEFERİHİSAR MANDALİNA ŞENLİĞİ',
                   og='https://seferihisar.bel.tr//assets/img/sayfalar/buyuk/26-seferihisar-mandalina-senligi.webp',
                   main='/assets/img/sayfalar/buyuk/26-seferihisar-mandalina-senligi.webp'):
    head = f"<meta property='og:image' content='{og}' />" if og else ''
    picture = f'<img id="MainContent_img" class="img-fluid" src="{main}" />' if main else ''
    return (f'<html><head>{head}</head><body><div class="col-md-9"><div class="inner">'
            f'<h2 class="right-title">{title}</h2></div><div class="inner">{picture}'
            '<p>🕒 14:00</p><p>📍 Seferihisar Kapalı Pazar yeri</p></div></div></body></html>')


def art_page(title='Kürk Mantolu Madonna  ', og=ART_POSTER):
    head = f'<meta property="og:image" content="{og}">' if og else ''
    return (f'<html><head>{head}</head><body><h1>{title}</h1>'
            '<img src="/300/300/img/uploads/image-d3dcac5454778aecb8d6b8be7948b70c9e070fd4.png"></body></html>')


def festival():
    return {'id': 'a68c297a0020abb551c59eca', 'revision': 2, 'kind': 'event', 'source_id': CALENDAR['id'],
            'source_name': CALENDAR['name'], 'title': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ', 'url': FESTIVAL,
            'identity': FESTIVAL, 'category': 'food', 'status': 'scheduled', 'time_known': True,
            'start': '2026-12-06T14:00:00+03:00', 'end': '2026-12-06T14:00:00+03:00',
            'location': 'Seferihisar Kapalı Pazar yeri', 'description': '26. SEFERİHİSAR MANDALİNA ŞENLİĞİ'}


def show(url=SHOW):
    return {'id': digest(url), 'revision': 1, 'kind': 'event', 'source_id': ART['id'], 'source_name': ART['name'],
            'title': 'Kürk Mantolu Madonna', 'url': url, 'identity': url, 'category': 'theatre', 'status': 'scheduled',
            'time_known': True, 'start': '2026-12-05T20:00:00+03:00', 'end': '2026-12-05T21:30:00+03:00',
            'location': 'Urla Hakan Çeken Kültür Merkezi', 'description': 'Tiyatro'}


def test_only_the_two_reviewed_event_sources_read_their_pages_poster():
    assert event_page_source(CALENDAR) and event_page_source(ART)
    assert not event_page_source({**CALENDAR, 'url': 'https://seferihisar.bel.tr.example.org/x'})
    assert not event_page_source({**ART, 'kind': 'html'})
    assert not event_page_source({'id': 'haber32', 'kind': 'html', 'url': 'https://www.haber32.com.tr/'})


def test_the_municipal_event_pages_own_poster_is_its_image():
    # OpenGraph writes "//assets"; it is the same file as the page's main picture.
    assert candidate_urls(municipal_page(), FESTIVAL, festival(), CALENDAR) == [POSTER]
    assert candidate_urls(municipal_page(og=None), FESTIVAL, festival(), CALENDAR) == [POSTER]


def test_an_izmir_art_shows_own_poster_is_its_image():
    assert candidate_urls(art_page(), SHOW, show(), ART) == [ART_POSTER]


def test_another_events_page_is_never_bound():
    with pytest.raises(ValueError) as refusal:
        candidate_urls(municipal_page(title='Başka Etkinlik'), FESTIVAL, festival(), CALENDAR)
    assert not isinstance(refusal.value, NoArticleImage)
    with pytest.raises(ValueError):
        candidate_urls(art_page(), 'https://www.izmir.art/tr/baska', show(), ART)


def test_a_page_without_its_own_poster_may_get_a_scene():
    # The site's default share logo is not the event's picture.
    with pytest.raises(NoArticleImage):
        candidate_urls(municipal_page(og='https://seferihisar.bel.tr/assets/img/logo.png', main=None), FESTIVAL, festival(), CALENDAR)
    with pytest.raises(NoArticleImage):
        candidate_urls(art_page(og='https://cdn.example.org/img/uploads/image-' + 'a' * 40 + '.png'), SHOW, show(), ART)


def poster(size=(1200, 1500)):
    raw = io.BytesIO()
    Image.new('RGB', size, '#f39a2b').save(raw, 'JPEG')
    return raw.getvalue()


@pytest.fixture
def store(tmp_path):
    with closing(Store(tmp_path / 'state.sqlite')) as opened:
        yield opened


def photos(store, tmp_path, monkeypatch, html=None):
    monkeypatch.setenv('SOURCE_PHOTOS_ENABLED', 'true')
    fetcher = Mock()
    fetcher.get.return_value = (html or municipal_page(), FESTIVAL)
    fetcher.image.return_value = (poster(), POSTER)
    return SourcePhotos(store, AT, tmp_path / 'photos', [CALENDAR, ART], fetcher=fetcher), fetcher


def card(row):
    return {'id': 'c' * 24, 'item_id': row['id'], 'revision': row['revision'], 'status': 'prepared'}


@pytest.mark.parametrize('failure', [None, ValueError('Poster text unreadable')])
def test_the_festival_card_carries_the_municipal_poster(store, tmp_path, monkeypatch, failure):
    monkeypatch.setattr('seferihisar.event_image_text.validate',
                        Mock(side_effect=failure) if failure else (lambda *args, **kwargs: True))
    reader, _ = photos(store, tmp_path, monkeypatch)
    row = festival(); post = card(row)
    assert list(reader.for_post(post, {row['id']: row})) == [0]
    assert not reader.awaits_original(post, {row['id']: row})
    assert json.loads(store.rows('SELECT payload FROM source_photos')[0]['payload'])['image_url'] == POSTER


def test_the_festival_waits_without_a_scene_while_its_poster_cannot_be_read(store, tmp_path, monkeypatch):
    reader, fetcher = photos(store, tmp_path, monkeypatch)
    fetcher.image.side_effect = requests.ConnectionError('offline')
    row = festival()
    assert reader.for_post(card(row), {row['id']: row}) == {}
    assert reader.awaits_original(card(row), {row['id']: row})


def test_a_municipal_event_without_a_poster_may_get_a_scene(store, tmp_path, monkeypatch):
    reader, _ = photos(store, tmp_path, monkeypatch, municipal_page(og=None, main=None))
    row = festival()
    assert reader.for_post(card(row), {row['id']: row}) == {}
    assert not reader.awaits_original(card(row), {row['id']: row})


def test_sessions_of_one_izmir_art_show_share_its_poster():
    evidence = {'version': 'source-photo-event-v1', 'source_id': 'izmir-art', 'source_url': SHOW,
                'title': 'Kürk Mantolu Madonna', 'subject': 'theatre'}
    other = show(SHOW.replace('6af17a57989273de48df8a33', '6af17a57989273de48df8a34'))
    assert same_event_artwork(evidence, other)
    assert not same_event_artwork(evidence, show('https://www.izmir.art/tr/sefiller?seans=6af17989989273de48df8a2e'))


WEBP = b'RIFF\xf8r\x01\x00WEBPVP8 ' + b'\x00' * 32


def image_session(content_type, body, monkeypatch):
    monkeypatch.setattr('seferihisar.collect.safe_url', lambda url, hosts: url)
    monkeypatch.setattr('seferihisar.collect.time.sleep', lambda seconds: None)

    def get(url, **kwargs):
        if url.endswith('/robots.txt'):
            response = Mock(is_redirect=False, status_code=200, headers={'Content-Type': 'text/plain'})
            response.iter_content.return_value = [b'User-agent: *\nAllow: /\n']
            response.text = 'User-agent: *\nAllow: /\n'
            return response
        response = Mock(is_redirect=False, status_code=200,
                        headers={} if content_type is None else {'Content-Type': content_type})
        response.iter_content.return_value = [body]
        return response
    return Mock(get=Mock(side_effect=get))


def test_izmir_arts_untyped_webp_poster_is_read_from_its_signature(monkeypatch):
    from seferihisar.collect import Fetcher
    opted = {**ART, 'untyped_images': True}
    assert Fetcher([opted], image_session(None, WEBP, monkeypatch)).image(ART_POSTER)[0] == WEBP


@pytest.mark.parametrize('content_type,body,opt_in', [
    (None, WEBP, False),                 # another host without the opt-in
    (None, b'<html>not found</html>', True),  # no image signature
    ('text/html', WEBP, True),           # a wrong declared type stays refused
])
def test_every_other_untyped_or_mistyped_answer_is_still_refused(monkeypatch, content_type, body, opt_in):
    from seferihisar.collect import Fetcher
    source = {**ART, 'untyped_images': True} if opt_in else ART
    with pytest.raises(ValueError, match='Unsupported source image response'):
        Fetcher([source], image_session(content_type, body, monkeypatch)).image(ART_POSTER)


def test_only_izmir_art_has_the_untyped_image_opt_in():
    sources = json.load(open('config/sources.json', encoding='utf-8'))
    sources = sources if isinstance(sources, list) else sources['sources']
    assert [s['id'] for s in sources if s.get('untyped_images')] == ['izmir-art']


def test_a_festival_named_after_the_fruit_shows_the_fruit():
    from seferihisar.illustrations import scene_brief
    from seferihisar.visual_topics import SCENES
    assert scene_brief(festival()) == SCENES['citrus_basket']
    assert scene_brief({**festival(), 'title': 'Seferihisar Kış Şenliği'}) != SCENES['citrus_basket']
