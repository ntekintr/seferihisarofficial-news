import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import yaml
from PIL import Image

from seferihisar.domain import parse_date
from seferihisar.security import validate_public, validate_state
from seferihisar.weather import export_weather, parse_forecast, publish_weather, refresh_weather, record_result, run_weather
from seferihisar.weather_data import SITE, SOURCE, asset_id, fresh, validate_forecast
from seferihisar.weather_render import display_condition, render_weather, scene_for

MORNING = parse_date('2026-10-16T08:00:00+03:00')
HTML = '''<table><tr><td>Başlangıç</td><td>:15.10.2026-18:00</td></tr>
<tr><td>Bitiş</td><td>:16.10.2026-18:00</td></tr></table>
<table><tr><th>İlçe</th><th>Beklenen Hava</th><th>En Düşük</th><th>En Yüksek</th></tr>
<tr><th>Urla</th><td>Güneşli</td><td>14</td><td>22</td></tr>
<tr><th>Seferihisar</th><td>Parçalı ve çok bulutlu</td><td>12</td><td>20</td></tr></table>'''


def seed(store,forecast=None,status='prepared'):
    forecast = forecast or parse_forecast(HTML,MORNING-timedelta(minutes=20))
    with store.db:
        store.db.execute('INSERT INTO weather_stories(day,forecast,status,checked_at,last_result) VALUES(?,?,?,?,?)',
                         (forecast['date'],json.dumps(forecast),status,forecast['fetched_at'],'prepared'))
    return forecast


def adapter(forecast):
    api = Mock()
    api.enabled.return_value = True
    api.account = '123'
    response = Mock(status_code=200,content=b'public JSON')
    response.json.return_value = {'demo':False,'weather_story':{'forecast':forecast,'display_condition':display_condition(forecast),'asset_id':asset_id(forecast),'asset':f'media/{asset_id(forecast)}/story-1.jpg'}}
    api.session.get.return_value = response
    api.session.head.return_value = Mock(status_code=200,headers={'Content-Type':'image/jpeg'})
    api.container.return_value = '999'
    api.call.return_value = {'id':'111'}
    return api


def test_real_district_row_explicit_period_and_turkish_day():
    value = parse_forecast(HTML,MORNING)
    assert (value['place'],value['low'],value['high']) == ('Seferihisar',12,20)
    assert value['date'] == '2026-10-16' and value['source_url'] == SOURCE
    assert fresh(value,MORNING) and fresh(value,parse_date('2026-10-16T05:10:00Z'))
    assert not fresh(value,MORNING+timedelta(days=1))
    assert not fresh(value,MORNING+timedelta(minutes=91))


@pytest.mark.parametrize('html',[
    HTML.replace('16.10.2026-18:00','15.10.2026-18:00'),
    HTML.replace('16.10.2026-18:00','16.10-18:00'),
    HTML.replace('Seferihisar','İzmir'), HTML+HTML,
    HTML.replace('<td>12</td>','<td>--</td>'),
    HTML.replace('<td>12</td>','<td>25</td>'),
    HTML.replace('Parçalı ve çok bulutlu','api_key=PRIVATE_TEXT_VALUE'),
])
def test_missing_stale_ambiguous_or_wrong_district_forecasts_are_rejected(html):
    with pytest.raises(ValueError):
        value = parse_forecast(html,MORNING)
        from seferihisar.security import assert_no_secrets
        assert_no_secrets(value)


