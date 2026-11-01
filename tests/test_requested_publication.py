"""Explicit owner selection preserves budget, source checks, pairing and no replay."""
import json
from datetime import timedelta
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import publish_requested
from seferihisar.schedule import prepare
from seferihisar.story_identity import repeat
from test_automatic_publication import api, news, claim

AT = parse_date('2026-10-21T10:00:00+03:00')


def selected(store):
    assets = news(store, AT, 'a')
    assets.update(news(store, AT, 'b'))
    target = next(p for p in store.posts() if p['title'].endswith('b'))
    payload = {k:v for k,v in target.items() if k not in ('status',)}
    payload['due_at'] = (AT + timedelta(hours=2)).isoformat()
    with store.db:
        store.db.execute('UPDATE posts SET due_at=?,payload=? WHERE id=?',
                         (payload['due_at'],json.dumps(payload),target['id']))
    return assets, target['id']


def test_exact_parent_can_precede_window_pairs_first_story_and_never_chooses_older_queue(store):
    assets, target = selected(store); adapter = api(); checkpoint = Mock()
    assert publish_requested(store, AT, 'https://example.org/', assets, target, adapter, checkpoint) == {
        'status':'complete', 'feed':'published', 'story':'published'}
    assert adapter.container.call_args_list[0].args[0] == ['https://example.org/'+assets[target]['feed'][0]]
    assert adapter.container.call_args_list[1].args[0] == ['https://example.org/'+assets[target]['story'][0]]
    assert checkpoint.call_count == 6
    assert all(p['status']=='prepared' for p in store.posts() if p['id'] != target and not p.get('publish_format'))
    assert publish_requested(store, AT+timedelta(minutes=1), 'https://example.org/', assets, target, adapter)['status']=='complete'
    assert adapter.container.call_count == 2


@pytest.mark.parametrize('status', ['publishing', 'uncertain'])
def test_requested_uncertain_parent_is_never_replayed(store,status):
    assets,target=selected(store); adapter=api()
    claim(store,next(p for p in store.posts() if p['id']==target),AT,status)
    assert publish_requested(store,AT,'https://example.org/',assets,target,adapter)['status']=='awaiting_resolution'
    adapter.container.assert_not_called()


@pytest.mark.parametrize('reason', ['daily_limit','failed_source','stale_source','cooldown','missing_media','visual_gate'])
def test_explicit_choice_cannot_bypass_safety_or_choose_another_item(store,monkeypatch,reason):
    assets,target=selected(store); adapter=api()
    if reason=='daily_limit':
        assets.update(news(store,AT,'c'))
        assets.update(news(store,AT,'d'))
        for p in [p for p in store.posts() if p['id']!=target][:3]:
            claim(store,p,AT-timedelta(hours=2),'uncertain')
    elif reason=='failed_source':
        with store.db: store.db.execute('INSERT INTO runs(started_at,finished_at,errors) VALUES(?,?,?)',
            (AT.isoformat(),AT.isoformat(),json.dumps([{'source_id':'example','code':'failed'}])))
    elif reason=='stale_source':
        with store.db: store.db.execute('UPDATE items SET last_seen=?',((AT-timedelta(hours=2)).isoformat(),))
    elif reason=='cooldown': claim(store,next(p for p in store.posts() if p['id']!=target),AT-timedelta(minutes=20))
    elif reason=='missing_media': assets[target]['feed']=[]
    else: monkeypatch.setattr('seferihisar.visual_gate.deployed',lambda *a,**kw:'visual_review_stale')
    result=publish_requested(store,AT,'https://example.org/',assets,target,adapter,require_visual_review=reason=='visual_gate')
    assert result['status'] in ('daily_limit','blocked_source','rate_limited','media_missing','visual_review_stale','awaiting_content_visual')
    adapter.container.assert_not_called()


def test_unknown_id_never_falls_back_to_another_prepared_item(store):
    assets,_=selected(store);adapter=api()
    assert publish_requested(store,AT,'https://example.org/',assets,'f'*24,adapter)['status']=='empty'
    adapter.container.assert_not_called()


