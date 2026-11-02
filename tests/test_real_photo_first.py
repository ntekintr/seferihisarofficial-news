"""1 Nov: a road opening was cut at "Dr.", left an empty band and showed a desk."""
import io
import json
from contextlib import closing
from datetime import timedelta
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.card_layout import FITTED, ONE_SCALE, VERSION, filled_hero
from seferihisar.domain import parse_date
from seferihisar.editorial_render import MAX_HERO_GROWTH, _compose
from seferihisar.media_caption import photo_credit_caption, without_photo_credit
from seferihisar.same_story import reports
from seferihisar.schedule import CARD_SUMMARY, card_summary
from seferihisar.source_photos import SourcePhotos, binding_reason, candidate_urls
from seferihisar.store import Store
from seferihisar.visual_match import MatchRejected
from seferihisar.visual_topics import news_subjects, unclassified_news

AT = parse_date('2026-11-01T15:00:00+03:00')
LEAD = 'İzmir Büyükşehir Belediyesi, Seferihisar’ın 30 yıllık çevreyolu hayalini gerçeğe dönüştürdü.'
TUGAY = 'Açılışta konuşan Başkan Dr. Cemil Tugay, Sığacık Kavşağı’na battı-çıktı yapılacağını, Millet Bahçesi’nin Büyükşehir’e tahsis edileceğini söyledi.'
LOCAL = {'id': 'local-paper', 'name': 'Yerel gazete', 'url': 'https://paper.example/haberler',
         'kind': 'html', 'enabled': True, 'trusted': True, 'access': 'robots'}
CITY = {'id': 'city-hall', 'name': 'Büyükşehir Belediyesi', 'url': 'https://city.example/haberler',
        'kind': 'html', 'enabled': True, 'trusted': True, 'access': 'robots'}
PHOTO = 'https://city.example/uploads/acilis.jpg'


def jpeg(color='#345678', size=(1024, 768)):
    raw = io.BytesIO()
    Image.new('RGB', size, color).save(raw, 'JPEG')
    return raw.getvalue()


def add(store, source, slug, title, **extra):
    url = source['url'].rsplit('/', 1)[0] + '/' + slug
    store.upsert({'kind': 'news', 'category': 'municipality', 'source_id': source['id'], 'source_name': source['name'],
                  'url': url, 'sources': [url], 'title': title, 'description': LEAD + ' ' + TUGAY,
                  'published_at': '2026-11-01T14:30:00+03:00', **extra}, AT.isoformat())
    return next(row for row in store.items() if row['url'] == url)


def page(row, picture=''):
    data = {'@type': 'NewsArticle', 'headline': row['title'], 'description': row['description'],
            'datePublished': row['published_at']}
    return ('<script type="application/ld+json">' + json.dumps(data) + '</script>'
            + f'<article><h1>{row["title"]}</h1><p>{row["description"]}</p>{picture}</article>')


@pytest.fixture
def store(tmp_path):
    with closing(Store(tmp_path / 'state.sqlite')) as opened:
        yield opened


def manager(store, tmp_path, monkeypatch, pages, sources=(LOCAL, CITY)):
    monkeypatch.setenv('SOURCE_PHOTOS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', lambda *args: None)
    fetcher = Mock()
    fetcher.get.side_effect = lambda url: (pages[url], url)
    fetcher.image.return_value = (jpeg(), PHOTO)
    return SourcePhotos(store, AT, tmp_path / 'photos', list(sources), fetcher=fetcher), fetcher


def road_story(store):
    own = add(store, LOCAL, 'cevreyolu', "Seferihisar'da 30 yıllık çevreyolu hayali gerçekleşti!")
    other = add(store, CITY, 'ulasim-mujdesi', 'Başkan Tugay’dan Seferihisar’a çevreyolu ve Millet Bahçesi müjdesi')
    return own, other


def test_a_title_abbreviation_never_ends_the_card_text():
    body = LEAD + ' ' + TUGAY
    assert card_summary(body) == body
    long = LEAD + ' Açılışta konuşan Başkan Dr. ' + 'Cemil Tugay yeni yolun ilçeye katkısını anlattı ' * 6 + 'dedi.'
    assert card_summary(long) == LEAD


def test_the_card_holds_every_whole_sentence_that_fits():
    extra = 'Yeni yol ilçe merkezindeki trafiği rahatlatacak.'
    body = ' '.join((LEAD, TUGAY, extra, extra, extra))
    summary = card_summary(body)
    assert len(summary) <= CARD_SUMMARY and summary.endswith('.') and TUGAY in summary


