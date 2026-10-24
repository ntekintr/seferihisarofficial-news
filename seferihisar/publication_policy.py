"""Owner publication limits and immutable-card repeat protection.

Independent weather/pharmacy tables are deliberately outside the news budget.
Claimed rows are observations, never reset or rewritten to recover a slot.
"""
import json
from datetime import timedelta

from .domain import TZ, normalized, parse_date

NEWS_DAILY_LIMIT = 3
CLAIMED = frozenset(('publishing', 'published', 'uncertain'))


def owner_exclusion(value):
    """The specifically declined recurring class, not all sport/yoga content."""
    title = normalized(value.get('title', ''))
    return ('owner_excluded' if 'canan tutal' in title and 'hatha yoga' in title
            else None)


def daily_limit_reason(store, at, *, story=False):
    day = at.astimezone(TZ).date()
    claims = [p for p in store.posts() if p['status'] in CLAIMED
              and (p.get('publish_format') == 'story') == story
              and (stamp := parse_date(p.get('published_at'))) is not None
              and stamp.astimezone(TZ).date() == day]
    return 'daily_limit' if len(claims) >= NEWS_DAILY_LIMIT else None


def post_reason(store, post, at):
    """A new delivery must still describe the original current occurrence."""
    if owner_exclusion(post):
        return 'owner_excluded'
    if post.get('item_id'):
        item = next((i for i in store.items() if i['id'] == post['item_id']), None)
        if not item or item['revision'] != post.get('revision'):
            return 'stale_parent'
    if post.get('publish_format') == 'story':
        parent = next((p for p in store.posts() if p['id'] == post.get('parent_post_id')), None)
        stamp = parse_date(parent.get('published_at')) if parent else None
        if (not parent or parent['status'] != 'published' or not stamp
                or stamp.astimezone(TZ).date() != at.astimezone(TZ).date()
                or not at - timedelta(hours=1) <= stamp <= at
                or post.get('story_index') != 0
                or post.get('revision') != parent.get('revision')
                or owner_exclusion(parent)):
            return 'stale_parent'
    return None


def card_key(post):
    """Use the frozen displayed facts; a mutable source revision is not news."""
    slides = post.get('slides')
    if not isinstance(slides, list) or not slides:
        return None
    values = []
    for slide in slides:
        if not isinstance(slide, dict) or not all(isinstance(slide.get(k), str) for k in ('title', 'body')):
            return None
        values.append([normalized(slide['title']), normalized(slide['body'])])
    if sum(len(''.join(v)) for v in values) < 30:
        return None
    return json.dumps([post.get('category'), values], ensure_ascii=False)


def story_pixels(post):
    proof = post.get('visual_review')
    return (proof.get('assets', {}).get(post.get('story_asset'))
            if isinstance(proof, dict) else None)


def duplicate_reason(store, post):
    """Identical rendered facts stay one delivery across revisions and restarts."""
    story = post.get('publish_format') == 'story'
    current_card, pixels = card_key(post), story_pixels(post) if story else None
    for old in store.posts():
        if (old['id'] == post['id'] or old['status'] not in CLAIMED
                or (old.get('publish_format') == 'story') != story):
            continue
        if (story and post.get('parent_post_id')
                and post['parent_post_id'] == old.get('parent_post_id')):
            return 'duplicate_story'
        if current_card and current_card == card_key(old):
            return 'duplicate_story'
        if pixels and pixels == story_pixels(old):
            return 'duplicate_story'
    return None
