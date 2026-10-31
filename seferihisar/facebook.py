"""Optional second destination for the existing Instagram content stream.

Only recently published Instagram content is eligible. Separate durable claims
prevent a Facebook failure from resetting or repeating an Instagram publication.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit

import requests

from .domain import TZ, digest, parse_date
from .schedule import blocked_sources, source_current
from .security import public_url
from .store import Store
from .publication_policy import (NEWS_DAILY_LIMIT, NEWS_EVENING_LIMIT, owner_exclusion, evening_post, fourth_parent,
                                 outage_story_claims, story_only)


class Facebook:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.token = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN', '')
        self.page = os.getenv('FACEBOOK_PAGE_ID', '')
        self.instagram = os.getenv('INSTAGRAM_USER_ID', '')
        version = os.getenv('META_GRAPH_VERSION', 'v26.0')
        if not re.fullmatch(r'v\d+\.0', version):
            raise ValueError('Invalid Graph API version')
        self.base = f'https://graph.facebook.com/{version}'

    def enabled(self):
        return (os.getenv('FACEBOOK_PUBLISH_ENABLED') == 'true' and
                os.getenv('FACEBOOK_TESTS_COMPLETED') == 'true' and
                bool(self.token) and bool(re.fullmatch(r'\d+', self.page)) and
                bool(re.fullmatch(r'\d+', self.instagram)))

    def call(self, path, method='POST', **params):
        response = self.session.request(method, f'{self.base}/{path}',
            headers={'Authorization': f'Bearer {self.token}'},
            params=params if method == 'GET' else None,
            data=params if method != 'GET' else None,
            timeout=(8, 30), allow_redirects=False)
        if not response.ok or 300 <= response.status_code < 400:
            raise RuntimeError('Facebook API request failed')
        result = response.json()
        if not isinstance(result, dict) or 'error' in result:
            raise RuntimeError('Facebook API response invalid')
        return result

    def check_identity(self):
        page = self.call('me', 'GET', fields='id,instagram_business_account')
        return (page.get('id') == self.page and
                page.get('instagram_business_account', {}).get('id') == self.instagram)

    def upload(self, url):
        return self.call(f'{self.page}/photos', url=url, published='false')['id']

    def publish(self, photo_ids, caption, story):
        if story:
            result = self.call(f'{self.page}/photo_stories', photo_id=photo_ids[0])
            if result.get('success') is not True:
                raise RuntimeError('Facebook story publication not confirmed')
            return result['post_id']
        return self.call(f'{self.page}/feed', message=caption,
                         attached_media=json.dumps([{'media_fbid': i} for i in photo_ids]))['id']


def current_post(store, post, at):
    if owner_exclusion(post):
        return False
    items = store.items()
    by_id = {i['id']: i for i in items}
    by_url = {url: i for i in items for url in i.get('sources', []) + [i['url']]}
    refs = ([by_id.get(post['item_id'])] if post.get('item_id')
            else [by_url.get(url) for url in post['source_urls']])
    failed = blocked_sources(store)
    if not refs or not all(i and source_current(i, at, failed) for i in refs):
        return False
    if post.get('item_id') and refs[0]['revision'] != post['revision']:
        return False
    return True


def deliver(store, post, at, site_url, paths, story, api, checkpoint, *, require_visual_review=False):
    kind = 'story' if story else 'feed'
    key = digest(f"facebook:{api.page}:{post['id']}:{kind}")
    previous = store.rows('SELECT * FROM facebook_deliveries WHERE id=?', (key,))
    if previous:
        return 'already_published' if previous[0]['status'] == 'published' else 'awaiting_resolution'
    # Includes uncertain attempts; a restart cannot restore the daily budget.
    claims = store.rows('SELECT post_id,claimed_at FROM facebook_deliveries WHERE page_id=? AND format=?', (api.page, kind))
    outage = {p['id'] for p in store.posts() if story_only(p)} if story else set()
    count = sum(parse_date(c['claimed_at']).astimezone(TZ).date() == at.date() and c['post_id'] not in outage for c in claims)
    if (post['id'] not in outage and (count >= NEWS_EVENING_LIMIT or count >= NEWS_DAILY_LIMIT
            and not (fourth_parent(store, post, at) and evening_post(store, post, at)))):
        return 'daily_limit'
    parsed = urlsplit(site_url)
    if not public_url(site_url) or parsed.query or parsed.fragment:
        raise ValueError('Public HTTPS media base required')
    if not paths or len(paths) > 10:
        return 'media_missing'
    if require_visual_review or isinstance(api, Facebook):
        from .visual_gate import deployed
        if reason := deployed(store, post, site_url, paths, session=api.session, story=story):
            return reason
    urls = []
    for path in paths:
        if not re.fullmatch(r'media/[a-f0-9]{24}/(?:feed|story)-\d+\.jpg', path):
            return 'media_missing'
        url = urljoin(site_url.rstrip('/') + '/', path)
        response = api.session.head(url, timeout=15, allow_redirects=False)
        if response.status_code != 200 or not response.headers.get('Content-Type', '').startswith('image/jpeg'):
            return 'media_not_deployed'
        urls.append(url)
    with store.db:
        changed = store.db.execute('INSERT OR IGNORE INTO facebook_deliveries VALUES(?,?,?,?,?,?,?, ?,NULL)',
            (key, post['id'], api.page, kind, 'publishing', at.isoformat(), at.isoformat(), '[]'))
    if changed.rowcount != 1:
        return 'awaiting_resolution'
    # Outside the provider try: checkpoint failure must prevent ALL Meta writes.
    if checkpoint:
        checkpoint()
    try:
        photo_ids = []
        for url in urls:
            photo_ids.append(api.upload(url))
            with store.db:
                store.db.execute('UPDATE facebook_deliveries SET photo_ids=?,updated_at=? WHERE id=?',
                                 (json.dumps(photo_ids), at.isoformat(), key))
            if checkpoint:
                checkpoint()
        media_id = api.publish(photo_ids, post['caption'], story)
        with store.db:
            store.db.execute("UPDATE facebook_deliveries SET status='published',media_id=?,updated_at=? WHERE id=?",
                             (media_id, at.isoformat(), key))
        if checkpoint:
            checkpoint()
        return 'published'
    except (requests.RequestException, RuntimeError, KeyError, ValueError):
        with store.db:
            store.db.execute("UPDATE facebook_deliveries SET status='uncertain',updated_at=? WHERE id=?", (at.isoformat(), key))
        if checkpoint:
            checkpoint()
        return 'uncertain'


def publish_recent(store: Store, at: datetime, site_url, assets, adapter=None, checkpoint=None, *, require_visual_review=False, target_id=None):
    api = adapter or Facebook()
    if not api.enabled():
        return {'status': 'disabled'}
    at = at.astimezone(TZ)
    parents = sorted((p for p in store.posts() if p['status'] == 'published' and not p.get('publish_format')
        and (target_id is None or p['id'] == target_id)
        and p.get('published_at') and at - timedelta(hours=1) <= parse_date(p['published_at']) <= at
        and parse_date(p['published_at']).astimezone(TZ).date() == at.date()), key=lambda p: p['published_at'])
    if not parents:
        return {'status': 'empty'}
    # Prevent publishing into the wrong page even if a secret was misconfigured.
    if not api.check_identity():
        return {'status': 'account_mismatch'}
    # A completed third pair cannot hide a later fourth still awaiting its
    # mirror. Existing uncertain delivery keys remain non-replayable.
    def complete(parent):
        keys = [digest(f"facebook:{api.page}:{parent['id']}:{kind}") for kind in ('feed', 'story')]
        rows = store.rows('SELECT id,status FROM facebook_deliveries WHERE id IN (?,?)', keys)
        return len(rows) == 2 and all(row['status'] == 'published' for row in rows)
    pending = [p for p in parents if not complete(p)]
    parent = (pending or parents)[-1]
    if not current_post(store, parent, at):
        return {'status': 'blocked_source'}
    feed = deliver(store, parent, at, site_url, assets.get(parent['id'], {}).get('feed', []), False, api, checkpoint, require_visual_review=require_visual_review)
    if feed not in ('published', 'already_published'):
        return {'status': feed}
    child = next((p for p in store.posts() if p['id'] == digest(parent['id'] + ':story:0') and p['status'] == 'published'), None)
    if not child:
        return {'status': 'story_pending', 'feed': feed}
    story = deliver(store, parent, at, site_url, [child['story_asset']], True, api, checkpoint, require_visual_review=require_visual_review)
    return {'status': 'complete' if story in ('published', 'already_published') else 'story_pending', 'feed': feed, 'story': story}


def publish_outage_story(store: Store, at: datetime, site_url, adapter=None, checkpoint=None, *, require_visual_review=False):
    """Mirror a recent power-cut story; it has no feed post to travel with."""
    api = adapter or Facebook()
    if not api.enabled():
        return {'status': 'disabled'}
    at = at.astimezone(TZ)
    stories = sorted((p for p in outage_story_claims(store, at) if p['status'] == 'published'
                      and at - timedelta(hours=1) <= parse_date(p['published_at']) <= at), key=lambda p: p['published_at'])
    if not stories:
        return {'status': 'empty'}
    if not api.check_identity():
        return {'status': 'account_mismatch'}
    for child in stories:
        parent = next((p for p in store.posts() if p['id'] == child.get('parent_post_id')), None)
        if not parent or not current_post(store, parent, at):
            return {'status': 'blocked_source'}
        status = deliver(store, parent, at, site_url, [child['story_asset']], True, api, checkpoint, require_visual_review=require_visual_review)
        if status != 'already_published':
            return {'status': status}
    return {'status': 'already_published'}
