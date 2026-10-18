"""Conservative display of event roles and addresses; source rows stay intact."""
import re
from urllib.parse import urlsplit

from .domain import NEARBY_PLACES, PLACES, normalized


PLATFORMS = {
    'bubilet.com.tr': 'Bubilet',
    'biletix.com': 'Biletix',
    'biletinial.com': 'Biletinial',
    'biletino.com': 'Biletino',
}
PLATFORM_NAMES = {normalized(value) for value in PLATFORMS.values()} | {
    normalized(prefix + host) for host in PLATFORMS for prefix in ('', 'www.')
}
GEOGRAPHY = {normalized(place) for place in (*PLACES, *NEARBY_PLACES, 'İzmir')}


def ticket_platform(item):
    # A reviewed ticket host establishes the seller/platform, not the producer.
    url = item.get('ticket_url') or item.get('url') or ''
    host = (urlsplit(url).hostname or '').removeprefix('www.')
    return PLATFORMS.get(host)


def organizer(item):
    value = item.get('organizer')
    if not value or normalized(value) in PLATFORM_NAMES:
        return None
    return value


def location(item):
    value = item.get('location')
    if not value:
        return None
    value = re.sub(r'\s+', ' ', value).strip()
    # Structured postal addresses often append the province already printed in
    # the street address. Remove only exact repeated geographic suffixes. Never
    # deduplicate numbers, street names, venue names or distinct district/city.
    while True:
        words = list(re.finditer(r'[^\W\d_]+', value))
        changed = False
        if words and not value[words[-1].end():].strip(' ,/·;-'):
            for size in range(min(3, len(words) // 2), 0, -1):
                suffix = [normalized(w.group()) for w in words[-size:]]
                previous = [normalized(w.group()) for w in words[-2*size:-size]]
                start = words[-size].start()
                tail = words[-2*size:]
                clean_gaps = all(not value[a.end():b.start()].strip(' ,/·;-')
                                 for a, b in zip(tail, tail[1:]))
                if (suffix == previous and all(w in GEOGRAPHY for w in suffix)
                        and clean_gaps):
                    value = value[:start].rstrip(' ,/·;-')
                    changed = True
                    break
        if not changed:
            return value


def needs_review(item):
    return bool(ticket_platform(item) or organizer(item) != item.get('organizer')
                or location(item) != item.get('location'))
