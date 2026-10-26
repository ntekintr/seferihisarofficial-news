"""Missing CDN robots is distinct from denial; session posters are never filler."""
from contextlib import closing
from datetime import timedelta
from unittest.mock import Mock
import pytest
import requests

from seferihisar.collect import Fetcher
from seferihisar.domain import parse_date
from seferihisar.source_photo_data import delivery_sources,same_event_artwork,EVENT_VERSION
from seferihisar.source_photo_retry import active,remember
from seferihisar.store import Store

SOURCE={'id':'bubilet','kind':'ticketing','url':'https://www.bubilet.com.tr/izmir','enabled':True}
URL='https://cdn.bubilet.com.tr/cdn-cgi/image/width=1200,quality=100/files/Etkinlik/show.png'


@pytest.mark.parametrize('status,allowed',[(404,True),(410,True),(403,False),(429,False),(503,False)])
def test_only_missing_robot_file_on_reviewed_cdn_allows_download(status,allowed):
    fetch=Fetcher([SOURCE]+delivery_sources({SOURCE['id']:SOURCE}))
    response=requests.Response();response.status_code=status
    error=requests.HTTPError(response=response)
    fetch.request=Mock(side_effect=[error,(b'image',URL)])
    if allowed:
        assert fetch.image(URL)==(b'image',URL)
        assert fetch.request.call_count==2
    else:
        with pytest.raises(requests.HTTPError):fetch.image(URL)
        assert fetch.request.call_count==1


def test_existing_disallow_rule_is_obeyed_and_other_cdns_do_not_opt_in():
    fetch=Fetcher([SOURCE]+delivery_sources({SOURCE['id']:SOURCE}))
    fetch.request=Mock(return_value=('User-agent: *\nDisallow: /', 'https://cdn.bubilet.com.tr/robots.txt'))
    with pytest.raises(ValueError,match='disallows'):fetch.image(URL)
    assert fetch.request.call_count==1
    assert not delivery_sources({'unreviewed':{**SOURCE,'id':'unreviewed'}})


def test_one_migration_retry_then_normal_cooldown(tmp_path):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        item={'id':'a'*24,'revision':1};at=parse_date('2026-10-26T11:00:00+03:00')
        remember(store,item,at,'image_read')
        assert active(store,item,at)
        assert not active(store,item,at,obsolete=('image_read',))
        remember(store,item,at,'poster_delivery_v2')
        assert active(store,item,at,obsolete=('image_read',))
        assert not active(store,item,at+timedelta(hours=1),obsolete=('image_read',))


def test_same_show_sessions_can_share_poster_but_other_items_cannot():
    base='https://www.bubilet.com.tr/izmir/etkinlik/ayni-gosteri/seans/'
    row={'kind':'event','category':'theatre','status':'scheduled','source_id':'bubilet',
         'title':'Aynı tiyatro gösterisi','url':base+'2'}
    evidence={'version':EVENT_VERSION,'source_id':'bubilet','subject':'theatre',
              'title':row['title'],'source_url':base+'1'}
    assert same_event_artwork(evidence,row)
    for changed in ({'kind':'news'},{'title':'Başka gösteri'},
                    {'url':base.replace('ayni-gosteri','baska-gosteri')+'2'},
                    {'url':base.replace('www.bubilet.com.tr','other.example')+'2'},
                    {'source_id':'other'},{'category':'concert'}):
        assert not same_event_artwork(evidence,{**row,**changed})
