import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from seferihisar.domain import digest, parse_date
from seferihisar.facebook import Facebook, publish_recent
from seferihisar.security import validate_state
from seferihisar.store import Store


def setup_content(store, at, *, slides=1):
    item = {'kind':'news', 'title':'Seferihisar kültür duyurusu', 'description':'Kaynak tarafından yerel kültür haberinin ayrıntıları duyuruldu.',
            'url':'https://example.org/news/1', 'sources':['https://example.org/news/1'],
            'source_id':'example', 'source_name':'Yerel kaynak', 'category':'culture',
            'published_at':(at-timedelta(minutes=20)).isoformat()}
    item_id, _ = store.upsert(item, at.isoformat())
    key = digest('facebook-test-parent')
    parent = {'id':key,'item_id':item_id,'revision':1,'kind':'news','due_at':at.isoformat(),
              'title':item['title'],'caption':'Haber metni. Kaynak: https://example.org/news/1',
              'source_urls':item['sources'],'created_at':at.isoformat(), 'category':'culture',
              'published_at':(at-timedelta(minutes=5)).isoformat()}
    store.queue(parent)
    child = {**parent, 'id':digest(key+':story:0'), 'parent_post_id':key, 'publish_format':'story',
             'story_index':0, 'story_asset':f'media/{key}/story-1.jpg'}
    store.queue(child)
    with store.db:
        store.db.execute("UPDATE posts SET status='published',media_id='7890'")
    return {key:{'feed':[f'media/{key}/feed-{i+1}.jpg' for i in range(slides)],'story':[child['story_asset']]}}, key


def api():
    result = Mock()
    result.enabled.return_value = True
    result.check_identity.return_value = True
    result.page = '1303548319516253'
    result.session.head.return_value = SimpleNamespace(status_code=200, headers={'Content-Type':'image/jpeg'})
    result.upload.return_value = '12345'
    result.publish.side_effect = ['1303548319516253_12345','67890']
    return result


def test_same_content_feed_and_first_story_are_mirrored_once_across_restart(store, at):
    assets, key = setup_content(store,at,slides=2); adapter=api(); checkpoints=Mock()
    result=publish_recent(store,at,'https://example.org/',assets,adapter,checkpoints)
    assert result == {'status':'complete','feed':'published','story':'published'}
    assert adapter.publish.call_args_list[0].args == (['12345','12345'],'Haber metni. Kaynak: https://example.org/news/1',False)
    assert adapter.publish.call_args_list[1].args[-1] is True
    assert adapter.upload.call_count == 3 and checkpoints.call_count == 7
    assert all(p['status']=='published' and p['media_id']=='7890' for p in store.posts())
    validate_state(store.path)
    reopened=Store(store.path)
    try:
        assert publish_recent(reopened,at,'https://example.org/',assets,adapter)['status']=='complete'
        assert adapter.publish.call_count==2
    finally:
        reopened.close()


@pytest.mark.parametrize('status',['publishing','uncertain'])
def test_existing_unresolved_claim_never_retries(store,at,status):
    assets,key=setup_content(store,at);adapter=api()
    claim=digest(f'facebook:{adapter.page}:{key}:feed')
    with store.db:
        store.db.execute('INSERT INTO facebook_deliveries VALUES(?,?,?,?,?,?,?,?,NULL)',
                         (claim,key,adapter.page,'feed',status,at.isoformat(),at.isoformat(),'[]'))
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='awaiting_resolution'
    adapter.upload.assert_not_called()


def test_timeout_after_feed_write_is_uncertain_without_republishing_instagram(store,at):
    assets,key=setup_content(store,at);adapter=api()
    adapter.publish.side_effect=requests.Timeout('must not reach logs')
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='uncertain'
    assert store.rows('SELECT status FROM facebook_deliveries')==[{'status':'uncertain'}]
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='awaiting_resolution'
    assert adapter.publish.call_count==1
    assert all(p['status']=='published' for p in store.posts())


def test_remote_claim_failure_prevents_all_meta_writes(store,at):
    assets,key=setup_content(store,at);adapter=api()
    with pytest.raises(RuntimeError):
        publish_recent(store,at,'https://example.org/',assets,adapter,Mock(side_effect=RuntimeError('remote unavailable')))
    adapter.upload.assert_not_called();adapter.publish.assert_not_called()


def test_story_failure_preserves_feed_and_does_not_retry_story(store,at):
    assets,key=setup_content(store,at);adapter=api()
    adapter.publish.side_effect=['12345',requests.Timeout()]
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['story']=='uncertain'
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['story']=='awaiting_resolution'
    assert adapter.publish.call_count==2


