"""Read-only editorial ordering, after the publisher's eligibility checks."""
from __future__ import annotations

import re
from datetime import timedelta

from .domain import NEARBY_PLACES, PLACES, TZ, normalized, parse_date


def locality(item):
    # A verified venue takes precedence over a district mentioned incidentally
    # in the title/description. Publisher branding and source names are not evidence.
    for text in (item.get('location'), item.get('title'), item.get('description')):
        value = normalized(text or '')
        for rank, places in enumerate((PLACES, NEARBY_PLACES)):
            if any(re.search(r'\b' + re.escape(normalized(place)) + r'\b', value)
                   for place in places):
                return rank
    return 2


def prioritize(store, posts, at):
    """Order eligible automatic feeds without changing a payload or a deadline.

    Corrections to announced events and imminent services lead; then current
    local news/events, the next week, older news, distant events and digests.
    No AI request, keyword-based truth judgement or paid service is involved.
    """
    at = at.astimezone(TZ)
    items = {item['id']: item for item in store.items()}
    announced = {}
    for claim in store.posts():
        if claim['status'] == 'published' and not claim.get('publish_format') and claim.get('item_id'):
            key = claim['item_id']
            announced[key] = max(announced.get(key, 0), claim['revision'])

    def key(post):
        item = items.get(post.get('item_id'), {})
        tier, timing, stamp = 5, 0, parse_date(post['due_at']).timestamp()
        if item.get('kind') == 'news':
            published = parse_date(item['published_at'])
            fresh = at - published <= timedelta(days=1)
            tier = 0 if fresh and item['category'] in ('outage', 'weather', 'transport') else 1 if fresh else 3
            timing, stamp = 1, -published.timestamp()
        elif item.get('kind') == 'event':
            start, end = parse_date(item['start']), parse_date(item['end'])
            days = (start.date() - at.date()).days
            upcoming = end.date() >= at.date()
            tier = (1 if days <= 1 else 2 if days <= 7 else 4) if upcoming else 5
            timing, stamp = (0 if days <= 0 else 2), start.timestamp()
            correction = (post['kind'] == 'cancellation' or
                          (post['kind'] == 'update' and 0 < announced.get(item['id'], 0) < post['revision']))
            service = item['category'] == 'outage' and start <= at + timedelta(days=1) and end > at
            if upcoming and (correction or service):
                tier, timing = 0, 0
        # Prefer the applicable reminder to a duplicate announcement for the
        # same occurrence. Keep source identities; do not merge dates/venues here.
        wording = {'cancellation': 0, 'update': 1, 'reminder_day': 2,
                   'reminder_3d': 3, 'announcement': 4}.get(post['kind'], 5)
        return tier, locality(item), timing, stamp, wording, parse_date(post['due_at']), post['id']

    return sorted(posts, key=key)
