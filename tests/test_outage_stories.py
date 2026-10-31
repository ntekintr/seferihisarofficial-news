from datetime import timedelta
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.facebook import publish_outage_story as mirror
from seferihisar.instagram import publish_automatic, publish_one, publish_outage_story, publish_requested
from seferihisar.operations import failed, safe_result, validate_result
from seferihisar.publication_policy import OUTAGE_STORY_LIMIT, day_claims, story_only
from seferihisar.render import render_post
from seferihisar.schedule import prepare
from tests.test_automatic_publication import api, claim, news

AT = parse_date('2026-11-02T08:40:00+03:00')
SITE = 'https://example.org/'


def outage(store, at, name='Urla', hours=1, start=None, end=None, location=None, note=''):
    begin = start or at + timedelta(hours=hours)
    item = {'kind':'event','identity':'https://example.org/gdz/'+name,'title':f'{name}’da planlı elektrik kesintisi',
            'description':'Planlı elektrik kesintisi resmî dağıtım şirketi tarafından duyuruldu.'+note,
            'url':'https://example.org/gdz/'+name,'sources':['https://example.org/gdz/'+name],
            'source_id':'gdz','source_name':'GDZ','category':'outage','start':begin.isoformat(),
            'end':(end or begin+timedelta(hours=4)).isoformat(),'status':'scheduled','time_known':True,
            'location':location or name}
    store.upsert(item,at.isoformat())
    prepare(store,at)
    return {p['id']:{'feed':[f"media/{p['id']}/feed-1.jpg"],'story':[f"media/{p['id']}/story-1.jpg"]}
            for p in store.posts() if not p.get('publish_format')}


def feeds(adapter):
    return [c for c in adapter.container.call_args_list if c.args[2] is False]


@pytest.mark.parametrize('value,expected',[
    ({'category':'outage','title':'Urla’da planlı elektrik kesintisi'},True),
    ({'category':'outage','title':'Urla’da planlı elektrik kesintisi · Story 1'},True),
    ({'category':'outage','title':'Urla’da su kesintisi'},False),
    ({'category':'municipality','title':'Elektrikli otobüs hattı açıldı'},False),
])
def test_only_power_cuts_are_story_only(value,expected):
    assert story_only(value) is expected


def test_power_cut_never_reaches_the_feed_even_when_it_is_the_only_content(store):
    assets=outage(store,AT);adapter=api()
    assert publish_automatic(store,AT,SITE,assets,adapter)['status']=='empty'
    assert publish_one(store,AT,SITE,assets,adapter=adapter)['status']=='empty'
    adapter.container.assert_not_called()


def test_explicit_owner_request_does_not_put_a_power_cut_on_the_feed(store):
    assets=outage(store,AT);adapter=api()
    parent=next(p for p in store.posts() if not p.get('publish_format'))
    assert publish_requested(store,AT,SITE,assets,parent['id'],adapter)['status']=='empty'
    adapter.container.assert_not_called()


def test_power_cut_publishes_alone_as_a_story_and_keeps_its_parent_unclaimed(store):
    assets=outage(store,AT);adapter=api();checkpoint=Mock()
    assert publish_outage_story(store,AT,SITE,assets,adapter,checkpoint)['status']=='published'
    assert adapter.container.call_count==1 and adapter.container.call_args.args[2] is True
    assert checkpoint.call_count==3
    parent=next(p for p in store.posts() if not p.get('publish_format'))
    child=next(p for p in store.posts() if p['id']==digest(parent['id']+':story:0'))
    assert child['status']=='published' and parent['status']=='prepared'
    assert adapter.container.call_args.args[0]==[SITE+assets[parent['id']]['story'][0]]


def test_news_keeps_all_three_daily_story_slots(store):
    assets=outage(store,AT);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    assert day_claims(store,AT,story=True)==[]
    assert len(day_claims(store,AT))==0


def test_power_cut_story_waits_for_news_but_never_delays_it(store):
    at=parse_date('2026-11-02T12:35:00+03:00');assets=news(store,at);assets.update(outage(store,at))
    adapter=api()
    assert publish_automatic(store,at,SITE,assets,adapter)['status']=='complete'
    assert publish_outage_story(store,at,SITE,assets,adapter)['status']=='rate_limited'
    assert publish_outage_story(store,at+timedelta(minutes=46),SITE,assets,adapter)['status']=='published'


def test_news_is_not_delayed_by_a_recent_power_cut_story(store):
    at=parse_date('2026-11-02T12:20:00+03:00');assets=outage(store,at);adapter=api()
    assert publish_outage_story(store,at,SITE,assets,adapter)['status']=='published'
    slot=at+timedelta(minutes=12);assets.update(news(store,slot))
    assert publish_automatic(store,slot,SITE,assets,adapter)['status']=='complete'