@pytest.mark.parametrize('change',['unpublished','old','yesterday','failed_source','revision','stale_source'])
def test_ineligible_instagram_content_is_not_mirrored(store,at,change):
    assets,key=setup_content(store,at);adapter=api()
    with store.db:
        if change=='unpublished':
            store.db.execute("UPDATE posts SET status='uncertain' WHERE id=?",(key,))
        elif change in ('old','yesterday'):
            payload=json.loads(store.rows('SELECT payload FROM posts WHERE id=?',(key,))[0]['payload'])
            payload['published_at']=(at-timedelta(hours=2 if change=='old' else 24)).isoformat()
            store.db.execute('UPDATE posts SET payload=? WHERE id=?',(json.dumps(payload),key))
        elif change=='failed_source':
            store.db.execute('INSERT INTO runs(started_at,finished_at,errors) VALUES(?,?,?)',
                (at.isoformat(),at.isoformat(),json.dumps([{'source_id':'example','code':'collection_failed'}])))
        elif change=='revision':
            store.db.execute('UPDATE items SET revision=2')
        else:
            store.db.execute('UPDATE items SET last_seen=?',((at-timedelta(hours=2)).isoformat(),))
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status'] in ('empty','blocked_source')
    adapter.upload.assert_not_called()


def test_page_or_instagram_mismatch_prevents_write(store,at):
    assets,key=setup_content(store,at);adapter=api();adapter.check_identity.return_value=False
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='account_mismatch'
    adapter.upload.assert_not_called()


def test_unpublished_instagram_story_waits_for_next_run(store,at):
    assets,key=setup_content(store,at);adapter=api()
    with store.db:
        store.db.execute("UPDATE posts SET status='uncertain' WHERE id<>?",(key,))
    assert publish_recent(store,at,'https://example.org/',assets,adapter)=={'status':'story_pending','feed':'published'}
    assert adapter.publish.call_count==1


def test_daily_budget_counts_uncertain_attempts(store,at):
    assets,key=setup_content(store,at);adapter=api()
    for i in range(2):
        with store.db:
            store.db.execute('INSERT INTO facebook_deliveries VALUES(?,?,?,?,?,?,?,?,NULL)',
                (digest(f'claim-{i}'),digest(f'other-{i}'),adapter.page,'feed','uncertain',at.isoformat(),at.isoformat(),'[]'))
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='daily_limit'
    adapter.upload.assert_not_called()


def test_undeployed_media_and_external_asset_paths_cannot_publish(store,at):
    assets,key=setup_content(store,at);adapter=api();adapter.session.head.return_value.status_code=404
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='media_not_deployed'
    assets[key]['feed']=['https://untrusted.example/image.jpg']
    assert publish_recent(store,at,'https://example.org/',assets,adapter)['status']=='media_missing'
    adapter.upload.assert_not_called()
    assert store.rows('SELECT * FROM facebook_deliveries')==[]


def test_adapter_is_disabled_until_credentials_and_both_explicit_gates(monkeypatch):
    for key in ('FACEBOOK_PUBLISH_ENABLED','FACEBOOK_TESTS_COMPLETED','FACEBOOK_PAGE_ACCESS_TOKEN','FACEBOOK_PAGE_ID','INSTAGRAM_USER_ID'):
        monkeypatch.delenv(key,raising=False)
    assert not Facebook().enabled()
    for key,value in {'FACEBOOK_PUBLISH_ENABLED':'true','FACEBOOK_TESTS_COMPLETED':'true',
        'FACEBOOK_PAGE_ACCESS_TOKEN':'SYNTHETIC_FACEBOOK_KEY','FACEBOOK_PAGE_ID':'1234','INSTAGRAM_USER_ID':'5678'}.items():
        monkeypatch.setenv(key,value)
    assert Facebook().enabled()
    monkeypatch.setenv('FACEBOOK_TESTS_COMPLETED','false')
    assert not Facebook().enabled()


def test_adapter_uses_bearer_header_no_redirects_and_safe_errors(monkeypatch):
    monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','SYNTHETIC_FACEBOOK_KEY')
    session=Mock();session.request.return_value=SimpleNamespace(ok=False,status_code=302)
    with pytest.raises(RuntimeError,match='^Facebook API request failed$'):
        Facebook(session).call('1234/feed',message='caption')
    args,kwargs=session.request.call_args
    assert kwargs['headers']=={'Authorization':'Bearer SYNTHETIC_FACEBOOK_KEY'}
    assert kwargs['allow_redirects'] is False and 'SYNTHETIC_FACEBOOK_KEY' not in args[1]


def test_persistent_delivery_cannot_carry_credentials_or_extra_fields(store,at,monkeypatch):
    assets,key=setup_content(store,at);adapter=api()
    publish_recent(store,at,'https://example.org/',assets,adapter)
    monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic-private-credential')
    with store.db: store.db.execute('UPDATE facebook_deliveries SET photo_ids=?',(json.dumps(['synthetic-private-credential']),))
    with pytest.raises(ValueError): validate_state(store.path)
