import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import publish_automatic, publish_one
from seferihisar.schedule import prepare
from seferihisar.store import Store


def api():
    result = Mock()
    result.enabled.return_value = True
    result.account = '1234'
    result.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type':'image/jpeg'})
    result.container.return_value = 'container'
    result.call.return_value = {'id':'media'}
    return result


def news(store, at, name='1'):
    item = {'kind':'news','title':'Seferihisar kültür duyurusu '+name,'description':'Kaynak tarafından yerel kültür haberinin ayrıntıları duyuruldu.',
            'url':'https://example.org/news/'+name,'sources':['https://example.org/news/'+name],
            'source_id':'example','source_name':'Yerel kaynak','category':'culture',
            'published_at':(at-timedelta(minutes=20)).isoformat()}
    store.upsert(item, at.isoformat())
    prepare(store, at)
    # It was prepared before the configured slot, whose deadline has now arrived.
    with store.db:
        store.db.execute('UPDATE posts SET due_at=?',((at-timedelta(minutes=10)).isoformat(),))
        for row in store.rows('SELECT id,payload FROM posts'):
            payload=json.loads(row['payload']);payload['due_at']=(at-timedelta(minutes=10)).isoformat()
            store.db.execute('UPDATE posts SET payload=? WHERE id=?',(json.dumps(payload),row['id']))
    return {p['id']:{'feed':[f"media/{p['id']}/feed-1.jpg"],
                     'story':[f"media/{p['id']}/story-1.jpg",f"media/{p['id']}/story-2.jpg"]} for p in store.posts() if not p.get('publish_format')}


def claim(store, post, at, status='published'):
    payload={**post,'published_at':at.isoformat()}
    with store.db:
        store.db.execute('UPDATE posts SET payload=?,status=? WHERE id=?',(json.dumps(payload),status,post['id']))


def test_pair_publishes_one_feed_and_matching_first_story_without_duplicates(store):
    at=parse_date('2026-10-10T12:35:00+03:00');assets=news(store,at);adapter=api();checkpoints=Mock()
    assert publish_automatic(store,at,'https://example.org/',assets,adapter,checkpoints)=={'status':'complete','feed':'published','story':'published'}
    assert adapter.container.call_count==2 and checkpoints.call_count==6
    parent=next(p for p in store.posts() if not p.get('publish_format'))
    child=next(p for p in store.posts() if p['id']==digest(parent['id']+':story:0'))
    assert child['status']=='published' and child['parent_post_id']==parent['id']
    assert adapter.container.call_args.args[0]==['https://example.org/'+assets[parent['id']]['story'][0]]
    assert publish_automatic(store,at+timedelta(minutes=15),'https://example.org/',assets,adapter)['status']=='complete'
    assert adapter.container.call_count==2


def test_runner_restart_resumes_story_without_resending_feed(store):
    at=parse_date('2026-10-10T12:35:00+03:00');assets=news(store,at);adapter=api()
    assert publish_one(store,at,'https://example.org/',assets,adapter=adapter)['status']=='published'
    reopened=Store(store.path)
    try:
        assert publish_automatic(reopened,at+timedelta(minutes=10),'https://example.org/',assets,adapter)['status']=='complete'
        assert adapter.container.call_count==2
        assert adapter.container.call_args.args[2] is True
    finally:
        reopened.close()


@pytest.mark.parametrize('status',['uncertain','publishing'])
def test_uncertain_feed_consumes_slot_and_is_never_resent(store,status):
    at=parse_date('2026-10-10T15:10:00+03:00');assets=news(store,at);adapter=api()
    claim(store,store.posts()[0],at-timedelta(minutes=5),status)
    assert publish_automatic(store,at,'https://example.org/',assets,adapter)['status']=='awaiting_resolution'
    adapter.container.assert_not_called()


def test_three_daily_feed_claims_including_uncertainty_stop_new_publication(store):
    at=parse_date('2026-10-10T18:35:00+03:00');assets={}
    for name in 'abcd': assets.update(news(store,at,name))
    for post,stamp,status in zip(store.posts()[:3],['08:35','12:35','15:10'],['published','uncertain','publishing']):
        claim(store,post,parse_date('2026-10-10T'+stamp+':00+03:00'),status)
    adapter=api()
    assert publish_automatic(store,at,'https://example.org/',assets,adapter)['status']=='daily_limit'
    adapter.container.assert_not_called()


def test_budget_resets_on_turkish_day_not_utc_day(store):
    at=parse_date('2026-10-11T05:35:00+00:00');assets=news(store,at,'a');assets.update(news(store,at,'b'));assets.update(news(store,at,'c'))
    for post in store.posts()[:2]:
        claim(store,post,parse_date('2026-10-10T21:10:00+03:00'))
    assert publish_automatic(store,at,'https://example.org/',assets,api())['status']=='complete'


@pytest.mark.parametrize('stamp',['2026-10-10T08:29:00+03:00','2026-10-10T16:01:00+03:00','2026-10-10T22:01:00+03:00'])
def test_late_or_night_runs_do_not_dump_queued_content(store,stamp):
    at=parse_date(stamp);assets=news(store,at);adapter=api()
    assert publish_automatic(store,at,'https://example.org/',assets,adapter)['status']=='outside_window'
    adapter.container.assert_not_called()


def test_failed_source_blocks_automatic_publication(store):
    at=parse_date('2026-10-10T15:10:00+03:00');assets=news(store,at);adapter=api()
    with store.db:
        store.db.execute('INSERT INTO runs(started_at,finished_at,errors) VALUES(?,?,?)',(at.isoformat(),at.isoformat(),json.dumps([{'source_id':'example','code':'collection_failed'}])))
    assert publish_automatic(store,at,'https://example.org/',assets,adapter)['status']=='empty'
    adapter.container.assert_not_called()


def test_uncertain_story_is_not_resent_after_restart(store):
    at=parse_date('2026-10-10T15:10:00+03:00');assets=news(store,at);adapter=api()
    adapter.call.side_effect=[{'id':'feed'},RuntimeError('private provider details')]
    assert publish_automatic(store,at,'https://example.org/',assets,adapter)['story']=='uncertain'
    calls=adapter.container.call_count
    assert publish_automatic(store,at+timedelta(minutes=10),'https://example.org/',assets,adapter)['status']=='awaiting_resolution'
    assert adapter.container.call_count==calls


def test_pair_exception_does_not_bypass_another_feed_cooldown(store):
    at=parse_date('2026-10-10T15:10:00+03:00');assets=news(store,at,'a');assets.update(news(store,at,'b'));adapter=api()
    for post in store.posts():
        claim(store,post,at-timedelta(minutes=5))
    result=publish_automatic(store,at,'https://example.org/',assets,adapter)
    assert result['story']=='rate_limited'
    adapter.container.assert_not_called()
