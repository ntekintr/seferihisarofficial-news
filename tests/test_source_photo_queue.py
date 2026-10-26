"""No-photo pages cannot starve later original images or become publish failures."""
import io
import json
from contextlib import closing
from unittest.mock import Mock

from PIL import Image

from seferihisar.domain import parse_date
from seferihisar.operations import failed, record_check, safe_result
from seferihisar.security import validate_state
from seferihisar.source_photos import SourcePhotos, MAX_READS, MAX_SOURCE_CHECKS
from seferihisar.store import Store
from seferihisar.visual_match import MatchRejected

AT = parse_date('2026-10-26T08:40:00+03:00')
SOURCE = {'id': 'local-paper', 'name': 'Yerel gazete', 'url': 'https://news.example/haberler',
          'kind': 'html', 'enabled': True, 'trusted': True, 'access': 'robots'}
PHOTO = 'https://news.example/uploads/meeting.jpg'


def item(store, number):
    url = f'https://news.example/muhtarlar-{number}'
    store.upsert({'kind': 'news', 'category': 'news', 'source_id': SOURCE['id'],
                  'source_name': SOURCE['name'], 'url': url, 'sources': [url],
                  'title': f'Isparta ve Seferihisar muhtarları {number} numaralı mahallede toplantı yaptı',
                  'description': 'Mahalle muhtarları toplantıda güncel talepleri görüştü.',
                  'published_at': '2026-10-26T08:00:00+03:00'}, AT.isoformat())
    return next(row for row in store.items() if row['url'] == url)


def page(row, photo=False):
    data = {'@type': 'NewsArticle', 'headline': row['title'],
            'description': row['description'], 'datePublished': row['published_at']}
    picture = f'<img src="{PHOTO}" alt="Muhtarlar toplantısı">' if photo else ''
    return ('<script type="application/ld+json">' + json.dumps(data) + '</script>'
            + f'<article><h1>{row["title"]}</h1><p>{row["description"]}</p>{picture}</article>')


def manager(store, tmp_path, monkeypatch):
    monkeypatch.setenv('SOURCE_PHOTOS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', lambda *args: None)
    fetcher = Mock()
    raw = io.BytesIO(); Image.new('RGB', (1024, 768), '#345678').save(raw, 'JPEG')
    fetcher.image.return_value = (raw.getvalue(), PHOTO)
    return SourcePhotos(store, AT, tmp_path/'photos', [SOURCE], fetcher=fetcher), fetcher


def test_no_image_pages_leave_image_slots_for_later_original(tmp_path, monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        rows = [item(store, n) for n in range(3)]
        photos, fetcher = manager(store, tmp_path, monkeypatch)
        fetcher.get.side_effect = [(page(row, photo=n == 2), row['url']) for n, row in enumerate(rows)]
        assert photos.image(rows[0]) is None and photos.image(rows[1]) is None
        assert photos.image(rows[2]) is not None
        assert photos.reads == fetcher.image.call_count == 1
        assert photos.stats['source_checks'] == fetcher.get.call_count == 3
        assert photos.stats['downloaded'] == 1
        assert photos.stats['rejection_stages'] == {'source_binding': 2}
        assert photos.image(rows[0]) is None  # No repeat within one run.
        assert fetcher.get.call_count == 3


def test_empty_sources_have_their_own_bounded_check_limit(tmp_path, monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        rows = [item(store, n) for n in range(MAX_SOURCE_CHECKS + 2)]
        photos, fetcher = manager(store, tmp_path, monkeypatch)
        fetcher.get.side_effect = [(page(row), row['url']) for row in rows]
        assert all(photos.image(row) is None for row in rows)
        assert photos.stats['source_checks'] == fetcher.get.call_count == MAX_SOURCE_CHECKS
        assert photos.reads == fetcher.image.call_count == 0
        assert photos.stats['deferred'] == 2


def test_rejected_image_downloads_still_consume_existing_two_slots(tmp_path, monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        rows = [item(store, n) for n in range(3)]
        photos, fetcher = manager(store, tmp_path, monkeypatch)
        fetcher.get.side_effect = [(page(row, photo=True), row['url']) for row in rows]
        def reject(*args):
            raise MatchRejected('Wrong subject')
        monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', reject)
        monkeypatch.setattr('seferihisar.visual_match.validate_headline_photo', reject)
        assert all(photos.image(row) is None for row in rows)
        assert photos.reads == fetcher.image.call_count == fetcher.get.call_count == MAX_READS == 2
        assert photos.stats['deferred'] == 1
        assert store.rows('SELECT * FROM source_photos') == []


def test_visual_wait_is_recorded_without_claim_or_false_failure(tmp_path):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        result = {'status': 'awaiting_content_visual', 'facebook': {'status': 'awaiting_content_visual'}}
        assert safe_result(result) == result and failed(result) is False
        assert record_check(store, result, AT, 'automatic') == result
        assert json.loads(store.rows('SELECT result FROM publication_checks')[0]['result']) == result
        assert store.rows('SELECT * FROM posts') == []
        validate_state(store.path)
