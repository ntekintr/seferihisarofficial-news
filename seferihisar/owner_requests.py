"""Finite owner request inside the existing publisher and existing daily budget."""
from pathlib import Path
import json

from .domain import digest, parse_date


def pending(store, at, config=None):
    path = Path(config) if config else Path(__file__).resolve().parents[1]/'config/owner-requests.json'
    if not path.exists():
        return None
    requests = json.loads(path.read_text(encoding='utf-8'))
    if len(requests) > 3:
        raise ValueError('Owner request budget exceeded')
    for request in requests:
        if set(request) != {'post_id', 'source_url', 'expires_at', 'requires_image'}:
            raise ValueError('Invalid owner request')
        expiry = parse_date(request['expires_at'])
        if not expiry or at >= expiry:
            continue
        post = next((p for p in store.posts() if p['id'] == request['post_id'] and not p.get('publish_format')), None)
        if not post or post['source_urls'] != [request['source_url']]:
            continue
        if post['status'] == 'published':
            child = next((p for p in store.posts() if p['id'] == digest(post['id']+':story:0')), None)
            if child and child['status'] == 'published':
                continue
        if post['status'] in ('expired', 'superseded'):
            continue
        return request
    return None


def publish(store, at, site_url, assets, checkpoint=None):
    request = pending(store, at)
    if request is None:
        return None
    post = next(p for p in store.posts() if p['id'] == request['post_id'])
    if request['requires_image'] and not (post.get('illustration_keys') or post.get('source_photo_keys')):
        return {'status': 'visual_review_unavailable'}
    from .instagram import publish_requested
    return publish_requested(store, at, site_url, assets, request['post_id'],
                             checkpoint=checkpoint, require_visual_review=True)
