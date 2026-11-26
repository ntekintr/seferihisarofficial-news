"""Owner, 26 Nov 2026: no unrelated generated picture, no one-word caption
heading and no private adoption/help appeal goes out as a news card."""
import json
from contextlib import closing
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seferihisar import illustrations
from seferihisar.domain import digest, parse_date
from seferihisar.illustrations import Illustrator, image_key
from seferihisar.instagram import publish_one
from seferihisar.operations import STATUSES, FAILURES, summary
from seferihisar.quality import mobile_number, news_editorial_reason, publication_copy_reason
from seferihisar.schedule import prepare, queue_item
from seferihisar.store import Store
from seferihisar.visual_policy import image_reason


def adapter():
    api = Mock()
    api.enabled.return_value = True
    api.account = '1234'
    api.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type': 'image/jpeg'})
    api.container.return_value = 'container-1'
    api.call.return_value = {'id': 'media-1'}
    return api


def assets_for(store):
    return {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"], 'story': [f"media/{p['id']}/story-1.jpg"]}
            for p in store.posts()}


AT = parse_date('2026-11-26T10:00:00+03:00')
# The card of 26 Nov 2026 (instagram-sehayder), shortened, with a fictional number.
BARINAKTA = {
    'kind': 'news', 'category': 'news', 'source_id': 'instagram-sehayder', 'source_name': 'SEHAYDER',
    'title': 'Barınakta',
    'description': ('Barınakta yaşayan dostlarımız sıcak bir yuva bekliyor. Seferihisar’da sahiplenmek isteyenler '
                    '0532 123 45 67 numarasından ulaşabilir.'),
    'url': 'https://www.instagram.com/p/EXAMPLE1/', 'sources': ['https://www.instagram.com/p/EXAMPLE1/'],
    'published_at': '2026-11-26T08:00:00+03:00',
}


def news(title, description='Seferihisar’da yapılan açıklamada vatandaşlara ayrıntılı bilgi verildi.',
         source_id='example-haber', url='https://www.example-haber.com.tr/haber-1'):
    return {'kind': 'news', 'category': 'news', 'source_id': source_id, 'source_name': 'Kaynak',
            'title': title, 'description': description, 'url': url, 'sources': [url],
            'published_at': '2026-11-26T08:00:00+03:00'}


def test_the_barinakta_card_is_held_for_its_number_and_its_heading():
    assert news_editorial_reason(BARINAKTA) == 'personal_mobile_number'
    without_number = {**BARINAKTA, 'description': 'Barınakta yaşayan dostlarımız Seferihisar’da sıcak bir yuva bekliyor.'}
    assert news_editorial_reason(without_number) == 'headline_too_short'


@pytest.mark.parametrize('text', [
    '0532 123 45 67', '05321234567', '+90 532 123 45 67', '+905321234567', '90 532 123 4567',
    '0 (532) 123 45 67', '(0532) 123-45-67', '532 123 45 67', '0532.123.45.67', 'Bilgi için: 0505 987 65 43.',
])
def test_turkish_mobile_numbers_are_found_in_any_spelling(text):
    assert mobile_number('Sahiplenmek için ' + text + ' arayabilirsiniz')


@pytest.mark.parametrize('text', [
    '0232 743 11 11', '(0232) 743 45 67', '0232 512 34 56', '444 0 532', 'Alo 153', '112 Acil Çağrı',
    '0850 222 05 32', '2026 bütçesi 5.000.000.000 TL', 'Saat 15.30', '10 532 kişi katıldı',
])
def test_institutional_lines_and_other_numbers_are_not_mobile(text):
    assert not mobile_number(text)


def test_an_institutional_line_does_not_hold_news():
    item = news('Belediye su arızası için çağrı merkezini duyurdu',
                'Seferihisar Belediyesi arızalar için 0232 743 11 11, 444 35 35 ve Alo 153 hatlarının açık olduğunu bildirdi.')
    assert news_editorial_reason(item) is None


@pytest.mark.parametrize('title, description, reason', [
    ('Fırtına uyarısı', 'Seferihisar’da gece başlayan fırtına sabah saatlerinde etkisini artırdı.', 'headline_too_short'),
    ('Seferihisar’da fırtına etkili oldu', 'Seferihisar’da gece başlayan fırtına sabah saatlerinde etkisini artırdı.', None),
])
def test_headings_need_three_words(title, description, reason):
    assert news_editorial_reason(news(title, description)) == reason


@pytest.mark.parametrize('description', [
    # The caption continues the cut first line with an ellipsis ...
    'Belediye ekipleri Seferihisar’da yeni park alanında... çalışmalar hafta boyunca sürecek dedi.',
    # ... or the heading was cut inside a word.
    'Belediye ekipleri Seferihisar’da yeni park alanındaki çalışmalarını hafta boyunca sürdürecek.',
])
def test_a_heading_cut_from_a_social_caption_is_held(description):
    title = 'Belediye ekipleri Seferihisar’da yeni park alanında'
    social = news(title, description, source_id='instagram-seferihisar-belediyesi',
                  url='https://www.instagram.com/p/EXAMPLE2/')
    assert news_editorial_reason(social) == 'headline_caption_fragment'
    # A website article whose summary begins with its heading is not a cut caption.
    assert news_editorial_reason(news(title, description)) is None