def test_expired_news_cannot_be_published_by_explicit_choice(store):
    assets,target=selected(store);adapter=api()
    for row in store.rows('SELECT id,payload FROM items'):
        value=json.loads(row['payload']);value['published_at']=(AT-timedelta(hours=49)).isoformat()
        with store.db:store.db.execute('UPDATE items SET payload=? WHERE id=?',(json.dumps(value),row['id']))
    assert publish_requested(store,AT,'https://example.org/',assets,target,adapter)['status']=='blocked_source'
    adapter.container.assert_not_called()


@pytest.mark.parametrize('extra', [['--automatic'],['--story'],[]])
def test_cli_rejects_ambiguous_or_invalid_requested_identity_before_opening_state(monkeypatch,extra):
    import sys
    from seferihisar.cli import main
    monkeypatch.setattr(sys,'argv',['seferihisar','publish','--post-id', 'a'*24 if extra else 'wrong',*extra])
    with pytest.raises(SystemExit) as result: main()
    assert result.value.code==2


def test_reworded_harvest_start_is_held_after_other_source_claim_but_later_development_is_distinct(store):
    titles=['Seferihisar Mandalinası’nda hasat başladı','Tescilli Satsuma mandalinasında hasat heyecanı başladı']
    for n,title in enumerate(titles):
        store.upsert({'kind':'news','title':title,'description':'Seferihisar’da mandalina hasadı başladı ve üreticiler çalışıyor.',
                      'url':f'https://example.org/{n}','source_id':'example','source_name':'Yerel kaynak',
                      'sources':[f'https://example.org/{n}'],'category':'food','published_at':AT.isoformat()},AT.isoformat())
    prepare(store,AT)
    old,pending=store.posts()
    claim(store,old,AT)
    assert repeat(store,pending)
    assert not repeat(store,{**pending,'title':'Güncelleme: '+pending['title']})
    assert not repeat(store,{**pending,'title':'Seferihisar’da mandalina üreticisine yeni alım desteği'})


def test_reworded_headline_of_the_same_ranking_is_held_after_other_source_claim(store):
    titles=['Seferihisar, Türkiye’nin Havası Temiz 10 İlçesi Arasında',"Türkiye'nin havası en temiz 10 ilçesi arasında Seferihisar da yer aldı"]
    for n,title in enumerate(titles):
        store.upsert({'kind':'news','title':title,'description':'Seferihisar hava kalitesi listesinde yer aldı ve dikkat çekti.',
                      'url':f'https://example.org/{n}','source_id':'example','source_name':'Yerel kaynak',
                      'sources':[f'https://example.org/{n}'],'category':'news','published_at':AT.isoformat()},AT.isoformat())
    prepare(store,AT)
    old,pending=store.posts()
    claim(store,old,AT)
    assert repeat(store,pending)
    assert not repeat(store,{**pending,'title':"Türkiye'nin havası en temiz 20 ilçesi arasında Seferihisar da yer aldı"})
    assert not repeat(store,{**pending,'title':"Türkiye'nin havası en kirli 10 ilçesi arasında Seferihisar da yer aldı"})


def test_category_label_does_not_separate_one_headline(store):
    title='Seferihisar sakızı hasat sezonu yoğun ilgiyle açıldı'
    store.upsert({'kind':'news','title':title,'description':'Seferihisar’da sakız hasadı için tören düzenlendi ve üreticiler katıldı.',
                  'url':'https://example.org/0','source_id':'example','source_name':'Yerel kaynak',
                  'sources':['https://example.org/0'],'category':'news','published_at':AT.isoformat()},AT.isoformat())
    prepare(store,AT)
    old=store.posts()[0]
    claim(store,old,AT)
    assert repeat(store,{**old,'id':'other','title':'Gastronomi: '+title})


def test_requested_facebook_delivery_does_not_choose_another_recent_parent(store,at):
    from test_facebook_publication import setup_content,api as facebook_api
    from seferihisar.facebook import publish_recent
    assets,old=setup_content(store,at);adapter=facebook_api()
    assert publish_recent(store,at,'https://example.org/',assets,adapter,target_id='f'*24)['status']=='empty'
    adapter.upload.assert_not_called()
