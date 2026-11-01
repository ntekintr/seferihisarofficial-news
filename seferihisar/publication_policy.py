"""Owner publication limits and immutable-card repeat protection.

Independent weather/pharmacy tables are deliberately outside the news budget.
Claimed rows are observations, never reset or rewritten to recover a slot.
"""
import json
from datetime import date, datetime, time, timedelta

from .domain import TZ, normalized, parse_date

NEWS_DAILY_LIMIT = 3
NEWS_EVENING_LIMIT = 4
OUTAGE_STORY_LIMIT = 2
OUTAGE_STORY_HOURS = (time(8, 30), time(21))
EVENING_EFFECTIVE_FROM = date.min
CLAIMED = frozenset(('publishing', 'published', 'uncertain'))


def story_only(value):
    """Owner decisions: a power cut (31 Oct) and a revised event card (1 Nov) never take a feed slot."""
    if value.get('category') == 'outage':
        return 'elektrik' in normalized(value.get('title', ''))
    return value.get('kind') == 'update'


def evening_enabled(at):
    return at.astimezone(TZ).date() >= EVENING_EFFECTIVE_FROM


def evening_window(at):
    local = at.astimezone(TZ)
    return evening_enabled(local) and time(20) <= local.time().replace(tzinfo=None) < time(23, 30)


def news_windows(day, base_slots):
    windows = [(datetime.combine(day, slot, TZ), datetime.combine(day, slot, TZ) + timedelta(hours=1), False)
               for slot in base_slots]
    if day >= EVENING_EFFECTIVE_FROM:
        windows += [(datetime.combine(day, time(20), TZ), datetime.combine(day, time(21), TZ), True),
                    (datetime.combine(day, time(22), TZ), datetime.combine(day, time(23, 30), TZ), True)]
    return sorted(windows)


def dispatch_window(at, base_slots):
    at = at.astimezone(TZ)
    return next((window for window in reversed(news_windows(at.date(), base_slots))
                 if window[0] <= at < window[1]), None)


def evening_news_item(item, at, *, bonus=True):
    """Only a new, first source edition; discovery/retimestamping is not news."""
    at = at.astimezone(TZ)
    published, first = parse_date(item.get('published_at')), parse_date(item.get('first_seen'))
    start = datetime.combine(at.date(), time(20), TZ)
    cutoff = datetime.combine(at.date(), time(23), TZ)
    return bool(evening_window(at) and item.get('kind') == 'news'
                and (not bonus or item.get('revision') == 1) and published and first
                and start <= published.astimezone(TZ) < cutoff
                and published <= at and start <= first.astimezone(TZ) <= at)


def day_claims(store, at, *, story=False):
    day = at.astimezone(TZ).date()
    return [p for p in store.posts() if p['status'] in CLAIMED
            and (p.get('publish_format') == 'story') == story
            and not (story and story_only(p))
            and (stamp := parse_date(p.get('published_at'))) is not None
            and stamp.astimezone(TZ).date() == day]


def outage_story_claims(store, at):
    day = at.astimezone(TZ).date()
    return [p for p in store.posts() if p['status'] in CLAIMED
            and p.get('publish_format') == 'story' and story_only(p)
            and (stamp := parse_date(p.get('published_at'))) is not None
            and stamp.astimezone(TZ).date() == day]


def outage_story_due(item, at):
    if item.get('kind') != 'event':
        return True
    start, end = parse_date(item.get('start')), parse_date(item.get('end'))
    if not start or not end or end <= at:
        return False
    # A cut matters only when close; a changed event matters until it happens.
    return (item.get('category') != 'outage'
            or start.astimezone(TZ).date() <= at.astimezone(TZ).date() + timedelta(days=1))


def outage_story_parents(store, at):
    """Today's and tomorrow's cuts, nearest area first.

    `duplicate_reason` blocks the story of an unchanged card, so the many
    revisions of one cut stay one story while a real change gets its own.
    """
    from .selection import prioritize
    items = {i['id']: i for i in store.items()}
    ready = {p.get('parent_post_id') for p in store.posts()
             if p['status'] == 'prepared' and p.get('publish_format') == 'story'}
    parents = [p for p in store.posts() if p['status'] == 'prepared' and p['id'] in ready and story_only(p)
               and p.get('item_id') in items and outage_story_due(items[p['item_id']], at)]
    return prioritize(store, parents, at)


def fourth_parent(store, parent, at):
    stamp = parse_date(parent.get('published_at'))
    claims = day_claims(store, at)
    return bool(stamp and parent['status'] == 'published'
                and sum(parse_date(p['published_at']) <= stamp for p in claims) == NEWS_EVENING_LIMIT
                and parent['id'] in {p['id'] for p in claims})


def evening_post(store, post, at, *, story=False, bonus=True):
    parent = post
    if story:
        parent = next((p for p in store.posts() if p['id'] == post.get('parent_post_id')), None)
        if not parent or post.get('story_index') != 0 or not fourth_parent(store, parent, at):
            return False
    if parent.get('kind') != 'news' or not parent.get('item_id'):
        return False
    item = next((i for i in store.items() if i['id'] == parent['item_id']), None)
    return bool(item and item['revision'] == parent.get('revision')
                and evening_news_item(item, at, bonus=bonus) and not owner_exclusion(parent))


def evening_summary(at):
    return {'enabled': evening_enabled(at), 'normal_daily_feed_limit': NEWS_DAILY_LIMIT,
            'normal_daily_story_limit': NEWS_DAILY_LIMIT, 'absolute_daily_feed_limit': NEWS_EVENING_LIMIT,
            'absolute_daily_story_limit': NEWS_EVENING_LIMIT, 'source_hours': '20:00–22:59',
            'publication_cutoff': '23:30', 'source_first_edition_required': True,
            'extra_story': 'first_matching_story_of_fourth_feed'}


def owner_exclusion(value):
    """The specifically declined recurring class, not all sport/yoga content."""
    title = normalized(value.get('title', ''))
    return ('owner_excluded' if 'canan tutal' in title and 'hatha yoga' in title
            else None)


def daily_limit_reason(store, at, post=None, *, story=False):
    if story and post and story_only(post):
        return 'daily_limit' if len(outage_story_claims(store, at)) >= OUTAGE_STORY_LIMIT else None
    count = len(day_claims(store, at, story=story))
    if count < NEWS_DAILY_LIMIT:
        return None
    if count == NEWS_DAILY_LIMIT and post and evening_post(store, post, at, story=story):
        return None
    return 'daily_limit'


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
        if story_only(post):
            # No feed goes first, so the parent stays unclaimed until the cut ends.
            if (not parent or parent['status'] != 'prepared' or post.get('story_index') != 0
                    or post.get('revision') != parent.get('revision')):
                return 'stale_parent'
            return None
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


def unchanged_update(store, post):
    """A new source revision says nothing until a fact on the card has changed."""
    if post.get('kind') != 'update' or not story_only(post) or post.get('category') == 'outage':
        return False
    family = post.get('parent_post_id', post['id'])
    claims = [p for p in store.posts() if p.get('item_id') == post.get('item_id') and p['status'] in CLAIMED
              and p.get('published_at') and family not in (p['id'], p.get('parent_post_id'))]
    latest = max(claims, key=lambda p: parse_date(p['published_at']), default=None)
    return bool(latest) and latest['slides'][0]['body'] == post['slides'][0]['body']


def duplicate_reason(store, post):
    """Identical rendered facts stay one delivery across revisions and restarts."""
    if unchanged_update(store, post):
        return 'duplicate_story'
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
