"""Owner rule, 22 Nov 2026: power cuts and theatre only when in Seferihisar.

Evidence from the state of 22 Nov 2026: GDZ cuts of Urla, Güzelbahçe and
Özdere went out as stories (e.g. 21 Nov "Urla · Altıntaş, Yaka"), and plays at
Urla Hakan Çeken Kültür Merkezi and Bademler Sanat Köyü went out as feeds.
"""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from seferihisar import district
from seferihisar.domain import digest, parse_date
from seferihisar.editor import verify
from seferihisar.instagram import publish_outage_story
from seferihisar.operations import failed, safe_result
from seferihisar.publication_policy import post_reason
from seferihisar.schedule import prepare, queue_item
from seferihisar.source_readers import gdz_planned_items
from tests.test_automatic_publication import api

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
AT = parse_date('2026-11-22T10:00:00+03:00')
SITE = 'https://example.org/'


def gdz(district_name, neighbourhoods):
    row = {'Kesinti_ID': '4000001', 'Durum': 'Planlandı', 'Sehir': 'İZMİR', 'Ilce': district_name,
           'Mahalle': neighbourhoods, 'MahalleSokak': [], 'Kesinti_Nedeni': 'Şebeke Bakım Çalışması',
           'Planlanan_Baslangic_Zamani': '2026-11-22T11:00:00'.replace('T', ' '),
           'Planlanan_Sona_Erme_Zamani': '2026-11-22 16:00:00'}
    body = json.dumps({'success': True, 'level': 'district_outages', 'city': 'İZMİR',
                       'district': district_name, 'data': [row], 'count': 1})
    return gdz_planned_items(body, SOURCES['gdz']['url'], SOURCES['gdz'], district_name, AT)


@pytest.mark.parametrize('name,neighbourhoods,expected', [
    ('SEFERİHİSAR', ['Beyler', 'Çolak İbrahim Bey', 'Turabiye'], None),
    ('SEFERİHİSAR', ['Payamlı'], None),
    ('URLA', ['Altıntaş', 'Yaka'], 'outage_outside_district'),
    ('GÜZELBAHÇE', ['Yalı'], 'outage_outside_district'),
    # A Seferihisar neighbourhood name does not make another district's cut local.
    ('GÜZELBAHÇE', ['Payamlı'], 'outage_outside_district'),
    ('MENDERES', ['Çukuraltı', 'Orta'], 'outage_outside_district'),
])
def test_gdz_cut_is_published_only_for_the_seferihisar_district(name, neighbourhoods, expected):
    [item] = gdz(name, neighbourhoods)
    assert district.reason(item) == expected
    assert verify(item, SOURCES['gdz'], AT) == expected


def play(location, url='https://biletinial.com/tr-tr/tiyatro/ornek-oyun', category='theatre', **extra):
    start = AT + timedelta(days=3)
    return {'kind': 'event', 'title': 'Örnek Oyun', 'description': 'Etkinlik duyurusu. Tek perdelik oyun.',
            'url': url, 'identity': url, 'sources': [url], 'source_id': 'biletinial', 'source_name': 'Biletinial',
            'category': category, 'start': start.isoformat(), 'end': (start + timedelta(hours=2)).isoformat(),
            'time_known': True, 'location': location, 'organizer': None, 'free': None, 'price': None,
            'currency': None, 'ticket_url': url, 'status': 'scheduled', 'previous_start': None, **extra}


