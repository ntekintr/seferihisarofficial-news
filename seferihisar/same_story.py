"""Other sources' reports of one story, read only to find it a real photograph.

Publishers title one story differently, so the comparison rests on words few
current stories share. Calibrated 1 Nov on 213 stories from both cities: of
about 30 pairs at this bar, one was loose. Never merges or changes a record.
"""
import re
from collections import Counter
from datetime import timedelta

from .domain import normalized, parse_date

WINDOW = timedelta(hours=72)
MIN_SHARED, MIN_TITLE = 7, 3


def stems(text):
    # Turkish suffixes hide a shared word; six letters keep it recognisable.
    value = normalized(text).replace('çevre yolu', 'çevreyolu')
    return {word[:6] for word in re.findall(r'[0-9a-zçğıöşü]{4,}', value)}


def text_of(item):
    return item['title'] + ' ' + (item.get('description') or '')[:500]


def reports(item, items):
    """Same-story news from other sources, the closest first."""
    news = [other for other in items if other.get('kind') == 'news' and other.get('published_at')]
    words = {other['id']: stems(text_of(other)) for other in news}
    counts = Counter(stem for found in words.values() for stem in found)
    rare = max(6, len(news) * .03)
    own, title, stamp = stems(text_of(item)), stems(item['title']), parse_date(item['published_at'])
    found = []
    for other in news:
        if (other['source_id'] == item['source_id']
                or abs(parse_date(other['published_at']) - stamp) > WINDOW):
            continue
        shared = {stem for stem in own & words[other['id']] if counts[stem] <= rare}
        hits = (title & words[other['id']]) | (stems(other['title']) & own)
        if len(shared) >= MIN_SHARED and len(hits) >= MIN_TITLE:
            found.append((len(shared), other))
    return [other for _, other in sorted(found, key=lambda pair: (-pair[0], pair[1]['id']))]
