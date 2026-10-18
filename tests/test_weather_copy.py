"""Actual MGM typo regression, legacy media preservation and no-write gates."""
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import ImageDraw

from seferihisar.domain import parse_date
from seferihisar.pipeline import _export
from seferihisar.schedule import prepare
from seferihisar.security import validate_state
from seferihisar.weather import export_weather, parse_forecast, publish_weather, refresh_weather
from seferihisar.weather_copy import VERSION, WeatherTextError, display_condition
from seferihisar.weather_data import SITE, asset_id, validate_forecast
from seferihisar.weather_render import condition_layout, render_weather, scene_for

AT = parse_date('2026-10-18T08:30:00+03:00')


@pytest.fixture
def legacy():
    return json.loads(Path('tests/fixtures/weather-seferihisar-typo.json').read_text(encoding='utf-8'))


def html(forecast):
    stamp = lambda key: parse_date(forecast[key]).strftime('%d.%m.%Y-%H:%M')
    return ('<table><tr><td>Başlangıç</td><td>:'+stamp('period_start')+'</td></tr>'
            '<tr><td>Bitiş</td><td>:'+stamp('period_end')+'</td></tr>'
            '<tr><th>Seferihisar</th><td>'+forecast['condition']+'</td>'
            '<td></td><td>20</td></tr></table>')


def seed(store, forecast, status='prepared', result='prepared'):
    with store.db:
        store.db.execute('INSERT INTO weather_stories(day,forecast,status,checked_at,last_result) VALUES(?,?,?,?,?)',
                         (forecast['date'],json.dumps(forecast,ensure_ascii=False),status,forecast['fetched_at'],result))


def test_real_mgm_typo_is_corrected_only_in_new_display_with_raw_facts_retained(legacy):
    before = deepcopy(legacy)
    forecast = parse_forecast(html(legacy), AT)
    assert forecast['display_version'] == VERSION
    assert forecast['condition'] == 'Parçalı ve az bulutlu, sabah saatlerinde puzlu'
    assert display_condition(forecast) == 'Parçalı ve az bulutlu, sabah saatlerinde puslu'
    assert scene_for(display_condition(forecast)) == 'fog'
    for key in ('place','low','high','period_start','period_end','source_url','date'):
        assert forecast[key] == legacy[key]
    assert legacy == before


@pytest.mark.parametrize('raw,expected', [
    ('Puzlu', 'Puslu'), ('PUZLU', 'PUSLU'), ('yer yer puzlu', 'yer yer puslu'),
    ('Buzlu, yoğun sisli ve kuvvetli rüzgârlı', 'Buzlu, yoğun sisli ve kuvvetli rüzgârlı'),
    ('Pus ve buzlanma; 20 km/sa rüzgâr', 'Pus ve buzlanma; 20 km/sa rüzgâr'),
    ('Bilinmeyen sözcük; puzluluk', 'Bilinmeyen sözcük; puzluluk'),
])
def test_exact_reviewed_spelling_preserves_other_meanings_and_qualifiers(legacy, raw, expected):
    forecast = {**legacy,'condition':raw,'display_version':VERSION}
    assert display_condition(forecast) == expected
    assert forecast['condition'] == raw


def test_legacy_media_identity_and_description_do_not_change(legacy):
    assert asset_id(legacy) == 'ec87eb731aa23ee404c35636'
    assert display_condition(legacy) == legacy['condition']
    assert asset_id({**legacy,'display_version':VERSION}) != asset_id(legacy)


