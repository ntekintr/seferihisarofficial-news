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
from seferihisar.weather import export_weather, parse_forecast, publish_weather, refresh_weather
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
    response.json.return_value = {'demo':False,'weather_story':{'forecast':forecast,'asset_id':asset_id(forecast),'asset':f'media/{asset_id(forecast)}/story-1.jpg'}}
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
    assert store.rows('SELECT status,last_result FROM weather_stories') == [{'status':'blocked','last_result':'source_unavailable'}]
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


@pytest.mark.parametrize('field,value',[('low',True),('high',90),('place','Urla'),('source_url','https://example.org/'),('date','2026-10-15'),('fetched_at','2026-10-16T07:00:00')])
def test_durable_state_rejects_wrong_or_private_forecast_fields(store,field,value):
    forecast=parse_forecast(HTML,MORNING)
    forecast[field]=value
    seed(store,forecast)
    with pytest.raises((ValueError,TypeError)):
        validate_state(store.path)


def test_workflow_is_cloud_scheduled_trusted_and_serialized():
    workflow=yaml.load(Path('.github/workflows/weather-story.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['on']['schedule']==[{'cron':'0 5 * * *'}]
    assert 'workflow_dispatch' not in workflow['on']
    assert workflow['concurrency']=={'group':'seferihisar-production','cancel-in-progress':'false'}
    job=workflow['jobs']['weather']
    assert job['environment']=='instagram-production' and job['permissions']=={'contents':'write'}
    assert 'head_repository.full_name == github.repository' in job['if'] and "conclusion == 'success'" in job['if']
    assert job['steps'][0]['with']['ref']=='main'
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
