"""24 Nov 2026 source review: wider Gündem feed, two local papers, @shisarbel,
and two out-of-district readers retired (owner rule: Seferihisar only)."""
import json
from pathlib import Path

import pytest

from seferihisar.collect import Fetcher, collect_source, feed_items, structured
from seferihisar.domain import parse_date
from seferihisar.editor import verify
from seferihisar.instagram_sources import instagram_sources, username
from seferihisar.source_catalog import public_catalog

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
CATALOG = {e['id']: e for e in json.loads(Path('config/source_catalog.json').read_text(encoding='utf-8'))}
AT = parse_date('2026-11-24T12:00:00+03:00')


def rss(*items):
    body = ''.join(f'''<item><title><![CDATA[{title}]]></title><link>{link}</link>
      <atom:link rel="self" href="{link}" type="application/rss+xml"/>
      <description><![CDATA[{description}]]></description>
      <pubDate>{date}</pubDate></item>''' for title, link, description, date in items)
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" '
            'xmlns:atom="http://www.w3.org/2005/Atom"><channel><title>t</title>' + body + '</channel></rss>')


def article(title, author, published, description):
    data = {'@context': 'https://schema.org', '@type': 'NewsArticle', 'headline': title,
            'datePublished': published, 'description': description,
            'author': {'@type': 'Organization', 'name': author}}
    return (f'<html><head><meta name="author" content="{author}">'
            f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script></head>'
            f'<body><article><h1>{title}</h1><p>{description}</p></article></body></html>')


class Pages:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        return self.pages[url], url


def test_gundem_keeps_its_identity_and_reads_every_category():
    gundem = SOURCES['seferihisar-gundem']
    assert gundem['url'] == 'https://www.seferihisargundem.com/rss.xml'
    assert gundem['enabled'] and gundem['kind'] == 'rss' and gundem['follow_feed_details'] is False
    # The Instagram profile's web fallback still names the same reader.
    assert CATALOG['instagram-gundem']['fallback_reader_ids'] == ['seferihisar-gundem']


def test_gundem_general_feed_drops_izmir_metropolitan_bulletins():
    feed = rss(
        ('İzmir’in 2027 bütçesinde dev yatırım atağı', 'https://www.seferihisargundem.com/butce/1/',
         'Büyükşehir Belediyesi 2027 bütçesini meclise sundu. Kent genelinde ulaşım ve altyapı yatırımları öne çıktı.',
         'Tue, 24 Nov 2026 09:00:00 +0300'),
        ('İzmir Oda Orkestrası konserine yoğun ilgi', 'https://www.seferihisargundem.com/orkestra/2/',
         'Büyükşehir’in orkestrası Ahmed Adnan Saygun Sanat Merkezi’nde sahne aldı.',
         'Thu, 19 Nov 2026 20:00:00 +0300'),
        ('Seferihisar’da çocukların günü; 3. Teos Çocuk Festivali başlıyor', 'https://www.seferihisargundem.com/teos/3/',
         'Belediye, Dünya Çocuk Hakları Günü için atölye ve gösterilerle dolu bir festival hazırladı.',
         'Thu, 19 Nov 2026 15:20:00 +0300'))
    items = feed_items(feed, 'https://www.seferihisargundem.com/', SOURCES['seferihisar-gundem'])
    assert [i['url'] for i in items] == ['https://www.seferihisargundem.com/teos/3/']


@pytest.mark.parametrize('sid,url', [
    ('egede-son-soz', 'https://www.egedesonsoz.com/rss/seferihisar-haberleri'),
    ('iz-gazete', 'https://www.izgazete.net/rss/seferihisar')])
def test_new_local_papers_match_existing_local_press_readers(sid, url):
    source, peer = SOURCES[sid], SOURCES['ege-telgraf']
    assert source['url'] == url
    for key in ('kind', 'enabled', 'trusted', 'access'):
        assert source[key] == peer[key] == SOURCES['seferihisar-life'][key]
    assert source.get('follow_feed_details', True)  # bylines and dates come from the article page
    assert CATALOG[sid]['group'] == CATALOG['seferihisar-life']['group'] == 'yerel_basın'
    assert CATALOG[sid]['status'] == 'connected'