def test_refresh_recovery_and_frozen_claims(store,monkeypatch):
    monkeypatch.setattr('seferihisar.weather.now',lambda:MORNING-timedelta(minutes=20))
    fetcher = Mock();fetcher.get.return_value = (HTML,SOURCE)
    refresh_weather(store,MORNING-timedelta(minutes=20),fetcher)
    validate_state(store.path)
    fetcher.get.side_effect = requests.Timeout('api_key=PRIVATE_EXCEPTION_VALUE')
    monkeypatch.setattr('seferihisar.weather.now',lambda:MORNING)
    refresh_weather(store,MORNING,fetcher)
    assert store.rows('SELECT status,last_result FROM weather_stories') == [{'status':'blocked','last_result':'source_timeout'}]
    assert b'PRIVATE_EXCEPTION_VALUE' not in store.path.read_bytes()
    fetcher.get.side_effect = None
    refresh_weather(store,MORNING,fetcher)
    assert store.rows('SELECT status FROM weather_stories') == [{'status':'prepared'}]
    with store.db:
        store.db.execute("UPDATE weather_stories SET status='uncertain',published_at=?",(MORNING.isoformat(),))
    before = store.rows('SELECT * FROM weather_stories')
    fetcher.reset_mock()
    refresh_weather(store,MORNING,fetcher)
    fetcher.get.assert_not_called()
    assert before == store.rows('SELECT * FROM weather_stories')


@pytest.mark.parametrize('hour',[0,5,9,12,23])
def test_only_morning_refreshes_and_only_eight_oclock_publishes(store,hour):
    forecast = seed(store)
    api = adapter(forecast);fetcher=Mock()
    at=MORNING.replace(hour=hour)
    refresh_weather(store,at,fetcher)
    fetcher.get.assert_not_called()
    assert publish_weather(store,at,SITE,api) == {'status':'outside_window'}
    api.container.assert_not_called();api.session.get.assert_not_called()


def test_claim_is_durable_before_meta_and_one_story_per_day(store):
    forecast=seed(store);api=adapter(forecast)
    news_before=store.rows('SELECT * FROM posts')
    facebook_before=store.rows('SELECT * FROM facebook_deliveries')
    claims=[]
    def checkpoint():
        validate_state(store.path)
        claims.append(store.rows('SELECT status,container_id,media_id FROM weather_stories')[0])
    api.container.side_effect=lambda *a: '999' if claims[0]['status']=='publishing' else pytest.fail('Claim missing')
    assert publish_weather(store,MORNING,SITE,api,checkpoint)=={'status':'published'}
    assert [c['status'] for c in claims] == ['publishing','publishing','published']
    assert api.container.call_args.args[2] is True
    assert publish_weather(store,MORNING+timedelta(minutes=25),SITE,api)=={'status':'already_published'}
    assert api.container.call_count==1 and api.call.call_count==1
    assert store.rows('SELECT * FROM posts')==news_before
    assert store.rows('SELECT * FROM facebook_deliveries')==facebook_before


def test_ambiguous_publish_is_never_replayed_and_persists_no_provider_error(store):
    forecast=seed(store);api=adapter(forecast)
    api.call.side_effect=requests.Timeout('access_token=PRIVATE_PROVIDER_VALUE')
    assert publish_weather(store,MORNING,SITE,api)=={'status':'uncertain'}
    before=store.rows('SELECT * FROM weather_stories')
    assert publish_weather(store,MORNING+timedelta(minutes=10),SITE,api)=={'status':'awaiting_resolution'}
    assert before==store.rows('SELECT * FROM weather_stories')
    assert api.call.call_count==1
    validate_state(store.path)
    assert b'PRIVATE_PROVIDER_VALUE' not in store.path.read_bytes()


@pytest.mark.parametrize('change', ['wrong_forecast','demo','old_media','missing_media','redirect','timeout'])
def test_deployed_manifest_is_required_before_claim(store,change):
    forecast=seed(store);api=adapter(forecast)
    data=api.session.get.return_value.json.return_value
    if change=='wrong_forecast':data['weather_story']['forecast']={**forecast,'high':21}
    elif change=='demo':data['demo']=True
    elif change=='old_media':data['weather_story']['asset']='media/'+'a'*24+'/story-1.jpg'
    elif change=='missing_media':api.session.head.return_value.status_code=404
    elif change=='redirect':api.session.get.return_value.status_code=302
    else:api.session.get.side_effect=requests.Timeout()
    assert publish_weather(store,MORNING,SITE,api)=={'status':'media_not_deployed'}
    assert store.rows('SELECT status FROM weather_stories')==[{'status':'prepared'}]
    api.container.assert_not_called()