@pytest.mark.parametrize('location,expected', [
    ('Anart - Gösteri ve Sanat Evi · Turabiye Mah. 25.Sokak No2 / Seferihisar - İzmir', None),
    ('Seferihisar Çağan Irmak Kültür Merkezi Hıdırlık Mahallesi 11 Eylül CAD. No:4/c Seferihisar İzmir', None),
    ('Teos Antik Tiyatrosu', None),
    ('Sığacık Kalesi Açık Hava Sahnesi', None),
    ('Kültür Evi · Adnan Menderes Cad. No:5 Seferihisar/İzmir', None),
    ('Urla Hakan Çeken Kültür Merkezi · Yenikent, 75. Yıl Cumhuriyet Cd. 94 A, 35430 Urla/İzmir', 'theatre_outside_district'),
    ('Bademler Sanat Köyü Bademler mahallesi no:8 bademler caddesi Urla-İzmir İzmir İzmir', 'theatre_outside_district'),
    ('Academico Güzelbahçe  İzmir İzmir', 'theatre_outside_district'),
    # 22 Nov 2026 state: a touring show's Ankara session passed `local` on "Doğanbey".
    ('CSO ADA ANKARA Bankkart Mavi Salon Doğanbey Mahallesi, Talatpaşa Blv No:38, 06050 Altındağ/Ankara', 'theatre_outside_district'),
    ('Seferihisar ve Urla ortak sahnesi', 'theatre_outside_district'),
    ('Kültür Merkezi İzmir', 'theatre_location_unconfirmed'),
    ('', 'theatre_location_unconfirmed'),
])
def test_theatre_is_published_only_at_a_seferihisar_venue(location, expected):
    assert district.reason(play(location)) == expected


def test_venue_not_the_blurb_decides():
    item = play('Urla Atatürk Kültür Merkezi  İzmir İzmir',
                description='Seferihisar’da da sahnelenen oyun şimdi burada.')
    assert district.reason(item) == 'theatre_outside_district'


@pytest.mark.parametrize('changes', [
    {'category': 'family', 'title': 'BÖCEK OTELİ', 'description': 'Çocuk Oyunu'},
    {'category': 'event', 'title': 'Bir Adamla İlişkiler', 'description': 'İnteraktif oyun gecesi.'},
    {'category': 'festival', 'url': 'https://example.org/etkinlik/1', 'ticket_url': None,
     'description': 'Gerçek çocuk tiyatrosu.'},
])
def test_stage_shows_of_other_categories_follow_the_theatre_rule(changes):
    assert district.reason(play('Urla AKM Fuaye Sahnesi Sıra Mahallesi Urla / İZMİR', **changes)) == 'theatre_outside_district'
    assert district.reason(play('Seferihisar Çağan Irmak Kültür Merkezi', **changes)) is None


def test_other_nearby_content_keeps_the_existing_rule():
    concert = play('Urla Hakan Çeken Kültür Merkezi', url='https://example.org/konser',
                   category='concert', ticket_url=None, description='Açık hava konseri.')
    assert district.reason(concert) is None


def notice(description, title='Planlı elektrik kesintisi duyurusu'):
    return {'kind': 'news', 'category': 'outage', 'title': title, 'description': description,
            'url': 'https://www.instagram.com/p/EXAMPLE1/', 'published_at': AT.isoformat()}


def test_multi_district_notice_keeps_only_the_seferihisar_lines():
    item = district.scope(notice('Yarın 09:00-17:00 arası planlı kesinti yapılacak.\n'
                                 'Seferihisar: Sığacık, Akarca\nUrla: Altıntaş, Yaka\nGüzelbahçe: Yalı'))
    assert item['description'] == 'Yarın 09:00-17:00 arası planlı kesinti yapılacak.\nSeferihisar: Sığacık, Akarca'
    assert district.reason(item) is None


@pytest.mark.parametrize('description,title,expected', [
    ('Urla: Altıntaş\nGüzelbahçe: Yalı', 'Planlı elektrik kesintisi duyurusu', 'outage_outside_district'),
    ('Seferihisar, Urla ve Güzelbahçe’de elektrik kesintisi olacak.', 'Planlı elektrik kesintisi duyurusu', 'outage_mixed_districts'),
    ('Seferihisar: Sığacık', 'Urla ve Seferihisar’da elektrik kesintisi', 'outage_mixed_districts'),
    ('Kesinti duyurusu.', 'İzmir’de elektrik kesintisi', 'outage_outside_district'),
])
def test_notice_that_cannot_be_split_or_has_no_seferihisar_line_is_withheld(description, title, expected):
    assert district.reason(district.scope(notice(description, title))) == expected