def test_actual_new_jpeg_draws_corrected_words_and_selects_matching_scene(legacy, tmp_path, monkeypatch):
    forecast = {**legacy,'display_version':VERSION}
    values=[]; original=ImageDraw.ImageDraw.text
    def capture(draw, xy, value, **kwargs):
        values.append(value); return original(draw, xy, value, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    scenes=[]
    def scene(description):
        scenes.append(description); return scene_for(description)
    monkeypatch.setattr('seferihisar.weather_render.scene_for',scene)
    target=render_weather(forecast,tmp_path)
    assert (tmp_path/target).exists()
    assert 'puzlu' not in ' '.join(values) and 'puslu' in ' '.join(values)
    assert scenes == [display_condition(forecast)]
    assert '20°' in values and 'None°' not in values and 'En düşük' not in values


@pytest.mark.parametrize('condition', ['Bulutlu 漢', 'W'*230])
def test_unrenderable_or_overflowing_weather_is_isolated_from_other_content(store, legacy, event, source, tmp_path, condition):
    forecast={**legacy,'condition':condition,'display_version':VERSION};seed(store,forecast)
    event.update(start='2026-10-18T14:00:00+03:00',end='2026-10-18T16:00:00+03:00')
    store.upsert(event,AT.isoformat());prepare(store,AT)
    _export(store,tmp_path/'public',[source],AT)
    data=json.loads((tmp_path/'public/data.json').read_text(encoding='utf-8'))
    assert data['weather_story']['status'] == 'blocked'
    assert data['weather_story']['last_result'] == 'forecast_text_unreadable'
    assert 'asset' not in data['weather_story']
    assert any(p['assets'].get('feed') for p in data['posts'] if p['status']=='prepared')
    validate_state(store.path)
    api=Mock();api.enabled.return_value=True
    assert publish_weather(store,AT,SITE,api) == {'status':'forecast_text_unreadable'}
    api.container.assert_not_called();api.session.get.assert_not_called()


@pytest.mark.parametrize('condition', ['123 456', 'Bulutlu...', 'Bulutlu\u202e', 'Bulutlu\nsağanak'])
def test_incomplete_or_invisible_control_text_is_held_without_guessing(legacy, condition):
    with pytest.raises(WeatherTextError):
        display_condition({**legacy,'condition':condition,'display_version':VERSION})


def test_recent_legacy_draft_is_researched_again_instead_of_skipping_copy_review(store, legacy, monkeypatch):
    legacy['fetched_at']=AT.isoformat();seed(store,legacy)
    fetcher=Mock();fetcher.get.return_value=(html(legacy),legacy['source_url'])
    monkeypatch.setattr('seferihisar.weather.now',lambda:AT)
    refresh_weather(store,AT,fetcher)
    fetcher.get.assert_called_once()
    forecast=json.loads(store.rows('SELECT forecast FROM weather_stories')[0]['forecast'])
    assert forecast['display_version']==VERSION and forecast['condition']==legacy['condition']


def test_unclaimed_legacy_weather_cannot_publish_or_export_as_reviewed(store, legacy, tmp_path):
    seed(store,legacy);api=Mock();api.enabled.return_value=True
    assert publish_weather(store,AT,SITE,api)=={'status':'forecast_text_review_required'}
    api.container.assert_not_called();api.session.get.assert_not_called()
    result=export_weather(store,tmp_path,AT)
    assert result['status']=='blocked' and result['last_result']=='forecast_text_review_required'
    assert 'asset' not in result
    assert json.loads(store.rows('SELECT forecast FROM weather_stories')[0]['forecast'])==legacy


def test_legacy_blocked_source_failure_is_not_relabelled_as_copy_failure(store, legacy, tmp_path):
    seed(store,legacy,status='blocked',result='source_timeout');before=store.rows('SELECT * FROM weather_stories')
    assert export_weather(store,tmp_path,AT)['last_result']=='source_timeout'
    assert store.rows('SELECT * FROM weather_stories')==before


@pytest.mark.parametrize('status', ['published','publishing','uncertain'])
def test_old_claims_remain_frozen_and_are_never_replayed(store, legacy, status, monkeypatch, tmp_path):
    seed(store,legacy,status=status);before=store.rows('SELECT * FROM weather_stories')
    fetcher=Mock();refresh_weather(store,AT,fetcher);fetcher.get.assert_not_called()
    api=Mock();api.enabled.return_value=True
    assert publish_weather(store,AT,SITE,api)['status']==('already_published' if status=='published' else 'awaiting_resolution')
    result=export_weather(store,tmp_path,AT)
    assert result['asset_id']==asset_id(legacy) and result['display_condition']==legacy['condition']
    assert store.rows('SELECT * FROM weather_stories')==before
    api.container.assert_not_called();api.session.get.assert_not_called()


@pytest.mark.parametrize('problem',['old_asset','old_text','missing_text'])
def test_wrong_deployed_text_or_legacy_image_is_blocked_before_any_meta_claim(store, legacy, problem):
    forecast={**legacy,'display_version':VERSION};seed(store,forecast)
    media={'forecast':forecast,'asset_id':asset_id(forecast),
           'asset':f'media/{asset_id(forecast)}/story-1.jpg','display_condition':display_condition(forecast)}
    if problem=='old_asset':media.update(asset_id=asset_id(legacy),asset=f'media/{asset_id(legacy)}/story-1.jpg')
    elif problem=='old_text':media['display_condition']=legacy['condition']
    else:media.pop('display_condition')
    api=Mock();api.enabled.return_value=True
    response=Mock(status_code=200,content=b'public JSON');response.json.return_value={'demo':False,'weather_story':media}
    api.session.get.return_value=response
    before=store.rows('SELECT * FROM weather_stories')
    assert publish_weather(store,AT,SITE,api)=={'status':'media_not_deployed'}
    assert store.rows('SELECT * FROM weather_stories')==before
    api.container.assert_not_called();api.session.head.assert_not_called();api.call.assert_not_called()


@pytest.mark.parametrize('version', [None,True,'weather-copy-v2',2])
def test_unknown_presentation_version_is_not_trusted(legacy, version):
    with pytest.raises(ValueError):validate_forecast({**legacy,'display_version':version})
