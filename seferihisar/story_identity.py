"""Conservative cross-source news repeat hold; never merge source records."""
import re
from datetime import timedelta

from .domain import CATEGORIES, normalized, parse_date

LABELS = '|'.join(normalized(label) for label in CATEGORIES.values())


def words(title):
    value = normalized(title)
    value = re.sub(rf'^(?:{LABELS}) ', '', value)
    value = re.sub(r'\bbir araya (?:geldi|geliyor|gelecek|gelerek)\b|\bbuluştu\b', 'toplanti', value)
    value = re.sub(r'\bmuhtar(?:iyla|lariyla|imizla|larimizla)\b', 'muhtar', value)
    value = re.sub(r'\byer (?:aldi|aliyor|alacak)\b', '', value)
    return set(value.split()) - {'ve', 'ile', 'bir', 'en', 'da', 'de'}


def harvest_start(title):
    """The same local season opening, not any later citrus development."""
    value = normalized(title)
    return (bool(re.search(r'\bseferihisar\w*\b|\bsatsuma\b', value))
            and bool(re.search(r'\bmandalina\w*\b|\bsatsuma\b', value))
            and bool(re.search(r'\bhasat\w*\b', value))
            and bool(re.search(r'\bbaşladi\b', value)))


def repeat(store, post):
    if post.get('kind') != 'news' or post.get('publish_format'):
        return False
    tokens = words(post.get('title', ''))
    if (len(tokens) < 6 and not harvest_start(post.get('title', ''))) or re.search(r'\b(?:düzeltme|güncelleme|iptal)\b', normalized(post.get('title', ''))):
        return False
    current = {i['id']: i for i in store.items()}
    item = current.get(post.get('item_id'), {})
    stamp = parse_date(item.get('published_at'))
    for old in store.posts():
        if old['id'] == post['id'] or old.get('kind') != 'news' or old.get('publish_format') or old['status'] not in ('published', 'publishing', 'uncertain'):
            continue
        # Use immutable claim time for old publications, not today's last_seen.
        previous = parse_date(old.get('published_at'))
        if not stamp or not previous or abs(stamp - previous) > timedelta(hours=72):
            continue
        other = words(old.get('title', ''))
        if (harvest_start(post.get('title', '')) and harvest_start(old.get('title', ''))
                and 'seferihisar' in normalized(item.get('title', '') + ' ' + item.get('description', ''))
                and 'seferihisar' in normalized(old.get('caption', ''))):
            return True
        if {t for t in tokens if t.isdigit()} != {t for t in other if t.isdigit()}:
            continue
        if len(tokens & other) >= 6 and len(tokens & other) / len(tokens | other) >= .92:
            return True
    return False
