import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest
from seferihisar.editor import verify
from seferihisar.facebook import publish_recent
from seferihisar.instagram import publish_one
from seferihisar.schedule import prepare, source_current


def notice(at, title):
    url = 'https://www.instagram.com/p/synthetic123/'
    return {'kind': 'news', 'title': title, 'description':
            'Seferihisar’da koruma altına alınan bir köpek. Köpeğini arayan ailesi varsa kaynağa ulaşsın.',
            'url': url, 'sources': [url], 'source_id': 'instagram-sehayder',
            'source_name': 'SEHAYDER Instagram', 'category': 'news', 'published_at': at.isoformat()}


@pytest.mark.parametrize('title,reason', [
    ('0000 0000000', 'insufficient_headline'),
    ('🙏🙏AİLESİ BULUNDU 🙏🙏', 'resolved_community_notice'),
    ('Sahibi bulundu', 'resolved_community_notice'),
])
def test_incomplete_or_resolved_notice_is_withheld_at_intake(at, title, reason):
    source = next(s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))
                  if s['id'] == 'instagram-sehayder')
    assert verify(notice(at, title), source, at) == reason


@pytest.mark.parametrize('title', ['0000 0000000', '🙏🙏AİLESİ BULUNDU 🙏🙏'])
@pytest.mark.parametrize('destination', ['feed', 'story', 'facebook'])
def test_legacy_bad_notice_cannot_reach_any_destination(store, at, title, destination):
    item = notice(at, title)
    item_id, _ = store.upsert(item, at.isoformat())
    key = digest('synthetic-notice')
    parent = {'id': key, 'item_id': item_id, 'revision': 1, 'kind': 'news',
              'due_at': at.isoformat(), 'created_at': at.isoformat(), 'title': title,
              'caption': 'Legacy text', 'category': 'news', 'source_urls': item['sources'],
              'slides': [{'title': title, 'body': item['description']}], 'formats': ['feed', 'story']}
    store.queue(parent)
    api = Mock()
    api.enabled.return_value = api.check_identity.return_value = True
    api.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    api.container.return_value = 'synthetic-container'
    api.call.return_value = {'id': 'synthetic-media'}
    assets = {key: {fmt: [f'media/{key}/{fmt}-1.jpg'] for fmt in ('feed', 'story')}}
    if destination == 'facebook':
        parent['published_at'] = at.isoformat()
        with store.db:
            store.db.execute("UPDATE posts SET status='published',payload=?,media_id='synthetic-media'",
                             (json.dumps(parent),))
        before = store.rows('SELECT * FROM posts')
        assert publish_recent(store, at, 'https://example.org/', assets, api)['status'] == 'blocked_source'
        assert store.rows('SELECT * FROM posts') == before
        assert store.rows('SELECT * FROM facebook_deliveries') == []
        api.upload.assert_not_called()
    else:
        assert publish_one(store, at, 'https://example.org/', assets,
                           story=destination == 'story', adapter=api)['status'] == 'empty'
    api.container.assert_not_called()
    api.publish.assert_not_called()
    assert not source_current(store.items()[0], at, set())


def test_named_active_notice_is_still_eligible(store, at):
    item = notice(at, 'Seferihisar’da yavru köpek için aile aranıyor')
    store.upsert(item, at.isoformat())
    prepare(store, at)
    assert any(p['status'] == 'prepared' for p in store.posts())


def test_numeric_play_name_and_other_sources_resolved_news_are_not_reclassified(event, at):
    from seferihisar.timeliness import publication_reason
    assert publication_reason({**event, 'title': '1984'}, at) is None
    assert publication_reason({**notice(at, 'Sahibi bulundu'), 'source_id': 'other-news'}, at) is None


def test_shop_sale_is_held_but_a_public_discount_is_not(at):
    from seferihisar.quality import news_quality_reason
    # Isparta's 31 Oct menswear sale, which reached that queue as local news.
    shop = {'kind': 'news', 'title': 'JAKAMEN’DEN EFSANE KASIM KAMPANYASI! YÜZDE 70’E VARAN İNDİRİM FIRSATI',
            'description': 'JAKAMEN, Kasım ayına özel başlattığı dev indirim kampanyasıyla alışveriş tutkunlarına '
                           'kaçırılmayacak fırsatlar sunuyor.'}
    assert news_quality_reason(shop) == 'promotional_copy_requires_review'
    public = {'kind': 'news', 'title': 'Seferihisar’da su faturalarına yüzde 50’ye varan indirim',
              'description': 'Belediye ihtiyaç sahibi ailelerin su faturalarında indirim uygulanacağını açıkladı.'}
    assert news_quality_reason(public) is None
