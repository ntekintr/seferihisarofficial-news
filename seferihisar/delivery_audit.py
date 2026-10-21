"""GET-only delivery observations; never repair, reset or replay a claim."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

from .domain import digest, now, parse_date

STATUSES = {'present', 'object_readable', 'caption_mismatch', 'timestamp_mismatch',
            'not_visible', 'read_failed', 'permission_required', 'credential_invalid',
            'settings_missing', 'account_mismatch', 'expired_not_checked', 'rate_limited',
            'story_read_unavailable'}
FAILURES = STATUSES - {'present', 'object_readable', 'expired_not_checked'}
MAX_ROWS = 500
MAX_GETS = 16


def validate_row(row):
    key, channel, kind, checked, status = row
    if (not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{24}', key)
            or channel not in ('instagram', 'facebook') or kind not in ('feed', 'story', 'weather')
            or (kind == 'weather' and channel != 'instagram') or status not in STATUSES
            or datetime.fromisoformat(checked).tzinfo is None):
        raise ValueError('Invalid delivery observation')


class ReadError(Exception):
    pass


class Reader:
    def __init__(self, session, version):
        self.session, self.base, self.calls = session, 'https://graph.facebook.com/' + version + '/', 0

    def get(self, path, token, fields):
        import requests
        if self.calls >= MAX_GETS:
            raise ReadError('rate_limited')
        self.calls += 1
        try:
            r = self.session.get(self.base + path, params={'fields': fields, **({'limit': 100} if path.endswith('/stories') else {})},
                                 headers={'Authorization': 'Bearer ' + token},
                                 timeout=(5, 10), allow_redirects=False)
            v = r.json()
            error = v.get('error', {}) if isinstance(v, dict) else {}
            code = error.get('code') if isinstance(error, dict) else None
            if code == 190:
                raise ReadError('credential_invalid')
            if code in (10, 200):
                raise ReadError('permission_required')
            if code in (4, 17, 32, 613) or r.status_code == 429:
                raise ReadError('rate_limited')
            if not r.ok or r.status_code >= 300 or not isinstance(v, dict) or error:
                raise ReadError('read_failed')
            return v
        except (requests.RequestException, ValueError):
            raise ReadError('read_failed') from None


def clean_text(value):
    return ' '.join(value.replace('\r\n', '\n').split()) if isinstance(value, str) else None


def feed_result(value, media, caption, claimed, field):
    if value.get('id') != media:
        return 'not_visible'
    if clean_text(value.get(field)) != clean_text(caption):
        return 'caption_mismatch'
    stamp = parse_date(value.get('timestamp' if field == 'caption' else 'created_time'))
    if not stamp or not claimed or not claimed - timedelta(minutes=5) <= stamp <= claimed + timedelta(minutes=30):
        return 'timestamp_mismatch'
    return 'present'


def facebook_story_result(rows, media, claimed):
    """Page /stories returns post_id, not a directly addressable Graph node ID."""
    if not isinstance(rows, list) or any(not isinstance(r, dict)
            or not re.fullmatch(r'\d{1,32}', str(r.get('post_id', '')))
            or not isinstance(r.get('status'), str) for r in rows):
        raise ReadError('story_read_unavailable')
    matches = [r for r in rows if str(r.get('post_id', '')) == media]
    if len(matches) != 1:
        return 'not_visible'
    row = matches[0]
    if str(row.get('status', '')).casefold() != 'published':
        return 'not_visible'
    value = row.get('creation_time')
    try:
        # Meta's Stories field is a Unix timestamp; tolerate an ISO date too.
        stamp = (datetime.fromtimestamp(int(value), tz=claimed.tzinfo)
                 if re.fullmatch(r'\d{1,12}', str(value)) else parse_date(value))
    except (ValueError, OverflowError, OSError):
        stamp = None
    if not stamp or not claimed - timedelta(minutes=5) <= stamp <= claimed + timedelta(minutes=30):
        return 'timestamp_mismatch'
    return 'present'


def refresh(store, at=None, *, environ=None, session=None):
    import requests
    at = at or now()
    env = os.environ if environ is None else environ
    version = env.get('META_GRAPH_VERSION', 'v26.0')
    if not re.fullmatch(r'v\d+\.0', version):
        return summary(store, at)
    reader = Reader(session or requests.Session(), version)
    previous = {r['id']: r for r in store.rows('SELECT * FROM delivery_audits')}
    tasks = []
    parents = {p['id']: p for p in store.posts() if not p.get('publish_format')}
    for p in store.posts():
        stamp = parse_date(p.get('published_at'))
        if p['status'] == 'published' and stamp and at - timedelta(days=2) <= stamp <= at:
            kind = 'story' if p.get('publish_format') == 'story' else 'feed'
            parent = parents.get(p.get('parent_post_id')) if kind == 'story' else p
            if parent and (kind == 'feed' or p.get('story_index') == 0):
                tasks.append((digest('instagram:' + p['id']), 'instagram', kind, p['media_id'], stamp, parent.get('caption', '')))
    for r in store.rows("SELECT * FROM facebook_deliveries WHERE status='published'"):
        stamp = parse_date(r['claimed_at'])
        if at - timedelta(days=2) <= stamp <= at and r['post_id'] in parents:
            tasks.append((digest('facebook:' + r['id']), 'facebook', r['format'], r['media_id'], stamp, parents[r['post_id']].get('caption', '')))
    for r in store.rows("SELECT * FROM weather_stories WHERE status='published'"):
        stamp = parse_date(r['published_at'])
        if stamp and at - timedelta(days=2) <= stamp <= at:
            tasks.append((digest('weather:' + r['day']), 'instagram', 'weather', r['media_id'], stamp, ''))
    # A successful observation is retained after a story expires. Expiry is not a deletion alarm.
    tasks.sort(key=lambda x: x[4], reverse=True)
    identities, story_ids, facebook_stories, updates = {}, None, None, []
    for key, channel, kind, media, stamp, caption in tasks[:40]:
        if at - stamp < timedelta(minutes=3):
            continue  # Allow provider list/caption propagation; a receipt is not a readback.
        old = previous.get(key)
        # v1 treated Facebook story post_id as a Graph object. Recheck that old
        # result once via the documented owner edge; new failures keep cooldown.
        legacy_story = (old and channel == 'facebook' and kind == 'story'
                        and old['status'] in ('read_failed', 'object_readable'))
        if old and not legacy_story and at - parse_date(old['checked_at']) < timedelta(hours=6):
            continue
        if kind != 'feed' and at - stamp >= timedelta(hours=23):
            if not old:
                updates.append((key, channel, kind, at.isoformat(), 'expired_not_checked'))
            continue
        if reader.calls >= MAX_GETS:
            break
        if channel == 'facebook' and env.get('FACEBOOK_PUBLISH_ENABLED') != 'true':
            continue
        token = env.get('INSTAGRAM_ACCESS_TOKEN' if channel == 'instagram' else 'FACEBOOK_PAGE_ACCESS_TOKEN', '')
        account = env.get('INSTAGRAM_USER_ID' if channel == 'instagram' else 'FACEBOOK_PAGE_ID', '')
        try:
            if not token or not re.fullmatch(r'\d{1,32}', account or '') or not re.fullmatch(r'\d{1,32}(?:_\d{1,32})?', media or ''):
                raise ReadError('settings_missing')
            if channel not in identities:
                identity = reader.get(account if channel == 'instagram' else 'me', token,
                                      'id,username' if channel == 'instagram' else 'id,instagram_business_account')
                linked = identity.get('instagram_business_account', {})
                valid = (identity.get('id') == account and
                         (identity.get('username') == 'seferihisarofficial' if channel == 'instagram'
                          else isinstance(linked, dict) and linked.get('id') == env.get('INSTAGRAM_USER_ID')))
                identities[channel] = 'ok' if valid else 'account_mismatch'
            if identities[channel] != 'ok':
                raise ReadError(identities[channel])
            if channel == 'instagram' and kind != 'feed':
                if story_ids is None:
                    rows = reader.get(account + '/stories', token, 'id').get('data')
                    if not isinstance(rows, list) or any(not isinstance(r, dict) or not re.fullmatch(r'\d{1,32}', r.get('id', '')) for r in rows):
                        raise ReadError('read_failed')
                    story_ids = {r['id'] for r in rows}
                result = 'present' if media in story_ids else 'not_visible'
            elif channel == 'facebook' and kind == 'story':
                if facebook_stories is None:
                    try:
                        facebook_stories = reader.get(account + '/stories', token,
                            'post_id,status,creation_time').get('data')
                        if not isinstance(facebook_stories, list):
                            raise ReadError('story_read_unavailable')
                    except ReadError as exc:
                        # Cache one failed edge read for this run as well.
                        facebook_stories = str(exc)
                if isinstance(facebook_stories, str):
                    raise ReadError(facebook_stories)
                result = facebook_story_result(facebook_stories, media, stamp)
            else:
                field = 'caption' if channel == 'instagram' else 'message'
                value = reader.get(media, token, 'id,' + field + (',timestamp' if channel == 'instagram' else ',created_time'))
                result = feed_result(value, media, caption, stamp, field)
        except ReadError as exc:
            result = str(exc)
            if channel == 'facebook' and kind == 'story' and result == 'read_failed':
                result = 'story_read_unavailable'
            if result in ('credential_invalid', 'permission_required', 'account_mismatch'):
                identities[channel] = result
        updates.append((key, channel, kind, at.isoformat(), result))
    with store.db:
        for row in updates:
            validate_row(row)
            store.db.execute('INSERT OR REPLACE INTO delivery_audits VALUES (?,?,?,?,?)', row)
        store.db.execute('DELETE FROM delivery_audits WHERE id NOT IN (SELECT id FROM delivery_audits ORDER BY checked_at DESC,id LIMIT ?)', (MAX_ROWS,))
    return summary(store, at)


def summary(store, at=None):
    at = at or now()
    rows = store.rows('SELECT * FROM delivery_audits')
    return {'version': 'delivery-audit-v2', 'checked_at': max((r['checked_at'] for r in rows), default=None),
            'results': dict(Counter(r['status'] for r in rows)),
            'recent_failures': sum(r['status'] in FAILURES and at - timedelta(days=1) <= parse_date(r['checked_at']) <= at for r in rows),
            'scope': 'GET-only recorded media IDs; feed caption/time; active Instagram story membership; Facebook Page story post_id/status/time',
            'image_pixels_inspected': False, 'republishing_allowed': False}


def main():
    from .store import Store
    store = Store('state/platform.sqlite')
    try:
        result = refresh(store)
    finally:
        store.close()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
