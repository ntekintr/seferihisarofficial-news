import json
from unittest.mock import patch

import pytest

from seferihisar.collect import discover, feed_items, safe_url, structured


def html(obj):
    return '<script type="application/ld+json">' + json.dumps(obj) + '</script>'


def test_structured_event_extracts_facts_and_cancellation(source):
    items = structured(html({"@type": "MusicEvent", "@id": "#concert", "name": "Seferihisar konseri", "startDate": "2026-10-30T20:00:00+03:00", "eventStatus": "https://schema.org/EventCancelled", "location": {"name": "Sığacık", "address": {"streetAddress": "Kaleiçi"}}, "offers": {"price": 0, "url": "/bilet"}}), source["url"], source)
    assert len(items) == 1
    event = items[0]
    assert event["free"] is True and event["status"] == "cancelled"
    assert event["organizer"] is None
    assert event["ticket_url"] == "https://seferihisar.bel.tr/bilet"


def test_missing_date_not_invented_and_nonlocal_excluded(source):
    assert not structured(html({"@type": "Event", "name": "Seferihisar konseri"}), source["url"], source)
    assert not structured(html({"@type": "Event", "name": "Ankara konseri", "startDate": "2026-11-01"}), source["url"], source)


def test_rss_and_atom_dates_and_local_filter(source):
    rss = '<rss><channel><item><title>Seferihisar sanat</title><link>https://seferihisar.bel.tr/haber?utm_source=test</link><pubDate>Sat, 10 Oct 2026 07:00:00 GMT</pubDate><description>Seferihisar sanat atölyesi açılıyor.</description></item></channel></rss>'
    result = feed_items(rss, source["url"], source)
    assert result[0]["published_at"] == "2026-10-10T10:00:00+03:00"
    assert "utm_" not in result[0]["url"]
    atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Sığacık etkinliği</title><link href="/test"/><published>2026-10-10T10:00:00+03:00</published><summary>Konser duyurusu</summary></entry></feed>'
    assert len(feed_items(atom, source["url"], source)) == 1


def test_html_article_metadata_fallback(source):
    page = '<meta property="og:title" content="Seferihisar kültür programı"><meta property="article:published_time" content="2026-10-10"><article><p>Seferihisar ilçesinde yeni kültür programı açıklandı.</p></article>'
    assert structured(page, source["url"], source)[0]["kind"] == "news"


def test_turkish_labelled_future_event_does_not_use_publication_date(source):
    page = '<meta property="og:title" content="Seferihisar konseri"><meta property="article:published_time" content="2026-10-10"><article><p>Seferihisar konser programı ve buluşması açıklandı.</p><p>Etkinlik tarihi: 30 Ekim 2026</p><p>Saat: 20.30</p><p>Yer: Sığacık</p><p>Ücret: Ücretsiz</p></article>'
    event = structured(page, source["url"], source)[0]
    assert event['start']=='2026-10-30T20:30:00+03:00'
    assert event['free'] is True and event['location']=='Sığacık'


def test_event_date_without_year_is_never_guessed(source):
    page = '<meta property="og:title" content="Seferihisar konseri"><article><p>Tarih: 30 Ekim</p></article>'
    assert not structured(page, source['url'], source)


def test_discovery_cannot_auto_trust(source):
    found = discover('<link rel="alternate" type="application/rss+xml" href="/feed"><a href="https://tickets.example/">Bilet</a>', source["url"])
    assert len(found) == 2
    assert all(not c["trusted"] and not c["enabled"] for c in found)


@pytest.mark.parametrize('url', ['http://seferihisar.bel.tr/', 'https://localhost/', 'https://evil.example/', 'https://user:pass@seferihisar.bel.tr/', 'https://seferihisar.bel.tr:8443/'])
def test_unapproved_or_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        safe_url(url, {"seferihisar.bel.tr"})


def test_private_ip_on_allowed_host_rejected():
    with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
        with pytest.raises(ValueError):
            safe_url('https://seferihisar.bel.tr/', {'seferihisar.bel.tr'})
