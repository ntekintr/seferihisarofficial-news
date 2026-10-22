"""Source/date/scope, readable cards and durable non-replaying daily stories."""
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar import pharmacy as module
from seferihisar.domain import TZ
from seferihisar.pharmacy_data import asset_id, fresh, make_bulletin, profile, validate_record
from seferihisar.pharmacy_source import parse_isparta, parse_izmir
from seferihisar.pharmacy_render import render, layouts
from seferihisar.security import validate_state, validate_public
from seferihisar.store import Store

AT=datetime(2026,10,22,17,tzinfo=TZ)


def bulletin(at=AT,entries=None):
    p=profile()
    return make_bulletin(entries or [dict(name='ÖRNEK ECZANESİ',address='Örnek Mahallesi 100. Sokak No:12/A',
        phone='02462188441',region='MERKEZ' if p['city']=='isparta' else 'SEFERİHİSAR',note='')],at.date(),at)


def insert(store,value,status='prepared'):
    with store.db:store.db.execute('INSERT INTO pharmacy_stories(day,bulletin,status,checked_at,last_result) VALUES(?,?,?,?,?)',
        (value['date'],json.dumps(value,ensure_ascii=False,sort_keys=True),status,value['checked_at'],'prepared'))


@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'state.sqlite');yield s;s.close()


def test_official_sources_do_not_mix_districts_or_site_dates(monkeypatch):
    from seferihisar import pharmacy_source as source
    monkeypatch.setattr(source,'make_bulletin',lambda entries,day,checked: {'entries':entries,'date':day.isoformat()})
    data=json.loads((Path(__file__).parent/'fixtures/pharmacy-izmir.json').read_text(encoding='utf-8'))
    value=parse_izmir(json.dumps(data),AT)
    assert {e['region'] for e in value['entries']}=={'SEFERİHİSAR','SIĞACIK'}
    html=(Path(__file__).parent/'fixtures/pharmacy-isparta.html').read_text(encoding='utf-8')
    value=parse_isparta(html,AT)
    assert len(value['entries'])==3 and {e['region'] for e in value['entries']}=={'MERKEZ'}
    assert value['entries'][0]['phone']=='02462188441'
    with pytest.raises(ValueError):parse_isparta(html.replace('22 Ekim 2026 Bugün','21 Ekim 2026 Bugün'),AT)


@pytest.mark.parametrize('delta',[-91,1])
def test_old_or_future_check_never_counts_as_fresh(delta):
    value=bulletin(AT+timedelta(minutes=delta));assert not fresh(value,AT)


def test_previous_day_never_becomes_current():
    assert not fresh(bulletin(AT-timedelta(days=1)),AT)


def test_source_failure_removes_pending_old_preview_but_never_a_claim(store,monkeypatch):
    insert(store,bulletin(AT-timedelta(minutes=30)))
    monkeypatch.setattr('seferihisar.pharmacy_source.fetch_bulletin',Mock(side_effect=ValueError('bad date')))
    module.refresh(store,AT)
    r=store.rows('SELECT * FROM pharmacy_stories')[0]
    assert r['status']=='blocked' and r['bulletin'] is None
    with store.db:store.db.execute("UPDATE pharmacy_stories SET status='uncertain'")
    old=store.rows('SELECT * FROM pharmacy_stories')
    module.refresh(store,AT);assert store.rows('SELECT * FROM pharmacy_stories')==old


@pytest.mark.parametrize('hour',[0,8,15,18,23])
def test_outside_window_performs_no_meta_or_late_replay(store,hour):
    api=Mock();assert module.publish(store,AT.replace(hour=hour),profile()['site'],api,Mock())['status']=='outside_window'
    api.enabled.assert_not_called();api.call.assert_not_called()


@pytest.fixture
def publish_setup(store,monkeypatch):
    value=bulletin();insert(store,value)
    api=Mock(account='12345678',base='https://graph.facebook.com/v26.0')
    api.enabled.return_value=True;api.container.side_effect=['1001','1002'];api.wait.return_value=None
    api.call.return_value={'id':'2001'}
    monkeypatch.setenv('INSTAGRAM_AUTH_MODE','facebook_login')
    monkeypatch.setattr(module,'_profile_enabled',lambda:True)
    monkeypatch.setattr(module,'account_matches',lambda adapter:True)
    monkeypatch.setattr(module,'readiness',lambda *args:module.Ready(value['date'],json.dumps(value,ensure_ascii=False,sort_keys=True),('https://example.invalid/story.jpg',)))
    return api,value