def test_non_notice_news_in_outage_category_is_not_touched():
    item = {'kind': 'news', 'category': 'outage', 'title': 'Seferihisar ve Urla’ya elektrikli otobüs',
            'description': 'Yeni hat açıldı.'}
    assert district.reason(item) is None and district.scope(item) is item


def outage_event(store, place, neighbourhoods):
    [item] = gdz({'Seferihisar': 'SEFERİHİSAR', 'Urla': 'URLA'}[place], neighbourhoods)
    item['identity'] = item['url'] + '#' + place
    key, _ = store.upsert(item, AT.isoformat())
    return next(i for i in store.items() if i['id'] == key)


def test_queued_cards_of_other_districts_are_held_with_a_reason(store):
    """Cards queued before this rule are re-evaluated on every run, state untouched by hand."""
    urla = outage_event(store, 'Urla', ['Altıntaş', 'Yaka'])
    local = outage_event(store, 'Seferihisar', ['Sığacık'])
    queue_item(store, urla, 'announcement', AT, AT)  # as the old code queued it
    prepare(store, AT)
    status = {p['item_id']: p['status'] for p in store.posts() if not p.get('publish_format')}
    assert status == {urla['id']: 'blocked_source', local['id']: 'prepared'}
    held = next(p for p in store.posts() if p['item_id'] == urla['id'])
    reason = store.rows('SELECT reason FROM withheld WHERE id=?', (digest(held['id']),))
    assert reason and reason[0]['reason'] == 'outage_outside_district'
    assert post_reason(store, held, AT) == 'outage_outside_district'
    # A later run does not release it.
    prepare(store, AT + timedelta(minutes=5))
    assert next(p for p in store.posts() if p['id'] == held['id'])['status'] == 'blocked_source'


def test_only_the_seferihisar_cut_reaches_the_story(store):
    urla = outage_event(store, 'Urla', ['Altıntaş'])
    queue_item(store, urla, 'announcement', AT, AT)
    outage_event(store, 'Seferihisar', ['Sığacık'])
    prepare(store, AT)
    assets = {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"], 'story': [f"media/{p['id']}/story-1.jpg"]}
              for p in store.posts() if not p.get('publish_format')}
    adapter = api()
    assert publish_outage_story(store, AT, SITE, assets, adapter)['status'] == 'published'
    later = AT + timedelta(minutes=46)
    with store.db:
        store.db.execute('UPDATE items SET last_seen=?', (later.isoformat(),))
    assert publish_outage_story(store, later, SITE, assets, adapter)['status'] == 'empty'
    published = [p['title'] for p in store.posts() if p['status'] == 'published']
    assert published == ['Seferihisar’da planlı elektrik kesintisi · Story 1']


def test_digest_leaves_out_other_districts_theatre(store):
    for index, location in enumerate(('Urla Hakan Çeken Kültür Merkezi Urla/İzmir',
                                      'Seferihisar Çağan Irmak Kültür Merkezi Seferihisar İzmir')):
        url = f'https://biletinial.com/tr-tr/tiyatro/oyun-{index}'
        store.upsert(play(location, url=url, title=f'Oyun {index}'), AT.isoformat())
    concert = play('Urla Hakan Çeken Kültür Merkezi', url='https://example.org/konser', category='concert',
                   ticket_url=None, title='Urla konseri', description='Açık hava konseri.')
    store.upsert(concert, AT.isoformat())
    prepare(store, AT)
    weekly = next(p for p in store.posts() if p['kind'] == 'weekly')
    titles = [s['title'] for s in weekly['slides'][1:]]
    assert any('Oyun 1' in t for t in titles) and not any('Oyun 0' in t for t in titles)
    assert any('Urla konseri' in t for t in titles)
    assert post_reason(store, weekly, AT) is None


def test_hold_codes_are_recorded_as_holds_not_failures():
    for code in district.REASONS:
        value = safe_result({'status': code, 'outage_story': code})
        assert value == {'status': code, 'outage_story': code} and not failed(value)
