"""Conservative cross-source news repeat hold; never merge source records."""
import re
from datetime import timedelta

from .domain import normalized, parse_date


def words(title):
    value = normalized(title)
    value = re.sub(r'^(?:yerel haberler|ulaşim|belediye|kamu duyurulari) ', '', value)
    value = re.sub(r'\bbir araya (?:geldi|geliyor|gelecek|gelerek)\b|\bbuluştu\b', 'toplanti', value)
    value = re.sub(r'\bmuhtar(?:iyla|lariyla|imizla|larimizla)\b', 'muhtar', value)
    return set(value.split()) - {'ve', 'ile', 'bir'}


def repeat(store, post):
    if post.get('kind') != 'news' or post.get('publish_format'):
        return False
    tokens = words(post.get('title', ''))
    if len(tokens) < 6 or re.search(r'\b(?:düzeltme|güncelleme|iptal)\b', normalized(post.get('title', ''))):
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
        if {t for t in tokens if t.isdigit()} != {t for t in other if t.isdigit()}:
            continue
        if len(tokens & other) >= 6 and len(tokens & other) / len(tokens | other) >= .92:
            return True
    return False
