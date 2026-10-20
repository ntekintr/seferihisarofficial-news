"""Daily GET-only feedback. Raw account measurements never enter public state."""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

from .domain import CATEGORIES, now, parse_date

VERSION = 'topic-feedback-v1'
STATUSES = {'ready', 'insufficient_data', 'settings_missing', 'credential_invalid',
            'permission_required', 'rate_limited', 'read_failed', 'account_mismatch'}
METRICS = ('reach', 'saved', 'shares', 'total_interactions')


def validate_profile(value):
    if not isinstance(value, dict) or set(value) != {'version', 'checked_at', 'status', 'weights'}:
        raise ValueError('Invalid learning profile')
    if value['version'] != VERSION or value['status'] not in STATUSES:
        raise ValueError('Invalid learning result')
    if datetime.fromisoformat(value['checked_at']).tzinfo is None:
        raise ValueError('Invalid learning timestamp')
    weights = value['weights']
    if (not isinstance(weights, dict) or not set(weights) <= set(CATEGORIES)
            or any(type(n) is not int or n not in (0, 1) for n in weights.values())
            or (value['status'] != 'ready' and weights)):
        raise ValueError('Invalid topic weights')
    return value


def profile(store, at):
    row = store.rows("SELECT payload FROM learning_profile WHERE id='instagram'")
    if row:
        value = validate_profile(json.loads(row[0]['payload']))
        stamp = parse_date(value['checked_at'])
        if at - timedelta(days=3) <= stamp <= at + timedelta(minutes=5):
            return value
    return {'version': VERSION, 'checked_at': at.isoformat(), 'status': 'insufficient_data', 'weights': {}}


class ReadError(Exception):
    pass


def read(session, base, path, token, params):
    import requests
    try:
        response = session.get(base + '/' + path, params=params,
                               headers={'Authorization': 'Bearer ' + token},
                               timeout=(5, 8), allow_redirects=False)
        value = response.json()
        error = value.get('error', {}) if isinstance(value, dict) else {}
        code = error.get('code') if isinstance(error, dict) else None
        if code == 190:
            raise ReadError('credential_invalid')
        if code in (10, 200):
            raise ReadError('permission_required')
        if code in (4, 17, 32, 613) or response.status_code == 429:
            raise ReadError('rate_limited')
        if not response.ok or response.status_code >= 300 or not isinstance(value, dict) or error:
            raise ReadError('read_failed')
        return value
    except (requests.RequestException, ValueError):
        raise ReadError('read_failed') from None


def measurements(value):
    """Missing, conflicting or partial counters are unavailable, never zero."""
    rows = value.get('data')
    if not isinstance(rows, list):
        raise ReadError('read_failed')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('name') not in METRICS or row['name'] in result:
            raise ReadError('read_failed')
        values = row.get('values')
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise ReadError('read_failed')
        count = values[0].get('value')
        if type(count) is not int or not 0 <= count <= 1_000_000_000:
            raise ReadError('read_failed')
        result[row['name']] = count
    if set(result) != set(METRICS):
        raise ReadError('read_failed')
    return result


def weights_for(samples):
    """Conservative engagement/reach preference, never a claim of causation.

    At least ten distinct posts, two adequately represented topics and a
    minimum of three posts/100 reached accounts per topic. Small samples do
    not invent a winner. Cumulative measurements are not called exact 24h/7d.
    """
    groups = defaultdict(list)
    for category, metric in samples:
        if category in CATEGORIES and metric['reach'] > 0:
            groups[category].append(metric)
    eligible = {k: v for k, v in groups.items() if len(v) >= 3 and sum(m['reach'] for m in v) >= 100}
    if sum(len(v) for v in groups.values()) < 10 or len(eligible) < 2:
        return {}
    def score(rows):
        # total_interactions already includes saves/shares; the additional
        # weight deliberately values those actions, not additional people.
        return (sum(m['total_interactions'] + m['saved'] + m['shares'] for m in rows) + 2) / (sum(m['reach'] for m in rows) + 100)
    baseline = score([m for rows in eligible.values() for m in rows])
    return {category: int(score(rows) >= baseline * 1.25) for category, rows in eligible.items()}


def refresh(store, at=None, *, environ=None, session=None):
    at = at or now()
    previous = store.rows("SELECT payload FROM learning_profile WHERE id='instagram'")
    if previous:
        value = validate_profile(json.loads(previous[0]['payload']))
        stamp = parse_date(value['checked_at'])
        if timedelta(0) <= at - stamp and (at.date() == stamp.astimezone(at.tzinfo).date() or at - stamp < timedelta(hours=20)):
            return value  # Research-run backups do not repeat today's reads.
    env = os.environ if environ is None else environ
    token, account = env.get('INSTAGRAM_ACCESS_TOKEN', ''), env.get('INSTAGRAM_USER_ID', '')
    version = env.get('META_GRAPH_VERSION', 'v26.0')
    result = {'version': VERSION, 'checked_at': at.isoformat(), 'status': 'settings_missing', 'weights': {}}
    if token and re.fullmatch(r'\d{1,32}', account) and re.fullmatch(r'v\d+\.0', version):
        import requests
        session = session or requests.Session()
        base = 'https://graph.facebook.com/' + version
        try:
            identity = read(session, base, account, token, {'fields': 'id,username'})
            if identity.get('id') != account or identity.get('username') != 'seferihisarofficial':
                raise ReadError('account_mismatch')
            # Only known automated feed claims present on this exact account.
            own = read(session, base, account + '/media', token, {'fields': 'id', 'limit': 100})
            rows = own.get('data')
            if not isinstance(rows, list) or any(not isinstance(r, dict) or not re.fullmatch(r'\d{1,32}', r.get('id', '')) for r in rows):
                raise ReadError('read_failed')
            own_ids = {r['id'] for r in rows}
            samples, seen = [], set()
            claims = sorted(store.posts(), key=lambda p: p.get('published_at', ''), reverse=True)
            for post in claims:
                stamp = parse_date(post.get('published_at'))
                media = post.get('media_id')
                if (post['status'] != 'published' or post.get('publish_format') or not post.get('item_id')
                        or media not in own_ids or media in seen or not stamp
                        or not timedelta(days=1) <= at - stamp <= timedelta(days=14)):
                    continue
                seen.add(media)
                value = read(session, base, media + '/insights', token,
                             {'metric': ','.join(METRICS), 'period': 'lifetime'})
                samples.append((post['category'], measurements(value)))
                if len(samples) >= 20:
                    break
            result['weights'] = weights_for(samples)
            result['status'] = 'ready' if result['weights'] else 'insufficient_data'
        except ReadError as exc:
            result.update(status=str(exc), weights={})
    validate_profile(result)
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO learning_profile VALUES (?,?)',
                         ('instagram', json.dumps(result, ensure_ascii=False)))
    return result


def main():
    from .store import Store
    store = Store('state/platform.sqlite')
    try:
        result = refresh(store)
        # Controlled state only; no raw counters, account IDs, text or URLs.
        print(json.dumps(result, ensure_ascii=False))
    finally:
        store.close()
    if result['status'] not in ('ready', 'insufficient_data'):
        raise SystemExit(1)  # always() persists the controlled failure status.


if __name__ == '__main__':
    main()