def test_a_source_cut_mid_sentence_falls_back_to_its_last_whole_sentence():
    assert card_summary(LEAD + ' Açılışta konuşan Başkan') == LEAD
    assert card_summary('kelime ' * 80).endswith('…')


def test_only_the_same_story_from_another_source_is_found(store):
    own, other = road_story(store)
    unrelated = add(store, CITY, 'zeytin', 'Zeytin üreticileri festivalde buluştu',
                    description='Üreticiler hasat sonrası ürünlerini tanıttı, sanatçılar sahne aldı.')
    same_source = add(store, LOCAL, 'tekrar', 'Çevreyolu açılışında Başkan Tugay konuştu')
    late = add(store, CITY, 'gecen-yil', 'Başkan Tugay’dan çevreyolu ve Millet Bahçesi sözü',
               published_at='2026-10-20T14:30:00+03:00')
    found = reports(own, [own, other, unrelated, same_source, late])
    assert [row['id'] for row in found] == [other['id']]


def test_same_story_photo_is_bound_named_and_credited(store, tmp_path, monkeypatch):
    own, other = road_story(store)
    photos, fetcher = manager(store, tmp_path, monkeypatch, {own['url']: page(own),
                                                             other['url']: page(other, f'<img src="{PHOTO}" alt="Açılış">')})
    post = {'id': 'a' * 24, 'kind': 'news', 'status': 'prepared', 'item_id': own['id'], 'revision': own['revision']}
    items = {row['id']: row for row in store.items()}
    assert photos.for_post(post, items)
    row = store.rows('SELECT * FROM source_photos')[0]
    value = json.loads(row['payload'])
    assert row['item_id'] == own['id'] and value['source_url'] == own['url'] and value['photo_url'] == other['url']
    assert photos.credit(post) == 'Büyükşehir Belediyesi'
    post['visual_review'] = {'images': {'0': value['sha256']}}
    assert binding_reason(store, post, items, AT) is None
    assert binding_reason(store, post, items, AT + timedelta(minutes=61)) == 'visual_review_stale'


def test_the_owner_keeps_a_photo_another_card_borrowed(store, tmp_path, monkeypatch):
    own, other = road_story(store)
    pages = {own['url']: page(own), other['url']: page(other, f'<img src="{PHOTO}" alt="Açılış">')}
    photos, _ = manager(store, tmp_path, monkeypatch, pages)
    photos.items = {row['id']: row for row in store.items()}
    assert photos.image(own)
    later, _ = manager(store, tmp_path, monkeypatch, pages)
    later.items = photos.items
    assert later.image(other)
    assert json.loads(store.rows('SELECT payload FROM source_photos WHERE item_id=?', (other['id'],))[0]['payload'])['version'] == 'source-photo-v1'


def test_a_photo_already_on_a_published_card_is_not_shown_again(store, tmp_path, monkeypatch):
    own, other = road_story(store)
    pages = {own['url']: page(own), other['url']: page(other, f'<img src="{PHOTO}" alt="Açılış">')}
    photos, _ = manager(store, tmp_path, monkeypatch, pages)
    photos.items = {row['id']: row for row in store.items()}
    assert photos.article_image(other)
    key = store.rows('SELECT id FROM source_photos')[0]['id']
    claim = {'id': 'b' * 24, 'kind': 'news', 'revision': 1, 'due_at': AT.isoformat(), 'title': 'Yayımlanmış haber',
             'item_id': other['id'], 'source_photo_keys': {'0': key}}
    store.queue(claim)
    with store.db:
        store.db.execute("UPDATE posts SET status='published' WHERE id=?", (claim['id'],))
    later, _ = manager(store, tmp_path, monkeypatch, pages)
    later.items = photos.items
    assert later.image(own) is None


def test_a_percent_encoded_opengraph_address_still_names_the_hero(store):
    row = add(store, LOCAL, 'cevreyolu', "Seferihisar'da 30 yıllık çevreyolu hayali gerçekleşti!")
    hero = 'https://paper.example/haber_resim/Seferihisar-da-30-yillik-cevreyolu.jpg'
    html = ('<meta property="og:image" content="https://paper.example/haber_resim/Seferihisar%2Dda%2D30%2Dyillik%2Dcevreyolu%2Ejpg">'
            + page(row, f'<img src="{hero}" alt="Açılış"><img src="https://paper.example/images/son.jpg" alt="">'))
    assert candidate_urls(html, row['url'], row, LOCAL) == [hero]