def test_a_complete_social_first_sentence_is_not_a_fragment():
    item = news('Belediye ekipleri Seferihisar’da yeni parkı açtı',
                'Belediye ekipleri Seferihisar’da yeni parkı açtı. Park hafta sonu ziyaretçilere hizmet verecek.',
                source_id='instagram-seferihisar-belediyesi', url='https://www.instagram.com/p/EXAMPLE3/')
    assert news_editorial_reason(item) is None


def test_research_never_queues_the_appeal_and_the_panel_names_the_reason(store):
    key, _ = store.upsert(BARINAKTA, AT.isoformat())
    prepare(store, AT)
    assert not [p for p in store.posts() if p.get('item_id') == key]
    assert store.rows('SELECT reason FROM withheld WHERE id=?', (digest(key + ':editorial'),)) == [
        {'reason': 'personal_mobile_number'}]
    holds = summary(store, AT)['editorial_holds']
    assert holds['personal_mobile_number'] == 1
    assert holds['headline_too_short'] == holds['headline_caption_fragment'] == 0


def test_a_card_queued_before_the_gate_is_held_at_publication(store):
    key, _ = store.upsert(BARINAKTA, AT.isoformat())
    queue_item(store, {**BARINAKTA, 'id': key, 'revision': 1}, 'news', AT, AT)
    card = next(p for p in store.posts() if p['item_id'] == key)
    assert publication_copy_reason(card, {i['id']: i for i in store.items()}) == 'editorial_review_required'
    publish_one(store, AT + timedelta(minutes=5), 'https://example.org/', assets_for(store), adapter=adapter())
    assert next(p for p in store.posts() if p['item_id'] == key)['status'] == 'blocked_source'


UNCLASSIFIED = news('Ethem amca cumhuriyetin 103’üncü yılını okuduğu şiirlerle kutladı',
                    'Seferihisar’da yaşayan Ethem amca bayram için yazdığı şiirleri okudu.')
PARKING = news('Seferihisar’da yeni otopark hizmete açıldı',
               'Belediye ilçe merkezinde 173 araçlık yeni otoparkı hizmete açtı.')


def enabled_illustrator(store, tmp_path, monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'test-token')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    return Illustrator(store, AT, tmp_path / 'images', session=Mock())


def test_unclassified_news_gets_no_generated_or_cached_scene(tmp_path, monkeypatch):
    assert illustrations.ARTICLE_SCENES_ENABLED is False
    describe, render = Mock(), Mock()
    monkeypatch.setattr('seferihisar.illustrations.describe', describe)
    monkeypatch.setattr(Illustrator, 'render', lambda self, prompt: render(prompt))
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        key, _ = store.upsert(UNCLASSIFIED, AT.isoformat())
        item = store.items()[0]
        # A scene cached by the old release is not reused either.
        store.db.execute('INSERT INTO illustrations VALUES (?,?,?,?,?,?,?)',
                         (image_key(item), key, 'ready', b'\xff\xd8cached', 1, AT.isoformat(), AT.isoformat()))
        store.db.commit()
        generator = enabled_illustrator(store, tmp_path, monkeypatch)
        assert generator.image(item, True) is None and generator.image(item, False) is None
        assert describe.call_count == render.call_count == 0
        stats = generator.stats
        assert stats['article_scene_disabled'] == stats['text_only'] == 2
        assert stats['article_scenes_enabled'] is False and stats['attempted'] == stats['article_scene'] == 0


def test_reviewed_topics_keep_their_scene_path(tmp_path, monkeypatch):
    generate = Mock(return_value=None)
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        store.upsert(PARKING, AT.isoformat())
        item = store.items()[0]
        generator = enabled_illustrator(store, tmp_path, monkeypatch)
        monkeypatch.setattr(generator, '_reuse_scene', lambda *args: generate() or None)
        generator.image(item, True)
        assert generate.call_count == 1 and generator.stats['article_scene_disabled'] == 0


def bind_scene(store, key):
    row = store.rows('SELECT payload FROM posts WHERE item_id=?', (key,))[0]
    payload = json.loads(row['payload'])
    payload['illustration_keys'] = {'0': 'a' * 24}
    payload['visual_review'] = {'images': {'0': 'b' * 64}}
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE item_id=?', (json.dumps(payload, ensure_ascii=False), key))
    return next(p for p in store.posts() if p['item_id'] == key)


def test_a_prepared_card_with_an_old_scene_waits_for_its_text_render(store):
    key, _ = store.upsert(UNCLASSIFIED, AT.isoformat())
    queue_item(store, {**UNCLASSIFIED, 'id': key, 'revision': 1}, 'news', AT, AT)
    card = bind_scene(store, key)
    items = {i['id']: i for i in store.items()}
    assert image_reason(card, items) == 'article_scene_retired'
    assert image_reason({**card, 'status': 'published'}, items) is None
    result = publish_one(store, AT + timedelta(minutes=5), 'https://example.org/', assets_for(store),
                         adapter=adapter(), require_visual_review=True)
    assert result == {'status': 'article_scene_retired'}
    assert 'article_scene_retired' in STATUSES and 'article_scene_retired' not in FAILURES
    assert next(p for p in store.posts() if p['item_id'] == key)['status'] == 'prepared'


def test_a_reviewed_topic_scene_is_not_retired(store):
    key, _ = store.upsert(PARKING, AT.isoformat())
    queue_item(store, {**PARKING, 'id': key, 'revision': 1}, 'news', AT, AT)
    card = bind_scene(store, key)
    assert image_reason(card, {i['id']: i for i in store.items()}) is None
