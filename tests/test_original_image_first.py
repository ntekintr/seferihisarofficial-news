"""12 Nov: scenes replaced real pictures the publishers had on their own articles.

Isparta and Seferihisar news whose page showed a headline banner, a portrait or
a photograph on the publisher's image host went out with a generated scene.
A scene is now generated only when the article itself shows no picture.
"""
import io
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from test_real_photo_first import AT, LOCAL, add, jpeg, manager, page, store  # noqa: F401
from seferihisar.illustrations import Illustrator, clean_image
from seferihisar.image_safety import validate_jpeg
from seferihisar.pipeline import _export
from seferihisar.schedule import queue_item
from seferihisar.source_photos import NoArticleImage, candidate_urls
from seferihisar.visual_policy import image_reason

OWN = 'https://paper.example/u/a.jpg'
TITLE = 'Seferihisar çevre yolu hizmete açıldı'


def draft(store, row):
    queue_item(store, row, 'news', AT, AT)
    return next(post for post in store.posts() if post.get('item_id') == row['id'])


def checked(store, tmp_path, monkeypatch, html, at=AT):
    row = next(iter(store.items()), None) or add(store, LOCAL, 'yol', TITLE)
    photos, fetcher = manager(store, tmp_path, monkeypatch, {row['url']: html(row)}, (LOCAL,))
    photos.at = at
    fetcher.image.return_value = (jpeg(), OWN)
    post = next((p for p in store.posts() if p.get('item_id') == row['id']), None) or draft(store, row)
    return photos, fetcher, row, post


def test_an_article_without_a_picture_may_get_a_scene_and_is_not_read_again_for_hours(store, tmp_path, monkeypatch):
    photos, fetcher, row, post = checked(store, tmp_path, monkeypatch, page)
    assert photos.for_post(post, {row['id']: row}) == {}
    assert not photos.awaits_original(post, {row['id']: row})
    assert store.rows('SELECT stage FROM source_photo_retries')[0]['stage'] == 'no_image'
    later, fetcher, row, post = checked(store, tmp_path, monkeypatch, page, AT + timedelta(minutes=30))
    assert later.for_post(post, {row['id']: row}) == {}
    assert not later.awaits_original(post, {row['id']: row})
    fetcher.get.assert_not_called()


@pytest.mark.parametrize('case', ['too_small', 'unreviewed_host', 'unreadable_page', 'unreadable_image', 'deferred'])
def test_a_scene_waits_while_the_article_may_show_its_own_picture(store, tmp_path, monkeypatch, case):
    address = 'https://cdn.example/u/a.jpg' if case == 'unreviewed_host' else OWN
    photos, fetcher, row, post = checked(store, tmp_path, monkeypatch,
                                         lambda row: page(row, f'<img src="{address}" alt="Açılış">'))
    if case == 'too_small':
        fetcher.image.return_value = (jpeg(size=(120, 90)), OWN)
    elif case == 'unreadable_page':
        fetcher.get.side_effect = requests.Timeout('offline')
    elif case == 'unreadable_image':
        fetcher.image.side_effect = requests.Timeout('offline')
    elif case == 'deferred':
        monkeypatch.setattr('seferihisar.source_photos.MAX_SOURCE_CHECKS', 0)
    assert photos.for_post(post, {row['id']: row}) == {}
    assert photos.awaits_original(post, {row['id']: row})
    if case != 'deferred':
        # The cooldown of a failed check is no proof that the article shows nothing.
        later, _, row, post = checked(store, tmp_path, monkeypatch, page, AT + timedelta(minutes=5))
        assert later.for_post(post, {row['id']: row}) == {} and later.stats['cooldown'] == 1
        assert later.awaits_original(post, {row['id']: row})


def test_an_event_or_an_unread_source_keeps_its_scene(store, tmp_path, monkeypatch):
    photos, _, row, post = checked(store, tmp_path, monkeypatch, page)
    outsider = {**row, 'id': 'c' * 24, 'source_id': 'not-a-photo-source'}
    assert photos.for_post({**post, 'item_id': outsider['id']}, {outsider['id']: outsider}) == {}
    assert not photos.awaits_original({**post, 'item_id': outsider['id']}, {outsider['id']: outsider})