def test_claim_is_checkpointed_before_container_and_day_is_not_replayed(store,publish_setup,monkeypatch):
    api,value=publish_setup;events=[]
    api.container.side_effect=lambda *a:events.append('container') or '1001'
    result=module.publish(store,AT,profile()['site'],api,lambda:events.append('checkpoint'))
    assert result=={'status':'published','stories':1} and events[:2]==['checkpoint','container']
    r=store.rows('SELECT * FROM pharmacy_stories')[0]
    validate_record(tuple(r.values()))
    # The real readiness path short-circuits the frozen claim, before Meta.
    monkeypatch.undo();api.enabled.return_value=True
    monkeypatch.setattr(module,'_profile_enabled',lambda:True)
    assert module.publish(store,AT,profile()['site'],api,Mock())['status']=='already_published'
    assert api.container.call_count==1
    assert store.rows('SELECT * FROM posts')==[] and store.rows('SELECT * FROM weather_stories')==[]
    validate_state(store.path)


def test_uncertain_partial_series_keeps_confirmed_ids_and_never_resets(store,publish_setup,monkeypatch):
    api,value=publish_setup
    ready=module.Ready(value['date'],json.dumps(value,ensure_ascii=False,sort_keys=True),('https://example.invalid/a.jpg','https://example.invalid/b.jpg'))
    monkeypatch.setattr(module,'readiness',lambda *args:ready)
    api.container.side_effect=['1001',RuntimeError('provider failure')]
    assert module.publish(store,AT,profile()['site'],api,Mock())=={'status':'uncertain','confirmed_parts':1}
    row=store.rows('SELECT * FROM pharmacy_stories')[0]
    assert json.loads(row['media_ids'])==['2001'] and json.loads(row['container_ids'])==['1001']
    old=store.rows('SELECT * FROM pharmacy_stories');module.refresh(store,AT+timedelta(minutes=20))
    assert store.rows('SELECT * FROM pharmacy_stories')==old


def test_failed_first_checkpoint_cannot_send_media(store,publish_setup):
    api,_=publish_setup
    with pytest.raises(RuntimeError):module.publish(store,AT,profile()['site'],api,Mock(side_effect=RuntimeError('state unavailable')))
    api.container.assert_not_called()


def test_missing_durable_checkpoint_cannot_publish(store,publish_setup):
    api,_=publish_setup
    assert module.publish(store,AT,profile()['site'],api,None)=={'status':'disabled'}
    api.container.assert_not_called()


def test_closed_isparta_profile_never_constructs_or_reads_api(store,monkeypatch):
    monkeypatch.setattr(module,'_profile_enabled',lambda:False)
    api=Mock();assert module.publish(store,AT,profile()['site'],api,Mock())=={'status':'disabled'}
    api.enabled.assert_not_called();api.call.assert_not_called()


def test_actual_render_is_readable_and_bound_to_current_day(tmp_path):
    value=bulletin();entry=value['entries'][0]
    entries=[dict(entry,name=f'ÖRNEK {i} ECZANESİ',address=('Örnek Mahallesi 100. Sokak No:12/A ' * 4).strip()) for i in range(4)]
    value=bulletin(entries=entries);pages=layouts(value);assert len(pages)>=2
    assert sum(len(p) for p in pages)==4
    result=render(value,tmp_path)
    for p in result['assets']:
        with Image.open(tmp_path/p) as image:assert image.size==(1080,1920)
    assert len(result['sha256'])==len(pages)
    validate_public(tmp_path)


def test_readiness_checks_actual_jpeg_bytes_and_bulletin(store,tmp_path,monkeypatch):
    value=bulletin();insert(store,value);images=render(value,tmp_path)
    manifest={'demo':False,'brand':{'version':value['brand_version']},'pharmacy_story':{'status':'prepared','bulletin':value,**images}}
    api=Mock();api.enabled.return_value=True
    api.session.get.side_effect=[SimpleNamespace(status_code=200,content=json.dumps(manifest).encode(),json=lambda:manifest),
        SimpleNamespace(status_code=200,content=(tmp_path/images['assets'][0]).read_bytes(),headers={'Content-Type':'image/jpeg'})]
    monkeypatch.setattr(module,'_profile_enabled',lambda:True)
    assert isinstance(module.readiness(store,AT,profile()['site'],api),module.Ready)
    assert all(c.kwargs['allow_redirects'] is False for c in api.session.get.call_args_list)
    api.session.get.side_effect=[SimpleNamespace(status_code=200,content=b'{}',json=lambda:manifest),
        SimpleNamespace(status_code=200,content=b'other pixels',headers={'Content-Type':'image/jpeg'})]
    assert module.readiness(store,AT,profile()['site'],api)=={'status':'media_not_deployed'}


