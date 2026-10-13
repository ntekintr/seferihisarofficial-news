import json
from unittest.mock import Mock

import pytest
import requests

from seferihisar.collect import Fetcher, collect_source, feed_items, structured
from seferihisar.domain import local
from seferihisar.editor import verify, headline, caption


@pytest.mark.parametrize('value', [
    'Urla konseri', 'Güzelbahçe festival programı', 'Yelki tiyatro etkinliği',
    'Özdere su kesintisi', 'URLA ESHOT ulaşım duyurusu',
    'GUZELBAHCE konser', 'SEFERİHİSAR haberleri',
])
def test_regional_relevance(value):
    assert local(value)


@pytest.mark.parametrize('value', [
    'Ankara konseri', 'Urla esnaf ziyareti', 'Özdere magazin',
    'Yelkili bir tekne konseri', 'Buralarda festival var',
    'Düzce sağlık müdürü Urla sağlık hizmetleri toplantısına katıldı',
])
def test_unrelated_or_routine_nearby_news_rejected(value):
    assert not local(value)


@pytest.mark.parametrize('status,reviewed,allowed', [(404, True, True), (410, True, True),
    (404, False, False), (403, True, False), (429, True, False), (500, True, False)])
def test_absent_robots_exception_is_narrow(source, monkeypatch, status, reviewed, allowed):
    fetcher = Fetcher([{**source, 'allow_missing_robots': reviewed}])
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError('not public', response=response)
    request = Mock(side_effect=[error, ('article', source['url'])])
    monkeypatch.setattr(fetcher, 'request', request)
    if allowed:
        assert fetcher.get(source['url'])[0] == 'article'
    else:
        with pytest.raises(requests.HTTPError):
            fetcher.get(source['url'])
        assert request.call_count == 1


def test_publisher_trailing_slash_redirect_finishes(source, monkeypatch):
    monkeypatch.setattr('seferihisar.collect.socket.getaddrinfo',
                        lambda *a, **k: [(None, None, None, None, ('93.184.216.34', 443))])
    monkeypatch.setattr('seferihisar.collect.time.sleep', lambda _: None)
    redirect = Mock(is_redirect=True, headers={'Location': '/duyuru/'})
    page = Mock(is_redirect=False, encoding='utf-8', headers={'Content-Type':'text/html; charset=utf-8'})
    page.iter_content.return_value = [b'public article']
    session = Mock()
    session.get.side_effect = [redirect, page]
    body, final = Fetcher([source],session).request('https://seferihisar.bel.tr/duyuru')
    assert body == 'public article'
    assert final == 'https://seferihisar.bel.tr/duyuru/'
    assert session.get.call_count == 2
    assert session.get.call_args.args[0] == final


def test_malformed_gundem_schema_falls_back_to_explicit_metadata():
    source = {'id':'seferihisar-gundem','name':'Seferihisar Gündem',
              'article_selector':'.post-body .detay'}
    page = '''<meta property="og:title" content="Seferihisar'da Ahi Festivali">
    <meta name="datePublished" content="2026-10-09T11:01:13+03:00">
    <script type="application/ld+json">{"@type":"NewsArticle","description":"bad
    json"}</script><div class="post-body"><div class="detay">
    <p>Seferihisar'da düzenlenen Ahi Festivali için program açıklandı.</p>
    </div></div>'''
    item = structured(page,'https://www.seferihisargundem.com/ahi/3085/',source)[0]
    assert item['published_at'] == '2026-10-09T11:01:13+03:00'
    assert item['url'].endswith('/ahi/3085/')
    assert item['identity'].endswith('/ahi/3085')
    assert 'program açıklandı' in item['description']


def test_municipal_template_uses_real_date_and_article_body(source):
    page = '''<script type="application/ld+json">{"@type":"Article",
    "headline":"Seferihisar kültür buluşması", "datePublished":"2026-10-10",
    "publisher":{"name":"Belediye",},}</script>
    <article><p>Seferihisar kültür buluşmasının programı kaynakta açıklandı.</p></article>'''
    item = structured(page, 'https://seferihisar.bel.tr/duyuru', source)[0]
    assert item['published_at'].startswith('2026-10-10')
    assert 'programı' in item['description']


