"""Reviewed ASP template, explicit publication time and article-bound harvest photo."""
import json
from pathlib import Path

import pytest

from seferihisar.collect import structured, source_listing
from seferihisar.domain import parse_date
from seferihisar.editor import verify
from seferihisar.source_photos import candidate, news_subject
from seferihisar.visual_match import MatchRejected, validate_match

SOURCE = next(s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))
              if s['id'] == 'gercek-izmir')
URL = 'https://www.gercekizmir.com/haber/Seferihisar-Mandalinasinda-hasat-basladi/200950'
PHOTO = 'https://www.gercekizmir.com/haber_resim/hasat-200950.jpg'
TITLE = 'Seferihisar Mandalinası’nda hasat başladı'
SUMMARY = ('Seferihisar Belediye Başkan Vekili Fuat Gümüş, mandalina üreticileriyle '
           'Satsuma mandalinasının tanıtımı, pazarlanması ve üreticilere destek projelerini görüştü.')


def article(date='10/21/2026 09:42'):
    return (f'<link rel="canonical" href="{URL}"><meta property="og:image" content="{PHOTO}">'
            f'<meta name="t_omni_pubdate" content="{date}"><meta name="pub_date" content="20261021">'
            f'<div id="haberdetaybaslik"><h1>{TITLE}</h1><h2>{SUMMARY}</h2></div>'
            f'<div><img src="{PHOTO}" alt="{TITLE}"><span id="contextual"><p>{SUMMARY}</p>'
            '<p>Kasım sonunda bir şenlik yapılması da planlanıyor.</p></span></div>'
            '<aside><img src="https://www.gercekizmir.com/other.jpg">Yorumlar ve başka haberler</aside>')


def test_reviewed_template_keeps_exact_local_timestamp_summary_and_food_category():
    item, = structured(article(), URL, SOURCE)
    assert item['published_at'] == '2026-10-21T09:42:00+03:00'
    assert item['description'] == SUMMARY and item['category'] == 'food'
    assert item['url'] == URL and item['identity'] == URL
    assert verify(item, SOURCE, parse_date('2026-10-21T10:00:00+03:00')) is None
    assert candidate(article(), URL, item, SOURCE) == PHOTO
    assert news_subject(item) == 'citrus_harvest'


@pytest.mark.parametrize('date', ['', '20261021', '21/10/2026 09:42', '10/32/2026 09:42', '10/21/2026', '10/21/2026 27:42'])
def test_date_only_or_invalid_publication_time_never_borrows_the_current_day(date):
    assert structured(article(date), URL, SOURCE) == []


def test_conflicting_meta_times_are_held():
    body = article() + '<meta name="t_omni_pubdate" content="10/21/2026 10:42">'
    assert structured(body, URL, SOURCE) == []


def test_listing_only_follows_local_detail_pages_not_categories_ads_or_external_origins():
    from unittest.mock import Mock
    fetch = Mock()
    fetch.get.return_value = (f'<a href="{URL}">{TITLE}</a>'
                             '<a href="/haber/Buca-merkez/200949">Buca</a>'
                             '<a href="/kategori/Yerel/208">Seferihisar</a>'
                             '<a href="https://other.example/haber/a/200950">Seferihisar</a>', SOURCE['url'])
    # The real reviewed site uses root-relative links.
    fetch.get.return_value = (fetch.get.return_value[0].replace(URL, URL.replace(SOURCE['url'][:-1], '')),
                              SOURCE['url'])
    _, _, links = source_listing(SOURCE, fetch, SOURCE['url'])
    assert links == [URL]


@pytest.mark.parametrize('change', ['date', 'title', 'image_host', 'canonical'])
def test_harvest_photo_cannot_escape_article_identity_checks(change):
    item, = structured(article(), URL, SOURCE)
    html = article()
    if change == 'date': html = html.replace('10/21/2026 09:42', '10/20/2026 09:42')
    if change == 'title': html = html.replace(TITLE, 'Seferihisar’da farklı bir hasat başladı')
    if change == 'image_host': html = html.replace(PHOTO, 'https://other.example/hasat.jpg')
    if change == 'canonical': html = html.replace(f'href="{URL}"', 'href="https://www.gercekizmir.com/other"')
    with pytest.raises(ValueError): candidate(html, URL, item, SOURCE)


def test_future_harvest_notice_has_no_incident_photo_and_harvest_is_never_generated():
    assert news_subject({'kind': 'news', 'source_id':'gercek-izmir', 'title': 'Seferihisar mandalina hasadı başlayacak'}) is None
    assert news_subject({'kind': 'news', 'source_id':'other', 'title':TITLE}) == 'citrus_harvest'
    with pytest.raises(MatchRejected): validate_match(b'', 'citrus_harvest')
