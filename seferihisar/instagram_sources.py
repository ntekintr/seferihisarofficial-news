"""GET-only public professional-account captions, isolated from the publisher.

Never follow Graph pagination URLs, download media, scrape a login, or persist
an API response. Only a validated public item/health manifest leaves this job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from .collect import MONTHS, labelled_event, safe_url
from .domain import TZ, canonical, category, local, now, parse_date
from .editor import verify
from .security import ITEM_FIELDS, assert_no_secrets, contains_secret

MAX_MANIFEST_BYTES = 500_000
MAX_MEDIA = 12
ERROR_CODES = {
    'instagram_credentials_missing', 'instagram_token_expired',
    'instagram_permission_required', 'instagram_rate_limited',
    'instagram_source_unavailable', 'instagram_read_failed',
    'instagram_manifest_missing', 'instagram_manifest_invalid',
}


class SourceReadError(Exception):
    def __init__(self, code):
        self.code = code if code in ERROR_CODES else 'instagram_read_failed'
        super().__init__(self.code)


def username(source: dict) -> str:
    value = source.get('instagram_username')
    if (not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9._]{1,30}', value)
            or value.casefold() == 'seferihisarofficial'
            or source.get('url') != 'https://www.instagram.com/' + value + '/'):
        raise SourceReadError('instagram_source_unavailable')
    return value


def read_account(source: dict, token: str, owner_id: str, version: str, session) -> dict:
    target = username(source)
    if not token or not re.fullmatch(r'\d{8,32}', owner_id):
        raise SourceReadError('instagram_credentials_missing')
    if not re.fullmatch(r'v\d{1,2}\.0', version):
        raise SourceReadError('instagram_read_failed')
    fields = 'business_discovery.username(' + target + '){username,media.limit(12){id,caption,permalink,timestamp}}'
    try:
        endpoint = safe_url('https://graph.facebook.com/' + version + '/' + owner_id,
                            {'graph.facebook.com'})
        response = session.get(endpoint, params={'fields': fields},
                               headers={'Authorization': 'Bearer ' + token},
                               timeout=(8, 15), allow_redirects=False, stream=True)
        try:
            # A redirect is never followed with this credential.
            if 300 <= response.status_code < 400:
                raise SourceReadError('instagram_read_failed')
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > MAX_MANIFEST_BYTES:
                    raise SourceReadError('instagram_read_failed')
            data = json.loads(body)
            if not isinstance(data, dict):
                raise SourceReadError('instagram_read_failed')
            error = data.get('error')
            if isinstance(error, dict):
                code = error.get('code')
                kind = {190:'instagram_token_expired', 10:'instagram_permission_required',
                        200:'instagram_permission_required', 4:'instagram_rate_limited',
                        17:'instagram_rate_limited', 32:'instagram_rate_limited',
                        613:'instagram_rate_limited', 100:'instagram_source_unavailable'}.get(code, 'instagram_read_failed')
                raise SourceReadError(kind)
            if response.status_code != 200:
                raise SourceReadError('instagram_read_failed')
            account = data.get('business_discovery')
            if not isinstance(account, dict) or account.get('username', '').casefold() != target.casefold():
                raise SourceReadError('instagram_source_unavailable')
            return account
        finally:
            response.close()
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        raise SourceReadError('instagram_read_failed') from None


def caption_items(account: dict, source: dict, at: datetime) -> list[dict]:
    media = account.get('media')
    rows = media.get('data') if isinstance(media, dict) else None
    if not isinstance(rows, list):
        raise SourceReadError('instagram_read_failed')
    items = []
    for row in rows[:MAX_MEDIA]:
        if not isinstance(row, dict):
            continue
        caption, link, stamp = (row.get(k) for k in ('caption', 'permalink', 'timestamp'))
        published = parse_date(stamp)
        if not isinstance(caption, str) or not isinstance(link, str) or not published:
            continue
        if not 40 <= len(caption) <= 3000 or contains_secret(caption):
            continue
        parts = urlsplit(link)
        if (parts.scheme != 'https' or parts.hostname not in ('www.instagram.com', 'instagram.com')
                or parts.username or parts.password or parts.port not in (None, 443)
                or parts.query or not re.fullmatch(r'/(?:p|reel)/[a-zA-Z0-9_-]{5,40}/?', parts.path)):
            continue
        url = 'https://www.instagram.com' + parts.path.rstrip('/') + '/'
        # Source hashtag campaigns are not evidence of the occurrence's location.
        prose = re.sub(r'#\w+|https?://\S+', '', caption).strip()
        if not local(prose):
            continue
        title = re.split(r'[\n.!?]', prose, maxsplit=1)[0].strip(' :–—')[:240]
        if len(title) < 8:
            continue
        item = {'kind':'news', 'title':title, 'description':prose,
                'url':url, 'identity':canonical(url), 'source_id':source['id'],
                'source_name':source['name'], 'category':category(prose),
                'published_at':published.isoformat(), 'sources':[url]}
        if item['category'] in ('outage','weather'):
            expiry = service_expiry(prose)
            if not expiry:
                continue
            item['valid_until'] = expiry.isoformat()
        if source['id']=='instagram-afad' and re.search(r'(?i)\bdeprem\w*',prose):
            item['valid_until'] = (published+timedelta(hours=3)).isoformat()
        # For event invitations the post timestamp is not the event date.
        invitation = re.search(r'(?i)\b(?:bilet|rezervasyon|bekliyoruz|katılın|başlayacak|gerçekleşecek)\b|\bsaat\s*:', prose)
        if invitation and item['category'] in ('concert','theatre','festival','cinema','culture','family','event','market','education','sport','food'):
            html = BeautifulSoup('<article></article>', 'html.parser')
            for line in prose.splitlines():
                paragraph = html.new_tag('p')
                paragraph.string = line
                html.article.append(paragraph)
            event = labelled_event(title, prose, html.article, url, source)
            if not event:
                continue
            item = event
        if verify(item, source, at) is None:
            items.append(item)
    return items


def service_expiry(prose: str) -> datetime | None:
    """Only an explicit full-year day and same-day clock range; no year inference."""
    numeric = re.findall(r'(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)',prose)
    named = re.findall(r'(?<!\d)(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})(?!\d)',prose,re.I)
    dates = {(int(y),int(m),int(d)) for d,m,y in numeric}
    dates.update((int(y),MONTHS[m.casefold()],int(d)) for d,m,y in named)
    hours = set(re.findall(r'(?<![\d.])(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})(?![\d.])',prose))
    if len(dates)!=1 or len(hours)!=1:
        return None
    y,m,d = next(iter(dates));first_h,first_m,last_h,last_m = map(int,next(iter(hours)))
    try:
        start = datetime(y,m,d,first_h,first_m,tzinfo=TZ)
        end = datetime(y,m,d,last_h,last_m,tzinfo=TZ)
    except ValueError:
        return None
    return end if end>start else None


def instagram_sources(sources):
    return [s for s in sources if s.get('enabled') and s.get('trusted')
            and s.get('kind') == 'instagram_api' and s.get('access') == 'api']


def manifest(sources: list[dict], at: datetime, session=None) -> dict:
    selected = instagram_sources(sources)
    if len(selected) > 20:
        raise ValueError('Too many Instagram sources')
    token, owner = os.getenv('IG_SOURCE_ACCESS_TOKEN', ''), os.getenv('IG_SOURCE_USER_ID', '')
    version = os.getenv('META_GRAPH_VERSION', 'v25.0')
    client = session or requests.Session()
    if session is None:
        client.trust_env = False
    result = {'schema_version':1, 'generated_at':at.isoformat(), 'items':[], 'health':[]}
    stop = None
    try:
        for source in selected:
            code, found = stop, []
            if not stop:
                try:
                    found = caption_items(read_account(source, token, owner, version, client), source, at)
                except SourceReadError as exc:
                    code = exc.code
                    if code in ('instagram_credentials_missing','instagram_token_expired','instagram_permission_required','instagram_rate_limited'):
                        stop = code
            result['items'].extend(found)
            result['health'].append({'source_id':source['id'], 'checked_at':now().isoformat(),
                                     'status':'failed' if code else ('ok' if found else 'empty'),
                                     'code':code, 'parsed':len(found)})
        assert_no_secrets(result)
        validate_manifest(result, selected, now())
        return result
    finally:
        if session is None:
            client.close()


def validate_manifest(data: dict, sources: list[dict], at: datetime):
    expected = {s['id']:s for s in instagram_sources(sources)}
    if (not isinstance(data, dict) or set(data) != {'schema_version','generated_at','items','health'}
            or data['schema_version'] != 1 or not isinstance(data['items'], list)
            or not isinstance(data['health'], list) or len(data['items']) > len(expected) * MAX_MEDIA
            or len(data['health']) != len(expected)):
        raise ValueError('Invalid public Instagram manifest')
    assert_no_secrets(data)
    generated = parse_date(data['generated_at'])
    if not generated or not at - timedelta(hours=1) <= generated <= at + timedelta(minutes=5):
        raise ValueError('Stale public Instagram manifest')
    seen = set()
    for row in data['health']:
        if not isinstance(row, dict) or set(row) != {'source_id','checked_at','status','code','parsed'}:
            raise ValueError('Invalid Instagram health')
        sid, checked = row['source_id'], parse_date(row['checked_at'])
        if sid not in expected or sid in seen or not checked or not generated <= checked <= at + timedelta(minutes=5):
            raise ValueError('Unexpected Instagram source')
        seen.add(sid)
        if type(row['parsed']) is not int or not 0 <= row['parsed'] <= MAX_MEDIA:
            raise ValueError('Invalid Instagram counters')
        if row['status'] not in ('ok','empty','failed') or row['code'] not in (None, *ERROR_CODES):
            raise ValueError('Invalid Instagram status')
        if (row['status'] == 'failed') != bool(row['code']) or (row['status'] == 'empty' and row['parsed']):
            raise ValueError('Conflicting Instagram health')
        found = [i for i in data['items'] if isinstance(i, dict) and i.get('source_id') == sid]
        if len(found) != row['parsed'] or (row['status'] == 'failed' and found):
            raise ValueError('Conflicting Instagram counters')
    for item in data['items']:
        source = expected.get(item.get('source_id')) if isinstance(item, dict) else None
        if not source or not set(item) <= ITEM_FIELDS or verify(item, source, at) is not None:
            raise ValueError('Unverified Instagram item')
        parts = urlsplit(item['url'])
        if (parts.query or parts.fragment or not re.fullmatch(r'/(?:p|reel)/[a-zA-Z0-9_-]{5,40}/', parts.path)
                or item.get('identity') != canonical(item['url']) or item.get('sources') != [item['url']]):
            raise ValueError('Invalid Instagram permalink')


def consume(path: Path | None, sources: list[dict], at: datetime):
    selected = instagram_sources(sources)
    code = 'instagram_manifest_missing'
    if path and path.exists():
        try:
            if path.is_symlink() or path.stat().st_size > MAX_MANIFEST_BYTES:
                raise ValueError('Oversized Instagram manifest')
            data = json.loads(path.read_text(encoding='utf-8'))
            validate_manifest(data, selected, at)
            return data['items'], data['health']
        except (OSError, ValueError, TypeError, AttributeError):
            code = 'instagram_manifest_invalid'
    return [], [{'source_id':s['id'], 'checked_at':at.isoformat(),
                 'status':'failed', 'parsed':0, 'code':code} for s in selected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path, default=Path('config/sources.json'))
    parser.add_argument('--output', type=Path, default=Path('work/instagram-sources/public.json'))
    args = parser.parse_args()
    try:
        data = manifest(json.loads(args.sources.read_text(encoding='utf-8')), now())
        encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest too large')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
        print(json.dumps({'sources':len(data['health']), 'accepted':len(data['items']),
                          'checks':data['health']}, ensure_ascii=False))
    except (OSError, ValueError, TypeError):
        raise SystemExit('Instagram source check failed; no response or credential exported.') from None


if __name__ == '__main__':
    main()
