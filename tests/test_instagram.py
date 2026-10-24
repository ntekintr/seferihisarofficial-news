from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import requests

from seferihisar.instagram import Instagram, prepare_story_jobs, publish_one
from seferihisar.schedule import prepare


def adapter(fail=False):
    api = Mock()
    api.enabled.return_value = True
    api.account = '1234'
    api.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type':'image/jpeg'})
    api.container.return_value = 'container-1'
    if fail:
        api.call.side_effect = requests.Timeout('hidden token should not be printed')
    else:
        api.call.return_value = {'id':'media-1'}
    return api


def assets_for(store):
    return {p['id']:{'feed':[f"media/{p['id']}/feed-1.jpg", f"media/{p['id']}/feed-2.jpg"], 'story':[f"media/{p['id']}/story-1.jpg", f"media/{p['id']}/story-2.jpg"]} for p in store.posts()}


def test_real_api_disabled_by_default_and_missing_one_control(monkeypatch):
    for key in ('INSTAGRAM_PUBLISH_ENABLED','META_TESTS_COMPLETED','INSTAGRAM_ACCESS_TOKEN','INSTAGRAM_USER_ID','INSTAGRAM_AUTH_MODE'):
        monkeypatch.delenv(key, raising=False)
    assert not Instagram().enabled()
    monkeypatch.setenv('INSTAGRAM_PUBLISH_ENABLED','true')
    monkeypatch.setenv('INSTAGRAM_ACCESS_TOKEN','test')
    monkeypatch.setenv('INSTAGRAM_USER_ID','1234')
    monkeypatch.setenv('INSTAGRAM_AUTH_MODE','facebook_login')
    assert not Instagram().enabled()
    monkeypatch.setenv('META_TESTS_COMPLETED','true')
    assert Instagram().enabled()


def test_published_item_not_republished_and_claim_checkpoint_precedes_meta(store,event,at):
    store.upsert(event,at.isoformat())
    prepare(store,at)
    api=adapter()
    checkpoint=Mock(side_effect=lambda: api.container.assert_not_called() if not api.container.called else None)
    result=publish_one(store,at,'https://example.org/',assets_for(store),adapter=api,checkpoint=checkpoint)
    assert result['status']=='published'
    assert checkpoint.call_count==3
    assert publish_one(store,at,'https://example.org/',assets_for(store),adapter=api)['status']=='rate_limited'
    assert api.call.call_count==1


def test_uncertain_publish_is_not_retried(store,event,at):
    store.upsert(event,at.isoformat())
    prepare(store,at)
    api=adapter(fail=True)
    result=publish_one(store,at,'https://example.org/',assets_for(store),adapter=api)
    assert result['status']=='uncertain'
    calls=api.call.call_count
    # The failed reminder remains uncertain even after the rate limit expires.
    later=at+timedelta(hours=1)
    publish_one(store,later,'https://example.org/',assets_for(store),adapter=api)
    assert api.call.call_count==calls


def test_media_not_yet_deployed_prevents_meta_call(store,event,at):
    store.upsert(event,at.isoformat())
    prepare(store,at)
    api=adapter()
    api.session.head.return_value.status_code=404
    result=publish_one(store,at,'https://example.org/',assets_for(store),adapter=api)
    assert result['status']=='media_not_deployed'
    api.container.assert_not_called()


def test_only_first_matching_story_has_persistent_identity(store,event,at):
    store.upsert(event,at.isoformat())
    prepare(store,at)
    assets=assets_for(store)
    prepare_story_jobs(store,assets)
    initial=[p['id'] for p in store.posts() if p.get('publish_format')=='story']
    prepare_story_jobs(store,assets)
    assert initial==[p['id'] for p in store.posts() if p.get('publish_format')=='story']
    api=adapter()
    from seferihisar.domain import parse_date
    parent=next(p for p in store.posts() if p['id'] in assets and not p.get('publish_format') and parse_date(p['due_at'])<=at)
    # A news story must accompany a confirmed recent feed, never an unpublished one.
    import json
    with store.db:
        store.db.execute("UPDATE posts SET status='published',payload=? WHERE id=?",
                         (json.dumps({**parent,'published_at':at.isoformat()}),parent['id']))
    result=publish_one(store,at,'https://example.org/',assets,story=True,adapter=api,
                       target_id=next(p['id'] for p in store.posts() if p.get('parent_post_id')==parent['id']),paired_story=True)
    assert result['status']=='published'
    args=api.container.call_args.args
    assert len(args[0])==1 and args[2] is True


def test_api_carousel_and_story_parameters():
    session=Mock()
    api=Instagram(session)
    api.account='1234'
    api.call=Mock(side_effect=[{'id':'a'},{'id':'b'},{'id':'parent'}])
    api.wait=Mock()
    assert api.container(['https://example.org/a.jpg','https://example.org/b.jpg'],'caption',False)=='parent'
    assert api.call.call_args.kwargs['children']=='a,b'
    api.call=Mock(return_value={'id':'story'})
    assert api.container(['https://example.org/a.jpg'],'caption',True)=='story'
    assert api.call.call_args.kwargs['media_type']=='STORIES'