def test_homepage_schema_url_does_not_collapse_articles(source):
    obj = {'@type':'NewsArticle','headline':'Urla konseri',
           'description':'Urla konser programı açıklandı.', 'datePublished':'2026-10-10',
           'url':'https://seferihisar.bel.tr/'}
    item = structured('<script type="application/ld+json">'+json.dumps(obj)+'</script>',
                      'https://seferihisar.bel.tr/konser',source)[0]
    assert item['url'].endswith('/konser')


def test_nearby_items_still_obey_date_and_sensitive_checks(source, event, at):
    item = {**event, 'title':'Urla konseri', 'description':'Konser programı', 'location':'Urla'}
    assert verify(item,source,at) is None
    item['description'] = 'Konserde yaralı var'
    assert verify(item,source,at) == 'human_review_required'
    assert "Seferihisar'da" not in headline(item,'reminder_day')


def test_migration_and_detention_reports_require_review(source, event, at):
    item = {**event, 'title':'Seferihisar açıklarında göçmenler yakalandı'}
    assert verify(item,source,at) == 'human_review_required'


def test_nearby_caption_uses_reported_place(event):
    item = {**event,'title':'Urla konseri','description':'Konser programı açıklandı.','location':'Urla'}
    content = caption(item,headline(item,'announcement'))
    assert '#urla' in content
    assert '#sigacik' not in content


def test_districts_share_budget_fairly(source):
    source = {**source,'url':'https://seferihisar.bel.tr/',
              'listing_urls':['https://seferihisar.bel.tr/a','https://seferihisar.bel.tr/b'],
              'link_selector':'a[href]','max_pages':2}
    pages = {'https://seferihisar.bel.tr/a':'<a href="/a1">A</a><a href="/a2">A2</a>',
             'https://seferihisar.bel.tr/b':'<a href="/b1">B</a>'}
    fetcher = Mock()
    fetcher.get.side_effect = lambda url: (pages.get(url,''),url)
    collect_source(source,fetcher,[])
    assert [c.args[0] for c in fetcher.get.call_args_list][-2:] == [
        'https://seferihisar.bel.tr/a1','https://seferihisar.bel.tr/b1']


def test_listing_fetches_original_slash_and_deduplicates_tracking_links(source):
    source = {**source,'link_selector':'a[href]'}
    fetcher = Mock()
    fetcher.get.side_effect = [('<a href="/haber/?utm_source=first">A</a><a href="/haber/">B</a>',source['url']), ('','https://seferihisar.bel.tr/haber/')]
    collect_source(source,fetcher,[])
    assert fetcher.get.call_count == 2
    assert fetcher.get.call_args.args[0] == 'https://seferihisar.bel.tr/haber/'


@pytest.mark.parametrize('event_date,kind',[('30 Ekim 2026','event'),('30 Ekim','news')])
def test_feed_event_uses_explicit_year_and_never_publication_date(source,event_date,kind):
    xml = '''<rss><channel><item><title>Urla konseri</title><link>/konser/</link>
    <pubDate>Sat, 10 Oct 2026 07:00:00 GMT</pubDate><description><![CDATA[
    <p>Urla konser programı ve buluşması açıklandı.</p>
    <p>Tarih: '''+event_date+'''</p><p>Saat: 20.30</p><p>Yer: Urla</p>
    ]]></description></item></channel></rss>'''
    item=feed_items(xml,source['url'],source)[0]
    assert item['kind']==kind
    if kind=='event':
        assert item['start']=='2026-10-30T20:30:00+03:00'
    else:
        assert 'start' not in item


def test_feed_only_source_still_rechecks_known_future_events(source,event):
    source={**source,'kind':'rss','follow_feed_details':False}
    feed='''<rss><channel><item><title>Seferihisar sanat</title><link>/sanat/</link>
    <pubDate>Sat, 10 Oct 2026 07:00:00 GMT</pubDate>
    <description>Seferihisar sanat buluşması için program açıklandı.</description>
    </item></channel></rss>'''
    fetcher=Mock()
    fetcher.get.side_effect=lambda url: (feed if url==source['url'] else '',url)
    items,_,errors=collect_source(source,fetcher,[])
    assert len(items)==1 and not errors
    assert fetcher.get.call_count==1
    fetcher.get.reset_mock()
    collect_source(source,fetcher,[event])
    assert fetcher.get.call_count==2
    assert fetcher.get.call_args.args[0]==event['url']

