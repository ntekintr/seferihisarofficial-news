"""GET-only checks using existing credentials; never reauthorization/publication."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from .domain import now


class CheckError(Exception):
    pass


def get(session, base, path, token, fields):
    try:
        response = session.get(base + '/' + path, params={'fields': fields},
            headers={'Authorization': 'Bearer ' + token}, timeout=(8, 20), allow_redirects=False)
        body = response.json()
        error = body.get('error', {}) if isinstance(body, dict) else {}
        code = error.get('code') if isinstance(error, dict) else None
        if code == 190:
            raise CheckError('credential_invalid')
        if code in (10, 200):
            raise CheckError('permission_required')
        if code in (4, 17, 32, 613) or response.status_code == 429:
            raise CheckError('rate_limited')
        if not response.ok or 300 <= response.status_code < 400 or not isinstance(body, dict) or 'error' in body:
            raise CheckError('read_failed')
        return body
    except requests.Timeout:
        raise CheckError('timeout') from None
    except (requests.RequestException, ValueError):
        raise CheckError('read_failed') from None


def check(environ=None, session=None):
    env = os.environ if environ is None else environ
    session = session or requests.Session()
    version = env.get('META_GRAPH_VERSION', 'v26.0')
    account, token = env.get('INSTAGRAM_USER_ID', ''), env.get('INSTAGRAM_ACCESS_TOKEN', '')
    result = {'checked_at': now().isoformat(), 'instagram': 'settings_missing',
              'facebook': 'disabled', 'expiry': 'not_checked', 'publication_attempted': False}
    if not re.fullmatch(r'v\d+\.0', version):
        return result
    base = 'https://graph.facebook.com/' + version
    if token and re.fullmatch(r'\d{1,32}', account):
        try:
            identity = get(session, base, account, token, 'id,username')
            if identity.get('id') != account or identity.get('username') != 'seferihisarofficial':
                raise CheckError('account_mismatch')
            quota = get(session, base, account + '/content_publishing_limit', token, 'quota_usage,config')
            rows = quota.get('data')
            if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or type(rows[0].get('quota_usage')) is not int or rows[0]['quota_usage'] < 0:
                raise CheckError('quota_unverified')
            result.update(instagram='connected', quota_usage=rows[0]['quota_usage'])
        except CheckError as exc:
            result['instagram'] = str(exc)
    if env.get('FACEBOOK_PUBLISH_ENABLED') == 'true':
        page, page_token = env.get('FACEBOOK_PAGE_ID', ''), env.get('FACEBOOK_PAGE_ACCESS_TOKEN', '')
        result['facebook'] = 'settings_missing'
        if page_token and re.fullmatch(r'\d{1,32}', page) and re.fullmatch(r'\d{1,32}', account):
            try:
                identity = get(session, base, 'me', page_token, 'id,instagram_business_account')
                linked = identity.get('instagram_business_account')
                if identity.get('id') != page or not isinstance(linked, dict) or linked.get('id') != account:
                    raise CheckError('account_mismatch')
                result['facebook'] = 'connected'
            except CheckError as exc:
                result['facebook'] = str(exc)
    return result


def main():
    result = check()
    target = Path('work/connection-health/summary.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    if output := os.getenv('GITHUB_STEP_SUMMARY'):
        with Path(output).open('a', encoding='utf-8') as file:
            file.write('### Meta bağlantı kontrolü — yalnız okuma\n\n```json\n' + json.dumps(result, indent=2) + '\n```\n\n')
            file.write('Bu test bağlantının şu anda okunabildiğini doğrular. Gelecekteki anahtar bitiş tarihi veya paylaşım yetkisinin tamamı bu testle doğrulanmaz. Yayın yapılmaz, izin veya anahtar değiştirilmez.\n')
    print(json.dumps(result))
    if result['instagram'] != 'connected' or result['facebook'] not in ('connected', 'disabled'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
