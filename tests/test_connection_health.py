import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
import yaml
from pathlib import Path

from seferihisar.connection_health import check

ENV = {'INSTAGRAM_USER_ID':'1234', 'INSTAGRAM_ACCESS_TOKEN':'PRIVATE_IG_CREDENTIAL',
       'FACEBOOK_PUBLISH_ENABLED':'true', 'FACEBOOK_PAGE_ID':'5678',
       'FACEBOOK_PAGE_ACCESS_TOKEN':'PRIVATE_FB_CREDENTIAL'}


def response(body, status=200):
    return SimpleNamespace(json=lambda: body, ok=200 <= status < 300, status_code=status)


def test_checks_existing_identities_using_get_only_without_printing_identifiers():
    session = Mock()
    session.get.side_effect = [response({'id':'1234','username':'seferihisarofficial'}),
        response({'data':[{'quota_usage':3}]}), response({'id':'5678','instagram_business_account':{'id':'1234'}})]
    result = check(ENV, session)
    assert result['instagram'] == result['facebook'] == 'connected'
    assert result['quota_usage'] == 3 and result['expiry'] == 'not_checked'
    assert result['publication_attempted'] is False
    assert 'PRIVATE_' not in json.dumps(result) and '1234' not in json.dumps(result)
    assert not session.post.called and not session.request.called
    for call in session.get.call_args_list:
        assert call.kwargs['allow_redirects'] is False
        assert set(call.kwargs['params']) == {'fields'}
        assert 'PRIVATE_' not in call.args[0]


@pytest.mark.parametrize('body,status,expected', [
    ({'error':{'code':190,'message':'PRIVATE_BODY'}},400,'credential_invalid'),
    ({'error':{'code':200}},403,'permission_required'),
    ({'error':{'code':4}},400,'rate_limited'), ({},429,'rate_limited'),
    ({},302,'read_failed'), ([],200,'read_failed'),
    ({'id':'9999','username':'wrong'},200,'account_mismatch'),
])
def test_controlled_failure_codes_never_include_provider_text(body, status, expected):
    session=Mock(); session.get.return_value=response(body,status)
    result=check({**ENV,'FACEBOOK_PUBLISH_ENABLED':'false'},session)
    assert result['instagram']==expected
    assert 'PRIVATE_' not in json.dumps(result)
    assert session.get.call_count==1


@pytest.mark.parametrize('error,expected', [(requests.Timeout('PRIVATE_EXCEPTION'),'timeout'),
    (requests.ConnectionError('PRIVATE_EXCEPTION'),'read_failed'), (ValueError('PRIVATE_EXCEPTION'),'read_failed')])
def test_network_failures_are_controlled(error, expected):
    session=Mock(); session.get.side_effect=error
    result=check({**ENV,'FACEBOOK_PUBLISH_ENABLED':'false'},session)
    assert result['instagram']==expected and 'PRIVATE_' not in json.dumps(result)


def test_missing_settings_do_not_make_requests():
    session=Mock()
    assert check({},session)['instagram']=='settings_missing'
    session.get.assert_not_called()


def test_daily_preflight_is_main_only_read_only_and_keeps_a_safe_report():
    text=Path('.github/workflows/instagram-connection-check.yml').read_text(encoding='utf-8')
    workflow=yaml.load(text,Loader=yaml.BaseLoader)
    assert workflow['on']['schedule'][0]['cron']=='10 5 * * *'
    assert workflow['permissions']=={'contents':'read'}
    assert workflow['jobs']['connection']['if']=="github.ref == 'refs/heads/main'"
    assert 'state_git persist' not in text and 'cli publish' not in text
    assert 'connection_health' in text
    artifact=workflow['jobs']['connection']['steps'][-1]
    assert artifact['if']=='always()' and artifact['with']['path']=='work/connection-health/summary.json'