def test_general_ege_feed_address_is_not_used():
    # /rss/seferihisar returns the paper's general feed; only the category feed is reviewed.
    assert not any(s['url'].rstrip('/').endswith('egedesonsoz.com/rss/seferihisar') for s in SOURCES.values())


def press_item(source_id, title, description, published='2026-11-23T13:28:00+03:00'):
    source = SOURCES[source_id]
    host = source['url'].split('/')[2]
    url = f'https://{host}/haber-{len(title)}'
    return {'kind': 'news', 'title': title, 'description': description, 'url': url, 'identity': url,
            'source_id': source_id, 'source_name': source['name'], 'category': 'news',
            'published_at': published, 'sources': [url]}


@pytest.mark.parametrize('title,description', [
    ("Tugay'dan Seferihisar'da Cumhur İttifakı turu", 'Ziyaret sırasında esnafla görüşüldü ve ilçedeki projeler anlatıldı.'),
    ("Sayıştay'dan Seferihisar'a mercek: tarifeler 2013'te kaldı", 'Rapora göre belediyenin bazı vergi ve harç tarifeleri güncellenmedi.'),
    ('Seferihisar’da inşaat krizi… İşçiler: Tehdit ediliyoruz', 'Bademler’deki bir şantiyede çalışan işçiler alacaklarını alamadıklarını söyledi.'),
    ("Orhanlı'da jeotermal davasında yeni duruşma", 'Köylüler Seferihisar Orhanlı’daki projeye karşı açtıkları süreci sürdürüyor.'),
    ("Seferihisar'da GES projesine itiraz", 'Mahalle sakinleri Seferihisar’daki güneş enerjisi santrali planına karşı dilekçe verdi.')])
def test_political_and_legal_local_press_stories_wait_for_a_human(title, description):
    assert verify(press_item('egede-son-soz', title, description), SOURCES['egede-son-soz'], AT) == 'human_review_required'


def test_ordinary_local_press_story_is_still_accepted():
    item = press_item('egede-son-soz', 'Seferihisar mandalinası Kültürpark’ta: Üreticiye verilen söz tutuldu',
                      'Seferihisar’ın tescilli mandalinası Kültürpark’taki satış noktasında üreticiden doğrudan satılmaya başlandı.')
    assert verify(item, SOURCES['egede-son-soz'], AT) is None
    assert verify({**item, 'title': 'Seferihisar Belediyesi davet ediyor: Zeytin hasat şenliği'},
                  SOURCES['egede-son-soz'], AT) is None


FEED = 'https://www.izgazete.net/rss/seferihisar'
BULLETIN = 'https://www.izgazete.net/seferihisarda-3-teos-cocuk-festivali-duzenlendi'
SPORT = 'https://www.izgazete.net/seferihisara-spor-tesisi-yatirimi-ihale-24-kasimda-yapilacak'
REPORTED = 'https://www.izgazete.net/seferihisarli-antrenor-milli-gorev'


def iz_pages():
    return {
        FEED: rss(("Seferihisar'da 3. TEOS Çocuk Festivali düzenlendi!", BULLETIN,
                   'Seferihisar’da Dünya Çocuk Hakları Günü festivalinde çocuklar atölyelerle buluştu.',
                   'Fri, 20 Nov 2026 23:10:00 +0300'),
                  ('Seferihisar’a spor tesisi yatırımı: İhale 24 Kasım’da', SPORT,
                   'Seferihisar Belediyesi spor tesisi için ihale tarihini açıkladı.',
                   'Wed, 18 Nov 2026 10:29:00 +0300'),
                  ('Seferihisarlı antrenör millî takımda görev aldı', REPORTED,
                   'Seferihisar’da çalışan antrenör millî takımın teknik ekibine seçildi.',
                   'Mon, 23 Nov 2026 17:30:00 +0300')),
        BULLETIN: article("Seferihisar'da 3. TEOS Çocuk Festivali düzenlendi!", 'SEFERİHİSAR BELEDİYESİ BÜLTEN',
                          '2026-11-20T23:10:00+03:00', 'Seferihisar’da Dünya Çocuk Hakları Günü festivalinde çocuklar atölyelerle buluştu.'),
        SPORT: article('Seferihisar’a spor tesisi yatırımı: İhale 24 Kasım’da', 'SEFERİHİSAR BELEDİYE BÜLTENİ',
                       '2026-11-18T10:29:00+03:00', 'Seferihisar Belediyesi spor tesisi için ihale tarihini açıkladı.'),
        REPORTED: article('Seferihisarlı antrenör millî takımda görev aldı', 'Ozan Ekiz',
                          '2026-11-23T17:30:00+03:00', 'Seferihisar’da çalışan antrenör millî takımın teknik ekibine seçildi.'),
    }