def test_a_video_layout_offers_its_own_opengraph_picture(store):
    row = add(store, LOCAL, 'yol', TITLE)
    identity = page(row).split('<article>')[0]
    video = identity + f'<meta property="og:image" content="{OWN}"><h1>{TITLE}</h1><iframe src="/embed/1"></iframe>'
    assert candidate_urls(video, row['url'], row, LOCAL) == [OWN]
    with pytest.raises(NoArticleImage):
        candidate_urls(identity + f'<h1>{TITLE}</h1>', row['url'], row, LOCAL)
    for address in ('https://cdn.example/u/a.jpg', 'https://paper.example/assets/logo.png'):
        unusable = identity + f'<meta property="og:image" content="{address}"><h1>{TITLE}</h1>'
        with pytest.raises(ValueError) as refusal:
            candidate_urls(unusable, row['url'], row, LOCAL)
        assert not isinstance(refusal.value, NoArticleImage)


def test_share_icons_and_logos_are_not_the_articles_picture(store):
    row = add(store, LOCAL, 'yol', TITLE)
    icons = ('<img src="https://cdn.example/icons/share.svg" alt="Paylaş">'
             '<img src="https://cdn.example/site-logo.png" alt="Gazete">'
             '<a href="https://paper.example/baska"><img src="https://cdn.example/u/other.jpg" alt="Diğer haber"></a>')
    with pytest.raises(NoArticleImage):
        candidate_urls(page(row, icons), row['url'], row, LOCAL)


@pytest.fixture
def scenes(monkeypatch):
    monkeypatch.setattr(Illustrator, '_reuse_scene', lambda *args: None)
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'SYNTHETIC_CLOUDFLARE_CREDENTIAL_0123456789')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.illustrations.validate_match', lambda data, expected: {})
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration', validate_jpeg)
    image = io.BytesIO()
    Image.new('RGB', (512, 512), '#346175').save(image, 'PNG')
    generate = Mock(return_value=clean_image(image.getvalue()))
    monkeypatch.setattr('seferihisar.illustrations.Illustrator.generate', generate)
    return generate


@pytest.mark.parametrize('picture,generated', [('', 1), (f'<img src="{OWN}" alt="Açılış">', 0)])
def test_research_generates_a_scene_only_for_an_article_without_a_picture(store, tmp_path, monkeypatch, scenes, picture, generated):
    row = add(store, LOCAL, 'yol', TITLE)
    draft(store, row)
    fetcher = Mock()
    fetcher.get.return_value = (page(row, picture), row['url'])
    # The article's picture is there but cannot be shown: the draft waits for it.
    fetcher.image.return_value = (jpeg(size=(120, 90)), OWN)
    monkeypatch.setattr('seferihisar.source_photos.Fetcher', lambda sources: fetcher)
    _export(store, tmp_path / 'research', [LOCAL], AT)
    post = store.posts()[0]
    assert scenes.call_count == generated and bool(post['illustration_keys']) == bool(generated)
    assert not post.get('source_photo_keys')
    assert image_reason(post) == (None if generated else 'awaiting_content_visual')


def test_a_scene_already_drawn_gives_way_to_the_articles_own_picture(store, tmp_path, monkeypatch, scenes):
    row = add(store, LOCAL, 'yol', TITLE)
    draft(store, row)
    fetcher = Mock()
    fetcher.get.return_value = (page(row), row['url'])
    monkeypatch.setattr('seferihisar.source_photos.Fetcher', lambda sources: fetcher)
    monkeypatch.setattr('seferihisar.source_photos.validate_news_photo', Mock(side_effect=ValueError('Headline graphic')))
    _export(store, tmp_path / 'first', [LOCAL], AT)
    assert store.posts()[0]['illustration_keys']
    # Seven hours on the publisher has added its banner graphic to the article.
    fetcher.get.return_value = (page(row, f'<img src="{OWN}" alt="Açılış">'), row['url'])
    fetcher.image.return_value = (jpeg(), OWN)
    _export(store, tmp_path / 'second', [LOCAL], AT + timedelta(hours=7))
    post = store.posts()[0]
    assert post['source_photo_keys'] and not post['illustration_keys'] and scenes.call_count == 1
    assert image_reason(post) is None
