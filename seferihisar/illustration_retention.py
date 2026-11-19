"""When a published card's scene may leave the illustration cache.

Owner decision (19 Nov 2026): "7 gün bile saklama 1 gün sonra silsin." A
scene bound by publication claims used to stay cached for ever, so 80 of them
filled the cache. Its bytes now leave 24 hours after the last delivery that
used it. The key stays claimed by its posts, so it is never generated again.

Standard library only: state restore imports this module.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

RETAIN_AFTER_PUBLICATION = timedelta(hours=24)
# Every other status (prepared, blocked_source, publishing, uncertain, ...)
# can still need the scene, so it keeps the bytes.
FINISHED = frozenset(('published', 'superseded', 'expired'))


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo is not None else None


def released_keys(db, at: datetime) -> set[str]:
    """Scene keys whose every user is finished and last delivery is 24 h old.

    Users are all posts binding the key (feed, stories, digests, reminders)
    and their Facebook mirror deliveries. An unfinished user, an unfinished
    Facebook delivery or any unreadable binding/timestamp releases nothing.
    """
    users = {}
    for post_id, status, payload in db.execute('SELECT id,status,payload FROM posts'):
        try:
            post = json.loads(payload)
            bindings = post.get('illustration_keys', {})
        except (TypeError, ValueError, AttributeError):
            return set()
        if not isinstance(bindings, (dict, list)):
            return set()
        for key in (bindings.values() if isinstance(bindings, dict) else bindings):
            if isinstance(key, str):
                users.setdefault(key, []).append((post_id, status, post.get('published_at')))
    deliveries = {}
    # A state that never mirrored to Facebook may not have the table yet.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='facebook_deliveries'").fetchone():
        for post_id, status, claimed, updated in db.execute(
                'SELECT post_id,status,claimed_at,updated_at FROM facebook_deliveries'):
            deliveries.setdefault(post_id, []).append((status, claimed, updated))
    released = set()
    for key, rows in users.items():
        stamps, finished = [], any(status == 'published' for _, status, _ in rows)
        for post_id, status, published in rows:
            if status not in FINISHED:
                finished = False
            elif status == 'published':
                stamps.append(_stamp(published))
            for delivery, claimed, updated in deliveries.get(post_id, []):
                if delivery != 'published':
                    finished = False
                stamps += [_stamp(claimed), _stamp(updated)]
        if finished and stamps and None not in stamps and at - max(stamps) >= RETAIN_AFTER_PUBLICATION:
            released.add(key)
    return released