def test_iz_gazete_drops_labelled_municipal_bulletin_copies_and_their_feed_entries():
    fetcher = Pages(iz_pages())
    items, _, errors = collect_source(SOURCES['iz-gazete'], fetcher, [])
    assert not errors
    assert [i['url'] for i in items] == [REPORTED]
    assert items[0]['published_at'] == '2026-11-23T17:30:00+03:00'
    assert fetcher.calls[0] == FEED and set(fetcher.calls[1:]) == {BULLETIN, SPORT, REPORTED}


def test_bulletin_byline_rule_is_only_for_the_reviewed_paper():
    pages = iz_pages()
    assert structured(pages[BULLETIN], BULLETIN, SOURCES['iz-gazete']) == []
    # Without the reviewed rule (every other source), the same page is a normal article.
    plain = {k: v for k, v in SOURCES['iz-gazete'].items() if k != 'republished_bulletin_author'}
    assert [i['url'] for i in structured(pages[BULLETIN], BULLETIN, plain)] == [BULLETIN]
    # Body text naming the bulletin is not a byline.
    reporter = pages[REPORTED].replace('</p>', ' Kaynak: Seferihisar Belediyesi bülteni.</p>')
    assert [i['url'] for i in structured(reporter, REPORTED, SOURCES['iz-gazete'])] == [REPORTED]


def test_unread_detail_page_never_falls_back_to_the_feed_entry():
    pages = iz_pages()

    class Failing(Pages):
        def get(self, url):
            if url == BULLETIN:
                raise ValueError('robots.txt disallows this path')
            return super().get(url)
    items, _, errors = collect_source(SOURCES['iz-gazete'], Failing(pages), [])
    assert BULLETIN not in {i['url'] for i in items} and errors


def test_shisarbel_is_read_like_the_other_instagram_sources():
    source, peer = SOURCES['instagram-seferihisar-belediye'], SOURCES['instagram-life']
    assert {k for k in source} == {k for k in peer}
    assert username(source) == 'shisarbel' and source['verified_profile_link'] == 'https://seferihisar.bel.tr/'
    assert source in instagram_sources(SOURCES.values())
    # The web crawler never gains Instagram as a host.
    assert 'www.instagram.com' not in Fetcher(list(SOURCES.values())).hosts


@pytest.mark.parametrize('sid', ['instagram-urla', 'rotary2440'])
def test_out_of_district_readers_are_disabled_not_deleted(sid, at):
    source = SOURCES[sid]
    assert source['enabled'] is False and source['trusted'] is True
    assert source not in instagram_sources(SOURCES.values())
    assert verify({'kind': 'news', 'title': 'Seferihisar'}, source, at) == 'unverified_source'
    entry = CATALOG[sid]
    assert entry['status'] == 'retired' and '24 Kasım 2026' in entry['note']
    check = {'source_id': sid, 'checked_at': at.isoformat(), 'status': 'ok', 'parsed': 1, 'accepted': 1, 'error_count': 0}
    shown = public_catalog([entry], [source], [check], at)[0]
    assert shown['status'] == 'retired' and shown['note'] == entry['note']


def test_rotary_host_is_no_longer_crawled():
    assert 'rotary2440.org' not in Fetcher(list(SOURCES.values())).hosts
