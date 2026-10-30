import json
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from seferihisar.schedule import card_location
from seferihisar.source_readers import collect_tickets, ticket_items

SOURCES = {s['id']: s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))}
FIXTURES = Path('tests/fixtures/source_coverage')


def fetcher_for(pages):
    fetcher = Mock()
    fetcher.get.side_effect = lambda url: (pages.get(url, 'detail'), url)
    return fetcher


def test_bademler_venue_reads_plain_detail_paths_not_the_shifted_branch_variant():
    # 30 Ekim 2026: the ?cinemaBranchId page printed 10:00 but its schema said 13:00.
    source = SOURCES['biletinial-bademler']
    venue = ('<li><a href="/tr-tr/egitim/nina-bafikir-ile-mindful-yoga?cinemaBranchId=18326">Yoga</a></li>'
             '<li><a href="/tr-tr/muzik/rebetiko-kordelio?cinemaBranchId=18326">Rebetiko</a></li>'
             '<li><a href="/tr-tr/egitim/nina-bafikir-ile-mindful-yoga?cinemaBranchId=18326">Yoga</a></li>'
             '<li><a href="/tr-tr/mekan/baska-mekan">Başka mekân</a></li>')
    fetcher = fetcher_for({source['url']: venue})
    collect_tickets(source, fetcher, [], reader=Mock(return_value=[]))
    assert [call.args[0] for call in fetcher.get.call_args_list] == [
        source['url'],
        'https://biletinial.com/tr-tr/egitim/nina-bafikir-ile-mindful-yoga',
        'https://biletinial.com/tr-tr/muzik/rebetiko-kordelio']


def test_detail_query_is_kept_for_sources_without_the_reviewed_opt_in():
    source = {**SOURCES['biletinial-bademler']}
    source.pop('strip_detail_query')
    venue = '<li><a href="/tr-tr/muzik/rebetiko-kordelio?cinemaBranchId=18326">Rebetiko</a></li>'
    fetcher = fetcher_for({source['url']: venue})
    collect_tickets(source, fetcher, [], reader=Mock(return_value=[]))
    assert fetcher.get.call_args_list[-1].args[0].endswith('?cinemaBranchId=18326')


def test_bademler_biletinial_reader_keeps_only_verified_bademler_sessions():
    source = SOURCES['biletinial-bademler']
    body = (FIXTURES / 'biletinial-bademler-detail.html').read_text(encoding='utf-8')
    items = ticket_items(body, 'https://biletinial.com/tr-tr/egitim/nina-bafikir-ile-mindful-yoga', source)
    assert [i['start'] for i in items] == ['2026-11-01T10:00:00+03:00', '2026-11-04T19:30:00+03:00']
    assert len({i['identity'] for i in items}) == 2
    assert all('Bademler Sanat Köyü' in i['location'] and 'Urla' in i['location'] for i in items)
    # The venue name alone is not enough; the session's own address must be local.
    assert not ticket_items(body.replace('Urla/İzmir', 'Konak/İzmir'), items[0]['url'], source)


def test_theatre_listing_reads_every_izmir_page_where_local_halls_appear():
    source = SOURCES['biletinial']
    assert [urlsplit(u).query.rsplit('page=', 1)[1] for u in source['listing_urls']] == ['1', '2', '3', '4']
    assert all('organizerUrl=tiyatro' in u and urlsplit(u).hostname == 'biletinial.com' for u in source['listing_urls'])
    rows = lambda saloon, slug: json.dumps({'hasMore': True, 'items': [
        {'saloonName': saloon, 'seoUrl': slug, 'organizerUrl': 'tiyatro'}]})
    pages = {source['listing_urls'][0]: rows('Konak Sahnesi', 'merkez-oyun'),
             source['listing_urls'][1]: rows('Seferihisar Çağan Irmak Kültür Merkezi', 'mavis-baba'),
             source['listing_urls'][2]: rows('Bornova Sahnesi', 'diger-oyun'),
             source['listing_urls'][3]: rows('Urla Hakan Çeken Kültür Merkezi', 'nese-i-muhabbet')}
    fetcher = fetcher_for(pages)
    collect_tickets(source, fetcher, [], reader=Mock(return_value=[]))
    assert [call.args[0] for call in fetcher.get.call_args_list][4:] == [
        'https://biletinial.com/tr-tr/tiyatro/mavis-baba',
        'https://biletinial.com/tr-tr/tiyatro/nese-i-muhabbet']


def test_music_and_event_listings_follow_only_local_venue_cards():
    source = SOURCES['biletinial-sahne']
    music = ('<li><a href="/tr-tr/muzik/blues-night">Blues Night</a> Avlu Urla 27 Kasım</li>'
             '<li><a href="/tr-tr/muzik/merkez-konser">Merkez Konser</a> Ahmed Adnan Saygun Sanat Merkezi</li>')
    events = '<li><a href="/tr-tr/etkinlik/halloween-fest">Halloween Fest</a> Urla Sahne 31 Ekim</li>'
    fetcher = fetcher_for({source['listing_urls'][0]: music, source['listing_urls'][1]: events})
    collect_tickets(source, fetcher, [], reader=Mock(return_value=[]))
    assert [call.args[0] for call in fetcher.get.call_args_list][2:] == [
        'https://biletinial.com/tr-tr/muzik/blues-night',
        'https://biletinial.com/tr-tr/etkinlik/halloween-fest']


@pytest.mark.parametrize('source_id', ['bubilet-bademler', 'biletinial-bademler'])
def test_both_bademler_providers_render_the_same_card_venue(event, source_id):
    event.update(source_id=source_id,
                 location='Bademler Sanat Köyü Bademler, Bademler Cd. No:8, 35432 Urla/İzmir İzmir İzmir')
    assert card_location(event) == 'Bademler Sanat Köyü'