def test_revision_with_the_same_card_gets_no_second_story(store):
    start=AT+timedelta(hours=1);assets=outage(store,AT,start=start);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    later=AT+timedelta(minutes=50)
    assets.update(outage(store,later,start=start,note=' Kaynak metni güncellendi.'))
    assert publish_outage_story(store,later,SITE,assets,adapter)['status']=='empty'
    assert adapter.container.call_count==1


def test_duplicate_card_cannot_starve_the_next_cut(store):
    start=AT+timedelta(hours=1);assets=outage(store,AT,start=start);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    later=AT+timedelta(minutes=50)
    assets.update(outage(store,later,start=start,note=' Kaynak metni güncellendi.'))
    assets.update(outage(store,later,'Karaburun',hours=2))
    assert publish_outage_story(store,later,SITE,assets,adapter)['status']=='published'
    assert adapter.container.call_count==2


def test_real_change_to_a_cut_gets_its_own_story(store):
    start=AT+timedelta(hours=1);assets=outage(store,AT,start=start);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    later=AT+timedelta(minutes=50)
    assets.update(outage(store,later,start=start,location='Urla · Yalnız İçmeler'))
    assert publish_outage_story(store,later,SITE,assets,adapter)['status']=='published'
    assert adapter.container.call_count==2


def test_daily_limit_prefers_the_nearest_area(store):
    assets=outage(store,AT,'Urla');assets.update(outage(store,AT,'Güzelbahçe'))
    assets.update(outage(store,AT,'Seferihisar'));assets.update(outage(store,AT,'Karaburun'))
    adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    first=next(p for p in store.posts() if p.get('publish_format')=='story' and p['status']=='published')
    assert first['title'].startswith('Seferihisar')
    stamp=AT
    for _ in range(OUTAGE_STORY_LIMIT-1):
        stamp+=timedelta(minutes=46)
        assert publish_outage_story(store,stamp,SITE,assets,adapter)['status']=='published'
    stamp+=timedelta(minutes=46)
    with store.db:
        store.db.execute('UPDATE items SET last_seen=?',(stamp.isoformat(),))
    assert publish_outage_story(store,stamp,SITE,assets,adapter)['status']=='daily_limit'
    assert adapter.container.call_count==OUTAGE_STORY_LIMIT


@pytest.mark.parametrize('hours,expected',[(1,'published'),(30,'published'),(60,'empty')])
def test_only_todays_and_tomorrows_cuts_are_announced(store,hours,expected):
    assets=outage(store,AT,hours=hours)
    assert publish_outage_story(store,AT,SITE,assets,api())['status']==expected


@pytest.mark.parametrize('stamp',['2026-11-02T08:29:00+03:00','2026-11-02T21:00:00+03:00'])
def test_power_cut_story_waits_for_daytime(store,stamp):
    at=parse_date(stamp);assets=outage(store,AT);adapter=api()
    assert publish_outage_story(store,at,SITE,assets,adapter)['status']=='outside_window'
    adapter.container.assert_not_called()


def test_missing_visual_waits_without_a_card(store):
    assets=outage(store,AT);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter,require_visual_review=True)['status']=='empty'
    adapter.container.assert_not_called()


def facebook():
    result=Mock();result.enabled.return_value=True;result.check_identity.return_value=True;result.page='1'
    return result


def test_facebook_mirrors_the_story_outside_the_news_budget(store,monkeypatch):
    assets=outage(store,AT);adapter=api()
    assert publish_outage_story(store,AT,SITE,assets,adapter)['status']=='published'
    calls=[];parent=next(p for p in store.posts() if not p.get('publish_format'))
    monkeypatch.setattr('seferihisar.facebook.current_post',lambda *a:True)
    monkeypatch.setattr('seferihisar.facebook.deliver',lambda store,post,*a,**k:calls.append((post['id'],a[3]))or'published')
    assert mirror(store,AT+timedelta(minutes=1),SITE,facebook())=={'status':'published'}
    assert calls==[(parent['id'],True)]


def test_facebook_has_nothing_to_mirror_without_a_recent_story(store):
    assert mirror(store,AT,SITE,facebook())=={'status':'empty'}


def test_check_log_keeps_outage_results_and_flags_failures():
    value=safe_result({'status':'empty','outage_story':'published','outage_facebook':'uncertain','post_id':'PRIVATE'})
    validate_result(value)
    assert value=={'status':'empty','outage_story':'published','outage_facebook':'uncertain'}
    assert failed(value) and not failed({'status':'empty','outage_story':'empty','outage_facebook':'disabled'})

def test_story_card_does_not_point_to_a_caption_it_does_not_have(store,tmp_path,monkeypatch):
    outage(store,AT)
    post=next(p for p in store.posts() if not p.get('publish_format'))
    seen={}
    monkeypatch.setattr('seferihisar.render.inline_note',lambda post:True)
    monkeypatch.setattr('seferihisar.render.card',lambda title,body,category,target,story=False,*a,**k:seen.update({story:k['caption_note']}))
    render_post(post,tmp_path)
    assert seen=={False:True,True:False}