def test_stale_or_disabled_forecast_cannot_publish(store):
    forecast=seed(store,parse_forecast(HTML,MORNING-timedelta(hours=2)))
    api=adapter(forecast)
    assert publish_weather(store,MORNING,SITE,api)=={'status':'forecast_stale'}
    api.enabled.return_value=False
    assert publish_weather(store,MORNING,SITE,api)=={'status':'disabled'}
    api.session.get.assert_not_called();api.container.assert_not_called()


def test_missing_or_failed_source_never_uses_yesterday(store):
    api=Mock();api.enabled.return_value=True
    assert publish_weather(store,MORNING,SITE,api)=={'status':'not_ready'}
    seed(store,status='blocked')
    assert publish_weather(store,MORNING,SITE,api)=={'status':'source_unavailable'}
    api.container.assert_not_called()


def test_fingerprint_is_revision_bound_and_export_is_public_safe(store,tmp_path):
    forecast=seed(store)
    assert asset_id(forecast)==asset_id({**forecast,'fetched_at':MORNING.isoformat()})
    assert asset_id(forecast)!=asset_id({**forecast,'high':21})
    target=tmp_path/'public';target.mkdir()
    result=export_weather(store,target,MORNING)
    assert result['asset_id']==asset_id(forecast)
    assert result['forecast']['source_url']==SOURCE
    with Image.open(target/result['asset']) as image:
        assert image.size==(1080,1920) and image.format=='JPEG'
    validate_public(target);validate_state(store.path)
    assert export_weather(store,target,MORNING+timedelta(days=1)) is None


def test_old_two_dimensional_card_cannot_be_claimed_as_the_new_three_dimensional_card(store):
    forecast=seed(store)
    api=adapter(forecast)
    # The actual previous renderer's identity for this exact MGM forecast.
    legacy='9fdc7ce17cda06c3818e6098'
    assert asset_id(forecast)!=legacy
    data=api.session.get.return_value.json.return_value['weather_story']
    data.update(asset_id=legacy,asset=f'media/{legacy}/story-1.jpg')
    assert publish_weather(store,MORNING,SITE,api)=={'status':'media_not_deployed'}
    api.container.assert_not_called()
    assert store.rows('SELECT status FROM weather_stories')==[{'status':'prepared'}]


@pytest.mark.parametrize('field,value',[('low',True),('high',90),('place','Urla'),('source_url','https://example.org/'),('date','2026-10-15'),('fetched_at','2026-10-16T07:00:00')])
def test_durable_state_rejects_wrong_or_private_forecast_fields(store,field,value):
    forecast=parse_forecast(HTML,MORNING)
    forecast[field]=value
    seed(store,forecast)
    with pytest.raises((ValueError,TypeError)):
        validate_state(store.path)


