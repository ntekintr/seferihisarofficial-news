"""Bind reviewed content, illustrations and deployed JPEG bytes to one edition."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urljoin

import requests

from .domain import digest,now
from .security import public_url, valid_visual_review

VERSION = 'content-visual-v3'
CONTENT_FIELDS = ('id', 'item_id', 'revision', 'kind', 'title', 'caption', 'category',
                  'source_urls', 'slides', 'illustration_keys')


def fingerprint(data):
    # Colon-separated SHA-256 bytes cannot resemble a long access token in
    # the unchanged public secret scanner. Do not weaken that boundary for hashes.
    return hashlib.sha256(data).digest().hex(':')


def content_key(post):
    values={k:post.get(k) for k in CONTENT_FIELDS}
    # Leave every pre-existing frozen edition's fingerprint unchanged.
    if 'source_photo_keys' in post:values['source_photo_keys']=post['source_photo_keys']
    if 'card_layout' in post:values['card_layout']=post['card_layout']
    return digest(json.dumps(values, ensure_ascii=False, sort_keys=True))


def review(post, illustrations, items=None):
    images = {str(i): fingerprint(path.read_bytes()) for i, path in illustrations.items()}
    content = content_key(post)
    if post.get('item_id'):
        references = {post['item_id']:post['revision']}
    else:
        by_url = {url:i for i in (items or {}).values() for url in i.get('sources', []) + [i['url']]}
        references = {by_url[url]['id']:by_url[url]['revision']
                      for url in post.get('source_urls', []) if url in by_url}
    edition = digest(VERSION + content + json.dumps([images,references], sort_keys=True))
    return {'version': VERSION, 'content': content, 'edition': edition,
            'images': images, 'references': references, 'assets': {}}


def valid_review(post):
    proof = post.get('visual_review')
    return (valid_visual_review(proof) and proof.get('version') == VERSION
            and proof.get('content') == content_key(post)
            and isinstance(proof.get('edition'), str)
            and re.fullmatch(r'[a-f0-9]{24}', proof['edition']))


def record_assets(post, assets, directory):
    post['visual_review']['assets'] = {path: fingerprint((directory / path).read_bytes())
                                     for paths in assets.values() for path in paths}


def deployed(store, post, site_url, paths, session=None, *, story=False):
    """A HEAD 200 is insufficient: old content may still live at a stable URL.

    This bounded GET check runs before any durable claim or Meta write for new
    feed/story and Facebook deliveries. It never fetches source URLs.
    """
    parent = post
    if post.get('publish_format') == 'story':
        parent = next((p for p in store.posts() if p['id'] == post.get('parent_post_id')), {})
    from .quality import publication_copy_reason
    items = {i['id']:i for i in store.items()}
    if reason := publication_copy_reason(parent, items):
        return reason
    from .source_photos import binding_reason
    if reason := binding_reason(store,parent,items,now()):
        return reason
    if not public_url(site_url) or not valid_review(parent):
        return 'visual_review_missing'
    proof = parent['visual_review']
    current = {key:i['revision'] for key,i in items.items()}
    if (not proof['references'] or any(current.get(key) != revision for key,revision in proof['references'].items())
            or (parent.get('item_id') and proof['references'].get(parent['item_id']) != parent['revision'])):
        return 'visual_review_stale'
    if not paths or any(path not in proof['assets'] or not re.fullmatch(
            r'media/' + proof['edition'] + r'/(?:feed|story)-\d+\.jpg', path) for path in paths):
        return 'visual_review_stale'
    client = session or requests
    try:
        raw = read(client, urljoin(site_url.rstrip('/') + '/', 'data.json'), 4 * 1024 * 1024, 'application/json')
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or not isinstance(manifest.get('posts'), list):
            return 'visual_review_unavailable'
        visible = next((p for p in manifest['posts'] if isinstance(p, dict) and p.get('id') == parent['id']), {})
        if (manifest.get('demo') or visible.get('visual_review') != proof
                or any(visible.get(k) != parent.get(k) for k in ('title','caption','category'))):
            return 'visual_review_stale'
        if any(path not in visible.get('assets', {}).get('story' if story else 'feed', []) for path in paths):
            return 'visual_review_stale'
        for path in paths:
            image = read(client, urljoin(site_url.rstrip('/') + '/', path), 4 * 1024 * 1024, 'image/jpeg')
            if fingerprint(image) != proof['assets'][path]:
                return 'visual_review_stale'
    except (requests.RequestException, ValueError, TypeError, KeyError, StopIteration, OSError):
        return 'visual_review_unavailable'
    return None


def read(session, url, limit, content_type):
    with session.get(url, timeout=(8, 20), allow_redirects=False, stream=True) as response:
        if response.status_code != 200 or not response.headers.get('Content-Type', '').startswith(content_type):
            raise ValueError('Reviewed media unavailable')
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Reviewed media oversized')
        return bytes(data)
