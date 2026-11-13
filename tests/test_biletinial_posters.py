"""13 Nov: a Bademler workshop went out with a generated scene; Biletinial had its poster.

Biletinial names each session's poster in that session's own Event record, on
an image host that answers 403 for the robots.txt it does not have.
"""
import io
import json
from contextlib import closing
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from seferihisar.collect import Fetcher
from seferihisar.domain import digest, parse_date
from seferihisar.image_safety import IllustrationCheckUnavailable
from seferihisar.source_photo_data import approved_image_url, delivery_sources, same_event_artwork, ticket_artwork_source
from seferihisar.source_photos import MAX_ARTWORK_READS, MAX_READS, NoArticleImage, SourcePhotos, candidate_urls
from seferihisar.source_readers import ticket_items
from seferihisar.store import Store

AT = parse_date('2026-11-13T09:00:00+03:00')
PAGE = 'https://biletinial.com/tr-tr/egitim/aysin-koruk-ile-cini-atolyeleri-yetiskin'
POSTER = 'https://b6s54eznn8xq.merlincdn.net/Uploads/Films/aysin-koruk-ile-cini-atolyeleri-yetiskin-2026326.jpg'
TITLE = 'Ayşin Koruk ile Çini Atölyeleri (Yetişkin)'
BADEMLER = {'id': 'biletinial-bademler', 'name': 'Bademler Sanat Köyü — Biletinial etkinlikleri',
            'url': 'https://biletinial.com/tr-tr/mekan/bademler-sanat-koyu', 'kind': 'ticketing', 'enabled': True,
            'trusted': True, 'access': 'robots', 'expected_venue': 'Bademler Sanat Köyü'}
PAPER = {'id': 'haber32', 'url': 'https://www.haber32.com.tr/', 'enabled': True}


def session(start, image=POSTER):
    record = {'@context': 'https://schema.org', '@type': 'EducationEvent', 'name': TITLE, 'url': PAGE,
              'startDate': start, 'endDate': start, 'eventStatus': 'https://schema.org/EventScheduled',
              'description': 'Çini atölyesi.',
              'location': {'@type': 'Place', 'name': 'Bademler Sanat Köyü',
                           'address': {'@type': 'PostalAddress', 'streetAddress': 'Bademler',
                                       'addressLocality': 'Urla', 'addressRegion': 'İzmir'}},
              'offers': {'@type': 'Offer', 'url': PAGE, 'price': 900, 'priceCurrency': 'TRY'}}
    if image:
        record['image'] = image
    return record


def page(*starts, image=POSTER):
    records = ''.join(f'<script type="application/ld+json">{json.dumps(session(s, image))}</script>' for s in starts)
    return f'<html><head><link rel="canonical" href="{PAGE}"></head><body><h1>{TITLE}</h1>{records}</body></html>'


FIRST, SECOND = '2026-11-15T14:30:00', '2026-11-22T14:30:00'


def item(html=None, start=FIRST):
    rows = ticket_items(html or page(FIRST, SECOND), PAGE, BADEMLER)
    row = next(r for r in rows if r['start'].startswith(start))
    return {**row, 'id': digest(row['identity']), 'revision': 1, 'source_id': BADEMLER['id'],
            'source_name': BADEMLER['name'], 'status': 'scheduled'}


def test_biletinial_is_a_reviewed_poster_source_on_its_own_image_host():
    assert ticket_artwork_source(BADEMLER)
    assert not ticket_artwork_source({**BADEMLER, 'url': 'https://biletinial.com.example.org/'})
    assert approved_image_url(BADEMLER['id'], PAGE, POSTER)
    assert not approved_image_url(BADEMLER['id'], PAGE, POSTER.replace('/Uploads/Films/', '/Uploads/Other/'))
    assert not approved_image_url('haber32', 'https://www.haber32.com.tr/a', POSTER)


def test_the_sessions_own_poster_is_bound_from_its_schema():
    assert candidate_urls(page(FIRST, SECOND), PAGE, item(), BADEMLER) == [POSTER]
    with pytest.raises(NoArticleImage):
        candidate_urls(page(FIRST, SECOND, image=None), PAGE, item(page(FIRST, SECOND, image=None)), BADEMLER)
    elsewhere = page(FIRST, SECOND, image='https://cdn.example.org/poster.jpg')
    with pytest.raises(ValueError) as refusal:
        candidate_urls(elsewhere, PAGE, item(elsewhere), BADEMLER)
    assert not isinstance(refusal.value, NoArticleImage)


def jpeg(size=(800, 1100)):
    raw = io.BytesIO()
    Image.new('RGB', size, '#553311').save(raw, 'JPEG')
    return raw.getvalue()


@pytest.fixture
def store(tmp_path):
    with closing(Store(tmp_path / 'state.sqlite')) as opened:
        yield opened


def photos(store, tmp_path, monkeypatch, html=None):
    monkeypatch.setenv('SOURCE_PHOTOS_ENABLED', 'true')
    fetcher = Mock()
    fetcher.get.return_value = (html or page(FIRST, SECOND), PAGE)
    fetcher.image.return_value = (jpeg(), POSTER)
    return SourcePhotos(store, AT, tmp_path / 'photos', [BADEMLER], fetcher=fetcher), fetcher