def test_early_wait_rechecks_and_only_sends_at_target(store,publish_setup,monkeypatch):
    api,_=publish_setup;clock=[AT-timedelta(seconds=35)]
    def sleep(seconds):clock[0]+=timedelta(seconds=seconds)
    original=api.container.side_effect
    def container(*args):
        assert clock[0]==AT
        return '1001'
    api.container.side_effect=container
    result=module.run(store,profile()['site'],api,Mock(),wait_for_target=True,clock=lambda:clock[0],sleeper=sleep)
    assert result['status']=='published' and clock[0]==AT


@pytest.mark.parametrize('mode,payload,expected',[
    ('facebook_login',{'id':'12345678','username':'correct'},True),
    ('facebook_login',{'id':'12345678','username':'other-city'},False),
    ('instagram_login',{'id':'12345678','username':'correct','account_type':'BUSINESS'},False),
    ('instagram_login',{'id':'other-app-id','user_id':'12345678','username':'correct','account_type':'Business'},True),
    ('instagram_login',{'user_id':'12345678','username':'correct','account_type':3},False),
    ('instagram_login',{'data':[{'user_id':'12345678','username':'correct','account_type':'Media_Creator'}]},True),
])
def test_account_and_route_checked_before_the_first_claim(monkeypatch,mode,payload,expected):
    monkeypatch.setenv('INSTAGRAM_AUTH_MODE',mode)
    monkeypatch.setattr(module,'profile',lambda:{'username':'correct'})
    api=Mock(account='12345678',base='https://graph.'+('instagram' if mode=='instagram_login' else 'facebook')+'.com/v26.0')
    api.call.return_value=payload
    assert module.account_matches(api) is expected
    assert api.call.call_args.args[1]=='GET'
    api.container.assert_not_called()


def test_wrong_account_cannot_claim_or_publish(store,publish_setup,monkeypatch):
    api,_=publish_setup;monkeypatch.setattr(module,'account_matches',lambda adapter:False)
    before=store.rows('SELECT * FROM pharmacy_stories')
    assert module.publish(store,AT,profile()['site'],api,Mock())=={'status':'account_mismatch'}
    assert store.rows('SELECT * FROM pharmacy_stories')==before
    api.container.assert_not_called()


def test_receipt_and_get_only_membership_are_separate(store,publish_setup):
    api,_=publish_setup
    assert module.publish(store,AT,profile()['site'],api,Mock())['status']=='published'
    api.call.reset_mock()
    assert module.observe(store,AT+timedelta(minutes=1),api)['status']=='propagation_pending'
    api.call.assert_not_called()
    api.call.return_value={'data':[{'id':'2001'}]}
    before=store.rows('SELECT * FROM pharmacy_stories')
    result=module.observe(store,AT+timedelta(minutes=17),api)
    assert set(result['parts'].values())=={'present'} and result['image_pixels_inspected'] is False
    assert store.rows('SELECT * FROM pharmacy_stories')==before
    assert api.call.call_args.args[1]=='GET'
    api.call.reset_mock()
    assert module.observe(store,AT+timedelta(minutes=32),api)['status']=='observation_current'
    api.call.assert_not_called()
    validate_state(store.path)


def test_record_rejects_wrong_city_and_incomplete_published_parts():
    value=bulletin();value['city']='another-city'
    with pytest.raises(ValueError):validate_record((value['date'],json.dumps(value),'prepared',AT.isoformat(),'prepared','[]','[]',None))
    value=bulletin()
    with pytest.raises(ValueError):validate_record((value['date'],json.dumps(value),'published',AT.isoformat(),'published','["1001"]','[]',AT.isoformat()))


def test_source_day_not_a_date_picker_default(monkeypatch):
    from seferihisar import pharmacy_source as source
    monkeypatch.setattr(source,'make_bulletin',lambda entries,day,checked: {'entries':entries,'date':day.isoformat()})
    html=(Path(__file__).parent/'fixtures/pharmacy-isparta.html').read_text(encoding='utf-8')
    with pytest.raises(ValueError):parse_isparta(html.replace('22 Ekim 2026 Bugün','23 Ekim 2026 Bugün'),AT)


def test_current_region_is_not_inferred_from_a_pharmacy_name(monkeypatch):
    from seferihisar import pharmacy_source as source
    monkeypatch.setattr(source,'make_bulletin',lambda entries,day,checked: entries)
    rows=json.loads((Path(__file__).parent/'fixtures/pharmacy-izmir.json').read_text(encoding='utf-8'))
    rows.append({**rows[0],'Adi':'SEFERİHİSAR ECZANESİ','Bolge':'URLA'})
    rows.append({**rows[0],'Adi':'DIŞARIDA ECZANESİ','Bolge':'GÜMÜLDÜR-ÜRKMEZ','Adres':'GÜMÜLDÜR MENDERES CAD. NO:2'})
    parsed=parse_izmir(json.dumps(rows),AT)
    assert len(parsed)==2 and all(e['name']!='DIŞARIDA ECZANESİ' for e in parsed)