def test_workflow_is_cloud_scheduled_trusted_and_serialized():
    workflow=yaml.load(Path('.github/workflows/weather-story.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['on']['schedule']==[{'cron':'35 4 * * *'},{'cron':'0,17,32,47 5 * * *'}]
    assert 'workflow_dispatch' not in workflow['on']
    assert workflow['concurrency']=={'group':'seferihisar-production','cancel-in-progress':'false'}
    job=workflow['jobs']['weather']
    assert job['environment']=='instagram-production' and job['permissions']=={'contents':'write'}
    assert 'head_repository.full_name == github.repository' in job['if'] and "conclusion == 'success'" in job['if']
    assert job['steps'][0]['with']['ref']=='main'
    assert job['timeout-minutes']=='35'
    assert sum(s.get('run')=='python -m seferihisar.weather --wait-for-morning' for s in job['steps'])==1
    assert job['steps'][-2]['run']=='python -m seferihisar.delivery_audit'
    assert 'FACEBOOK_PAGE_ACCESS_TOKEN' not in str(job)
    assert 'always()' in job['steps'][-1]['if']
    assert job['steps'][-1]['run']=='python -m seferihisar.state_git persist'


@pytest.mark.parametrize('condition,scene',[
    ('Güneşli','sunny'),('Az bulutlu','partly-cloudy'),('Parçalı ve çok bulutlu','partly-cloudy'),
    ('Çok bulutlu','cloudy'),('Kapalı','cloudy'),('Hafif yağmurlu','rain'),
    ('Gök gürültülü sağanak yağışlı','storm'),('Kuvvetli rüzgârlı','wind'),
    ('Kar yağışlı','snow'),('Sulu kar yağışlı','snow'),('Sisli','fog'),('Yağışsız ve güneşli','sunny'),
])
def test_snail_scene_matches_the_forecast(condition,scene):
    assert scene_for(condition)==scene


def test_relative_tomorrow_from_yesterday_bulletin_is_today_on_card():
    forecast=parse_forecast(HTML.replace('Parçalı ve çok bulutlu','Yarın öğleden sonra sağanak yağışlı'),MORNING)
    assert display_condition(forecast)=='bugün öğleden sonra sağanak yağışlı'
    assert forecast['condition']=='Yarın öğleden sonra sağanak yağışlı'


def test_real_daytime_bulletin_recovers_without_inventing_an_overnight_minimum(store,monkeypatch,tmp_path):
    html=Path('tests/fixtures/mgm-seferihisar-daytime.html').read_text(encoding='utf8')
    old=seed(store,status='blocked')
    assert old['low']==12
    fetcher=Mock();fetcher.get.return_value=(html,SOURCE)
    monkeypatch.setattr('seferihisar.weather.now',lambda:MORNING)
    refresh_weather(store,MORNING,fetcher)
    row=store.rows('SELECT * FROM weather_stories')[0]
    forecast=json.loads(row['forecast'])
    assert row['status']=='prepared' and row['last_result']=='prepared'
    assert forecast['low'] is None and forecast['high']==20
    assert forecast['period_start']=='2026-10-16T06:00:00+03:00'
    assert forecast['period_end']=='2026-10-17T06:00:00+03:00'
    assert fresh(forecast,MORNING)
    validate_state(store.path)
    target=tmp_path/'public'
    export_weather(store,target,MORNING)
    validate_public(target)
    api=adapter(forecast)
    assert publish_weather(store,MORNING,SITE,api)=={'status':'published'}
    assert publish_weather(store,MORNING+timedelta(minutes=18),SITE,api)=={'status':'already_published'}
    assert api.container.call_count==1


@pytest.mark.parametrize('low,high',[(None,20),(12,None),(-3,0)])
def test_only_available_temperature_is_drawn_and_absent_value_is_never_printed(store,tmp_path,monkeypatch,low,high):
    forecast=parse_forecast(HTML,MORNING);forecast.update(low=low,high=high)
    import seferihisar.weather_render as renderer
    original=renderer.ImageDraw.ImageDraw.text
    labels=[]
    def text(self,xy,value,*args,**kwargs):
        labels.append(value)
        return original(self,xy,value,*args,**kwargs)
    monkeypatch.setattr(renderer.ImageDraw.ImageDraw,'text',text)
    render_weather(forecast,tmp_path)
    assert 'None°' not in labels
    assert ('En düşük' in labels)==(low is not None)
    assert ('En yüksek' in labels)==(high is not None)
    assert all(str(value)+'°' in labels for value in (low,high) if value is not None)


def test_two_missing_temperatures_and_ambiguous_invalid_values_still_block():
    with pytest.raises(ValueError):
        parse_forecast(HTML.replace('<td>12</td>','<td></td>').replace('<td>20</td>','<td></td>'),MORNING)
    forecast=parse_forecast(HTML,MORNING)
    for changes in ({'low':None,'high':None},{'low':None,'high':True},{'low':None,'high':'20'}):
        with pytest.raises(ValueError):validate_forecast({**forecast,**changes})


@pytest.mark.parametrize('error,code',[
    (requests.Timeout('PRIVATE_REQUEST'),'source_timeout'),
    (requests.exceptions.SSLError('PRIVATE_REQUEST'),'source_tls_failed'),
    (requests.HTTPError('PRIVATE_REQUEST'),'source_http_error'),
    (requests.ConnectionError('PRIVATE_REQUEST'),'source_connection_failed'),
    (requests.RequestException('PRIVATE_REQUEST'),'source_unavailable'),
    (ValueError('robots.txt disallows this path'),'source_robots_denied'),
    (ValueError('PRIVATE_REQUEST'),'forecast_invalid'),
])
def test_failure_reason_survives_late_runs_without_saving_provider_text(store,monkeypatch,error,code):
    seed(store)
    monkeypatch.setattr('seferihisar.weather.now',lambda:MORNING)
    fetcher=Mock();fetcher.get.side_effect=error
    refresh_weather(store,MORNING,fetcher)
    before=store.rows('SELECT * FROM weather_stories')
    assert before[0]['last_result']==code
    api=adapter(json.loads(before[0]['forecast']))
    assert publish_weather(store,MORNING,SITE,api)=={'status':code}
    api.container.assert_not_called()
    record_result(store,'2026-10-16',{'status':'outside_window'})
    assert store.rows('SELECT * FROM weather_stories')==before
    validate_state(store.path)
    assert b'PRIVATE_REQUEST' not in store.path.read_bytes()


class MorningClock:
    def __init__(self,at):
        self.at,self.sleeps = at,[]

    def now(self):
        return self.at

    def sleep(self,seconds):
        self.sleeps.append(seconds)
        self.at += timedelta(seconds=seconds)


@pytest.mark.parametrize('early',['2026-10-16T07:35:00+03:00','2026-10-16T07:41:38+03:00',
                                  '2026-10-16T04:59:59Z'])
def test_early_ready_runner_waits_without_a_claim_then_rechecks_at_eight(store,early):
    forecast=seed(store);api=adapter(forecast);clock=MorningClock(parse_date(early))
    before=store.rows('SELECT * FROM weather_stories')
    original_sleep=clock.sleep
    def sleep(seconds):
        assert store.rows('SELECT * FROM weather_stories')==before
        api.container.assert_not_called();api.call.assert_not_called()
        original_sleep(seconds)
    claims=[]
    def checkpoint():
        assert clock.at==MORNING
        validate_state(store.path)
        claims.append(store.rows('SELECT status FROM weather_stories')[0]['status'])
    result=run_weather(store,SITE,api,checkpoint,wait_for_morning=True,clock=clock.now,sleeper=sleep)
    assert result=={'status':'published'}
    assert sum(clock.sleeps)==(MORNING-parse_date(early)).total_seconds()
    assert max(clock.sleeps)<=30
    assert api.session.get.call_count==2 and api.session.head.call_count==2
    assert claims==['publishing','publishing','published']
    assert store.rows('SELECT published_at FROM weather_stories')==[{'published_at':MORNING.isoformat()}]
    assert run_weather(store,SITE,api,wait_for_morning=True,clock=clock.now,sleeper=sleep)=={'status':'already_published'}
    assert api.container.call_count==1 and api.call.call_count==1


@pytest.mark.parametrize('at,wait,status',[
    ('2026-10-16T07:34:59+03:00',True,'outside_window'),
    ('2026-10-16T07:41:00+03:00',False,'outside_window'),
    ('2026-10-16T08:00:00+03:00',True,'published'),
    ('2026-10-16T08:21:00+03:00',True,'published'),
    ('2026-10-16T08:59:59+03:00',True,'published'),
    ('2026-10-16T09:00:00+03:00',True,'outside_window'),
])
def test_wait_is_opt_in_bounded_and_preserves_the_existing_publication_window(store,at,wait,status):
    stamp=parse_date(at)
    forecast=seed(store,parse_forecast(HTML,stamp-timedelta(minutes=5)))
    api=adapter(forecast);sleeper=Mock()
    assert run_weather(store,SITE,api,wait_for_morning=wait,clock=lambda:stamp,sleeper=sleeper)=={'status':status}
    sleeper.assert_not_called()
    assert api.container.call_count==(status=='published')


@pytest.mark.parametrize('failure,status',[
    ('missing','not_ready'),('disabled','disabled'),('blocked','source_timeout'),
    ('old_at_eight','forecast_stale'),('legacy','forecast_text_review_required'),
    ('undeployed','media_not_deployed'),('published','already_published'),
    ('publishing','awaiting_resolution'),('uncertain','awaiting_resolution'),
])
def test_unready_or_claimed_early_job_releases_the_production_lock_without_waiting(store,failure,status):
    forecast=parse_forecast(HTML,MORNING-timedelta(minutes=20))
    if failure=='old_at_eight':
        forecast['fetched_at']=(MORNING-timedelta(minutes=91)).isoformat()
        assert fresh(forecast,MORNING-timedelta(minutes=19))
    if failure=='legacy':forecast.pop('display_version')
    if failure!='missing':
        seed(store,forecast,status=failure if failure in ('blocked','published','publishing','uncertain') else 'prepared')
    if failure=='blocked':
        with store.db:store.db.execute("UPDATE weather_stories SET last_result='source_timeout'")
    before=store.rows('SELECT * FROM weather_stories')
    api=adapter(forecast);sleeper=Mock()
    if failure=='disabled':api.enabled.return_value=False
    if failure=='undeployed':api.session.head.return_value.status_code=404
    assert run_weather(store,SITE,api,wait_for_morning=True,clock=lambda:MORNING-timedelta(minutes=19),sleeper=sleeper)=={'status':status}
    assert store.rows('SELECT * FROM weather_stories')==before
    sleeper.assert_not_called();api.container.assert_not_called();api.call.assert_not_called()


@pytest.mark.parametrize('change,status',[('media','media_not_deployed'),('claim','awaiting_resolution'),
                                         ('late','outside_window'),('day','outside_window')])
def test_wakeup_rechecks_manifest_claim_and_clock_before_any_meta_write(store,change,status):
    forecast=seed(store);api=adapter(forecast);clock=MorningClock(MORNING-timedelta(minutes=19))
    def sleep(seconds):
        assert seconds<=30
        clock.at=MORNING
        if change=='media':api.session.head.return_value.status_code=404
        elif change=='claim':
            with store.db:store.db.execute("UPDATE weather_stories SET status='uncertain'")
        elif change=='late':clock.at=MORNING+timedelta(hours=1)
        else:clock.at=MORNING+timedelta(days=1)
    assert run_weather(store,SITE,api,wait_for_morning=True,clock=clock.now,sleeper=sleep)=={'status':status}
    assert store.rows('SELECT status FROM weather_stories')==[{'status':'uncertain' if change=='claim' else 'prepared'}]
    api.container.assert_not_called();api.call.assert_not_called()


def test_clock_stall_cannot_hold_production_beyond_the_bounded_wait(store):
    forecast=seed(store);api=adapter(forecast);sleeper=Mock()
    before=store.rows('SELECT * FROM weather_stories')
    result=run_weather(store,SITE,api,wait_for_morning=True,clock=lambda:MORNING-timedelta(minutes=19),sleeper=sleeper)
    assert result=={'status':'outside_window'}
    assert sum(c.args[0] for c in sleeper.call_args_list)==25*60
    assert store.rows('SELECT * FROM weather_stories')==before
    api.container.assert_not_called();api.call.assert_not_called()
