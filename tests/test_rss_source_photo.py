"""RSS publication facts plus the exact official HTML gallery, never guesses."""
import pytest

from seferihisar.source_photos import candidate_urls


def test_official_rss_proves_date_when_article_html_has_no_article_schema():
    url='https://www.izmir.bel.tr/tr/Haberler/seferihisar-doga-yuruyusu/123/156'
    title='Seferihisar’da gençler doğa yürüyüşünde buluştu'
    source={'id':'izmir-belediye','name':'İzmir Büyükşehir Belediyesi','url':'https://www.izmir.bel.tr/tr/Rss/Haberler',
            'kind':'rss','photo_identity_reader':'rss-html-v1','photo_article_selector':'.izbel-content',
            'body_selector':'.izbel-content','photo_inline_selector':'.triple-slider .imageGallery1 img[src]'}
    item={'kind':'news','source_id':source['id'],'url':url,'title':title,'published_at':'2026-10-25T10:21:34+03:00'}
    feed=f'<rss><channel><item><title>{title}</title><link>{url}</link><description>Seferihisar doğa etkinliği.</description><pubDate>Sun, 25 Oct 2026 07:21:34 GMT</pubDate></item></channel></rss>'
    image='https://www.izmir.bel.tr/YuklenenDosyalar/Haberler/Buyuk/example.jpeg'
    html=f'<div class="izbel-content"><h1>{title}</h1><div class="triple-slider"><div class="imageGallery1"><a href="{image}"><img src="{image}"></a></div></div></div>'
    assert candidate_urls(html,url,item,source,feed_html=feed)==[image]
    for changed in (feed.replace('07:21:34','08:21:34'),feed.replace(title,'Seferihisar başka duyuru')):
        with pytest.raises(ValueError):candidate_urls(html,url,item,source,feed_html=changed)
    with pytest.raises(ValueError):candidate_urls(html,url,item,source)
    with pytest.raises(ValueError):candidate_urls(html.replace(title,'Başka başlık'),url,item,source,feed_html=feed)