@pytest.mark.parametrize('failure', [ValueError('Source poster title unreadable'), IllustrationCheckUnavailable()])
def test_a_poster_the_checks_cannot_read_is_still_the_shows_image(store, tmp_path, monkeypatch, failure):
    monkeypatch.setattr('seferihisar.event_image_text.validate', Mock(side_effect=failure))
    reader, _ = photos(store, tmp_path, monkeypatch)
    row = item()
    post = {'id': 'a' * 24, 'item_id': row['id'], 'revision': 1, 'status': 'prepared'}
    assert list(reader.for_post(post, {row['id']: row})) == [0] and not reader.awaits_original(post, {row['id']: row})
    assert json.loads(store.rows('SELECT payload FROM source_photos')[0]['payload'])['image_url'] == POSTER


def test_a_workshop_waits_without_a_scene_while_its_poster_may_exist(store, tmp_path, monkeypatch):
    reader, fetcher = photos(store, tmp_path, monkeypatch)
    fetcher.image.side_effect = requests.HTTPError('403')
    row = item()
    post = {'id': 'a' * 24, 'item_id': row['id'], 'revision': 1, 'status': 'prepared'}
    assert reader.for_post(post, {row['id']: row}) == {} and reader.awaits_original(post, {row['id']: row})


def test_a_workshop_without_any_poster_may_get_a_scene(store, tmp_path, monkeypatch):
    bare = page(FIRST, SECOND, image=None)
    reader, _ = photos(store, tmp_path, monkeypatch, bare)
    row = item(bare)
    post = {'id': 'a' * 24, 'item_id': row['id'], 'revision': 1, 'status': 'prepared'}
    assert reader.for_post(post, {row['id']: row}) == {} and not reader.awaits_original(post, {row['id']: row})


def test_weekly_sessions_of_one_workshop_share_its_poster(store, tmp_path, monkeypatch):
    monkeypatch.setattr('seferihisar.event_image_text.validate', lambda *args, **kwargs: True)
    reader, _ = photos(store, tmp_path, monkeypatch)
    first, second = item(), item(start=SECOND)
    assert reader.image(first)
    key = store.rows('SELECT id FROM source_photos')[0]['id']
    evidence = json.loads(store.rows('SELECT payload FROM source_photos')[0]['payload'])
    store.queue({'id': 'b' * 24, 'kind': 'announcement', 'revision': 1, 'due_at': AT.isoformat(), 'title': TITLE,
                 'item_id': first['id'], 'source_photo_keys': {'0': key}})
    with store.db:
        store.db.execute("UPDATE posts SET status='published' WHERE id=?", ('b' * 24,))
    assert same_event_artwork(evidence, second)
    assert reader.image(second) and len(store.rows('SELECT * FROM source_photos')) == 2
    assert not same_event_artwork(evidence, {**second, 'url': PAGE + '-baska'})


def test_a_poster_has_reads_of_its_own_when_news_used_them_all(store, tmp_path, monkeypatch):
    monkeypatch.setattr('seferihisar.event_image_text.validate', lambda *args, **kwargs: True)
    reader, _ = photos(store, tmp_path, monkeypatch)
    reader.reads = MAX_READS
    assert reader.image(item()) and reader.artwork_reads == 1 and reader.reads == MAX_READS
    later, fetcher = photos(store, tmp_path, monkeypatch)
    later.artwork_reads = MAX_ARTWORK_READS
    assert later.image(item(start=SECOND)) is None and later.stats['deferred'] == 1
    fetcher.image.assert_not_called()


def robots_session(status, monkeypatch):
    monkeypatch.setattr('seferihisar.collect.safe_url', lambda url, hosts: url)
    monkeypatch.setattr('seferihisar.collect.time.sleep', lambda seconds: None)

    def get(url, **kwargs):
        response = Mock(is_redirect=False, headers={'Content-Type': 'image/jpeg'})
        if url.endswith('/robots.txt'):
            response.status_code = status
            response.raise_for_status.side_effect = requests.HTTPError(response=response)
        response.iter_content.return_value = [b'\xff\xd8poster']
        return response
    return Mock(get=Mock(side_effect=get))


def test_only_the_reviewed_poster_host_reads_a_403_robots_file_as_absent(monkeypatch):
    hosts = delivery_sources({BADEMLER['id']: BADEMLER, PAPER['id']: PAPER})
    assert [s['url'] for s in hosts if s.get('robots_absent_as_403')] == ['https://b6s54eznn8xq.merlincdn.net/']
    assert Fetcher([BADEMLER] + hosts, robots_session(403, monkeypatch)).image(POSTER)[0] == b'\xff\xd8poster'


@pytest.mark.parametrize('status', [401, 404, 429, 500, 503])
def test_every_other_robots_answer_still_stops_the_poster(monkeypatch, status):
    hosts = delivery_sources({BADEMLER['id']: BADEMLER})
    with pytest.raises(requests.HTTPError):
        Fetcher([BADEMLER] + hosts, robots_session(status, monkeypatch)).image(POSTER)


def test_a_403_robots_file_still_stops_every_other_host(monkeypatch):
    with pytest.raises(requests.HTTPError):
        Fetcher([PAPER], robots_session(403, monkeypatch)).get('https://www.haber32.com.tr/haber')
    unreviewed = {'enabled': True, 'url': 'https://b6s54eznn8xq.merlincdn.net/'}
    with pytest.raises(requests.HTTPError):
        Fetcher([unreviewed], robots_session(403, monkeypatch)).image(POSTER)