def test_own_photo_passes_as_a_photograph_when_its_topic_label_does_not(store, tmp_path, monkeypatch):
    # The live SeferihisarLife opening photo failed the `traffic` label.
    row = add(store, LOCAL, 'yol', 'Seferihisar çevre yolu hizmete açıldı')
    assert news_subjects(row)[0] == 'traffic'
    photos, _ = manager(store, tmp_path, monkeypatch, {row['url']: page(row, f'<img src="https://paper.example/u/a.jpg" alt="Açılış">')}, (LOCAL,))
    photos.fetcher.image.return_value = (jpeg(), 'https://paper.example/u/a.jpg')
    checks = []

    def check(data, expected):
        checks.append(expected)
        if expected != 'article_photo':
            raise MatchRejected('Wrong topic')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', check)
    monkeypatch.setattr('seferihisar.visual_match.validate_headline_photo', lambda *args: (_ for _ in ()).throw(MatchRejected('No banner')))
    assert photos.image(row) and checks == ['traffic', 'article_photo']
    assert json.loads(store.rows('SELECT payload FROM source_photos')[0]['payload'])['subject'] == 'traffic'


def test_a_graphic_still_fails_as_a_photograph(store, tmp_path, monkeypatch):
    row = add(store, LOCAL, 'yol', 'Seferihisar çevre yolu hizmete açıldı')
    photos, _ = manager(store, tmp_path, monkeypatch, {row['url']: page(row, f'<img src="https://paper.example/u/a.jpg" alt="Açılış">')}, (LOCAL,))
    photos.fetcher.image.return_value = (jpeg(), 'https://paper.example/u/a.jpg')

    def reject(*args):
        raise MatchRejected('Headline graphic')
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', reject)
    monkeypatch.setattr('seferihisar.visual_match.validate_headline_photo', reject)
    assert photos.image(row) is None and store.rows('SELECT * FROM source_photos') == []


def test_a_photo_credit_sits_under_the_source_and_never_reads_as_a_copy_change():
    caption = 'Başlık\n\nMetin\n\nKaynak: Yerel gazete\nhttps://paper.example/a\n\n#seferihisar'
    credited = photo_credit_caption(caption, 'Büyükşehir Belediyesi')
    assert credited == caption.replace('/a\n\n#', '/a\nFotoğraf: Büyükşehir Belediyesi\n\n#')
    assert without_photo_credit(credited) == caption
    assert photo_credit_caption(credited, None) == caption
    assert photo_credit_caption(credited, 'Başka Kaynak').count('Fotoğraf:') == 1
    assert photo_credit_caption('x' * 2195 + '\n\nKaynak: A', 'Büyükşehir Belediyesi').count('Fotoğraf:') == 0


def test_the_picture_takes_the_space_short_text_leaves(tmp_path):
    source = tmp_path / 'photo.jpg'
    source.write_bytes(jpeg())
    options = {'illustration': source, 'caption_note': True, 'source_photo': True}
    _, spare = _compose('Kısa başlık', LEAD, 'municipality', **options)
    assert 0 < spare
    _, left = _compose('Kısa başlık', LEAD, 'municipality', grow=min(spare, MAX_HERO_GROWTH), **options)
    assert left == spare - min(spare, MAX_HERO_GROWTH)
    _, full = _compose('Kısa başlık', ' '.join([LEAD, TUGAY]) * 3, 'municipality', **options)
    assert full < spare


def test_claimed_layouts_keep_their_bytes():
    assert filled_hero({'status': 'prepared'}) and filled_hero({'status': 'published', 'card_layout': VERSION})
    for layout in (FITTED, ONE_SCALE):
        assert not filled_hero({'status': 'published', 'card_layout': layout})
    assert not filled_hero({'status': 'published'})


@pytest.mark.parametrize('title', ["Seferihisar'da 30 yıllık çevreyolu hayali gerçekleşti!",
                                   'Trafiği rahatlatacak yol açıldı', 'Seferihisar’ın ulaşımında yeni bir dönem'])
def test_road_stories_show_a_road(title):
    assert news_subjects({'kind': 'news', 'category': 'municipality', 'title': title})[1] == 'traffic'


def test_a_general_municipal_story_gets_its_own_scene_not_a_desk():
    item = {'kind': 'news', 'category': 'municipality', 'title': 'Meclis üyesi yeni partiye katıldı'}
    assert news_subjects(item) == (None, None) and unclassified_news(item)
