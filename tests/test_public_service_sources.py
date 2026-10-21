"""Reviewed official templates: public fields, bounded links and dated local facts."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.collect import collect_source, source_listing, structured
from seferihisar.domain import local, parse_date
from seferihisar.editor import verify

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
CATALOG = {s['id']: s for s in json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))}
BODY = 'Seferihisar ilçesinde kurumun yeni hizmetleri ve çalışmalarına ilişkin açıklama yapıldı.'


def article(key, date=None, title='Seferihisar hizmet duyurusu'):
    if key == 'izmir-tarim':
        return (f'<h3 class="page-title">{title}</h3><span class="itemDateCreated">{date or "21.10.2026 /"}</span>'
                f'<div id="th-content-post"><div>{BODY}</div></div>')
    if key == 'izmir-orman':
        return (f'<div class="ogm-news-content"><h1>{title}</h1></div><span class="haber-tarih">{date or "21.10.2026"}</span>'
                f'<div id="x_ControlWrapper_RichHtmlField"><p>{BODY}</p></div>')
    return (f'<div class="page-content-header"><h5>{title}</h5></div>'
            f'<span class="update-date"><b></b>{date or "21 Ekim 2026"}</span><div id="div_print"><p>{BODY}</p></div>')


def url(key):
    return SOURCES[key]['url'].rstrip('/') + {'izmir-tarim': '/Haber/1225/Seferihisar-hizmet',
        'izmir-orman': '/haberler/seferihisar-hizmet', 'izmir-saglik': '/TR-395800/seferihisar-hizmet.html'}[key]


@pytest.mark.parametrize('key', ['izmir-tarim', 'izmir-orman', 'izmir-saglik'])
def test_real_template_fields_are_used_instead_of_sidebar_or_template_dates(key):
    page = article(key) + '<aside><time datetime="2026-10-22">Başka haber</time></aside>'
    page += '<script type="application/ld+json">' + json.dumps({'@type': 'NewsArticle',
        'headline': 'Seferihisar başka haber', 'description': 'Seferihisar menü haber metni',
        'datePublished': '2026-10-22'}) + '</script>'
    item, = structured(page, url(key), SOURCES[key])
    assert item['published_at'] == '2026-10-21T00:00:00+03:00'
    assert item['title'] == 'Seferihisar hizmet duyurusu' and item['description'] == BODY
    assert verify(item, SOURCES[key], parse_date('2026-10-21T13:30:00+03:00')) is None


@pytest.mark.parametrize('key', ['izmir-tarim', 'izmir-orman', 'izmir-saglik'])
@pytest.mark.parametrize('change', ['missing_date', 'conflicting_date', 'missing_body', 'missing_title'])
def test_changed_official_template_cannot_silently_borrow_fallback_fields(key, change):
    from bs4 import BeautifulSoup
    source = SOURCES[key]
    soup = BeautifulSoup(article(key), 'html.parser')
    if change == 'missing_date': soup.select_one(source['published_date_selector']).decompose()
    if change == 'conflicting_date': soup.append(BeautifulSoup(article(key, '20.10.2026 /' if key == 'izmir-tarim' else '20.10.2026' if key == 'izmir-orman' else '20 Ekim 2026'), 'html.parser'))
    if change == 'missing_body': soup.select_one(source['article_selector']).decompose()
    if change == 'missing_title': soup.select_one(source['title_selector']).decompose()
    soup.append(BeautifulSoup('<article><p>Seferihisar yedek şablon metni ve güncel menü.</p></article><h1>Yan menü</h1><time datetime="2026-10-21"></time>', 'html.parser'))
    with pytest.raises(ValueError, match='Reviewed article fields missing'):
        structured(str(soup), url(key), source)


@pytest.mark.parametrize('date', ['21.10 /', '21.10.2026', '32.10.2026 /', '21.10.2026 / 20.10.2026'])
def test_tarim_date_field_never_guesses_year_or_invalid_format(date):
    with pytest.raises(ValueError): structured(article('izmir-tarim', date), url('izmir-tarim'), SOURCES['izmir-tarim'])


def test_old_health_banner_keeps_old_date_and_cannot_republish_as_today():
    item, = structured(article('izmir-saglik', '05 Aralık 2025'), url('izmir-saglik'), SOURCES['izmir-saglik'])
    assert item['published_at'] == '2025-12-05T00:00:00+03:00'
    assert verify(item, SOURCES['izmir-saglik'], parse_date('2026-10-21T13:30:00+03:00')) == 'outdated_or_missing_date'


def test_unrelated_body_cannot_borrow_seferihisar_from_navigation():
    page = article('izmir-orman', title='Manisa değerlendirme toplantısı').replace(BODY, 'Manisa ilinde yönetim toplantısı yapılarak kurum içi çalışmalar değerlendirildi.')
    assert structured(page + '<footer>Seferihisar yangın</footer>', url('izmir-orman'), SOURCES['izmir-orman']) == []


def test_ogm_public_literal_links_are_decoded_but_javascript_is_never_executed():
    source = SOURCES['izmir-orman']
    page = '''<script>ReactDOM.render(View,{initialState:{items:[
    {Link:"/izmirobm/haberler/seferihisar-yangin"},
    {Link:"\\/izmirobm\\/haberler\\/seferihisar-yangin"},
    {Link:"https://other.example/izmirobm/haberler/seferihisar"},
    {Link:"/izmirobm/haberler/../admin"},
    {Link:"/izmirobm/haberler/other?access_token=private"},
    {Link:fetch("https://other.example/")}]}})</script>'''
    fetch = Mock(); fetch.get.return_value = page, source['url']
    _, _, links = source_listing(source, fetch, source['url'])
    assert links == ['https://www.ogm.gov.tr/izmirobm/haberler/seferihisar-yangin']
    fetch.get.assert_called_once_with(source['url'])
    fetch.get.return_value = page, 'https://other.example/izmirobm'
    with pytest.raises(ValueError, match='Unapproved embedded view origin'):
        source_listing(source, fetch, source['url'])


def test_ogm_collection_has_one_shared_detail_budget_even_with_many_links():
    source = SOURCES['izmir-orman']
    page = '<script>' + ','.join(f'{{Link:"/izmirobm/haberler/seferihisar-{i}"}}' for i in range(20)) + '</script>'
    fetch = Mock(); fetch.get.side_effect = [(page, source['url'])] + [(article(source['id']), source['url'] + f'/haberler/seferihisar-{i}') for i in range(3)]
    items, _, errors = collect_source(source, fetch, [])
    assert len(items) == 3 and not errors and fetch.get.call_count == 4


def test_health_empty_anchor_uses_reviewed_visible_title_attribute_only_for_important_local_links():
    source = SOURCES['izmir-saglik']
    page = '''<div class="slider-desc-center">
    <a href="/TR-369079/guzelbahcede-merkez-52.html" title="Güzelbahçe’de Acil Sağlık Hizmetleri İstasyonu açıldı"></a>
    <a href="/TR-369080/buca-acil.html" title="Buca Acil Sağlık Hizmetleri İstasyonu açıldı"></a>
    <a href="/TR-369081/urla-ziyareti.html" title="Urla müdür ziyareti"></a></div>'''
    fetch = Mock(); fetch.get.return_value = page, source['url']
    _, _, links = source_listing(source, fetch, source['url'])
    assert links == ['https://izmirism.saglik.gov.tr/TR-369079/guzelbahcede-merkez-52.html']
    assert local('Urla aile sağlığı merkezi açıldı')
    assert not local('Urla sağlık hizmetleri toplantısı')


def test_eczaci_403_is_catalogued_without_an_active_reader():
    assert 'izmir-eczaci' not in SOURCES
    assert CATALOG['izmir-eczaci']['status'] == 'access_failed'
    assert '403' in CATALOG['izmir-eczaci']['note']
