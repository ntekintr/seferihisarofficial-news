"""Source validity and publication deadlines, independent of crawl freshness."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .domain import TZ, normalized, parse_date
from .quality import news_quality_reason


def undated_event_invitation(item: dict) -> bool:
    """A news publication date cannot substitute for an invited occurrence."""
    if item.get('kind') != 'news':
        return False
    text = normalized(item.get('title', '') + ' ' + item.get('description', ''))
    activity = item.get('category') in (
        'concert', 'theatre', 'festival', 'cinema', 'culture', 'family',
        'event', 'market', 'education', 'sport', 'food')
    activity |= bool(re.search(r'\b(?:konser|festival|tiyatro|etkinlik|atölye|gösteri)\w*\b', text))
    invitation = re.search(r'\b(?:bilet|rezervasyon|bekliyoruz|katilin|başlayacak|gerçekleşecek|davetlisiniz)\w*\b', text)
    return bool(activity and invitation)


def requires_validity(item: dict) -> bool:
    if item.get('kind') != 'news':
        return False
    if item.get('category') in ('weather', 'outage'):
        return True
    # Category selection can prefer a festival or transport word in a warning.
    text = normalized(item.get('title', '') + ' ' + item.get('description', ''))
    weather = re.search(r'\b(?:meteoroloji\w*|firtina\w*|sağanak\w*|yağiş\w*|sicak\w*|rüzg[aâ]r\w*|sel|don|dolu|kar|tsunami|deprem|yangin)\b', text)
    warning = re.search(r'\b(?:uyari\w*|bekleniyor|beklenmektedir|tedbir\w*)\b', text)
    service = re.search(r'\b(?:elektrik|su|doğalgaz)\s+kesinti\w*\b|\b(?:yol|trafik|ulaşim)\w*\s+kapat\w*\b', text)
    return bool((weather and warning) or service)


def service_expiry(prose: str) -> datetime | None:
    """Accept one explicit full-year day and one same-day clock range only.

    Multiple days/periods and relative or incomplete dates require a dedicated
    source reader. Neither today's date nor the article timestamp fills gaps.
    """
    months = {name: index for index, name in enumerate((
        'ocak', 'şubat', 'mart', 'nisan', 'mayıs', 'haziran', 'temmuz',
        'ağustos', 'eylül', 'ekim', 'kasım', 'aralık'), 1)}
    text = prose.casefold().replace('\u0307', '')
    if re.search(r'\b(?:bugün|yarın|dün|ertesi)\b', text):
        return None
    numeric = list(re.finditer(r'(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)', text))
    named = list(re.finditer(r'(?<!\d)(\d{1,2})\s+(' + '|'.join(months) + r')\s+(20\d{2})(?!\d)', text))
    ranges = list(re.finditer(r'(?<![\d.])(\d{1,2})[:.](\d{2})\s*[-–]\s*(\d{1,2})[:.](\d{2})(?![\d.])', text))
    dates = {(int(m[3]), int(m[2]), int(m[1])) for m in numeric}
    dates.update((int(m[3]), months[m[2]], int(m[1])) for m in named)
    hours = {m.groups() for m in ranges}
    # An extra clock or incomplete date must not be silently tied to the one
    # complete day elsewhere in the article. Dot clocks are covered by ranges.
    tokens = list(re.finditer(r'(?<!\d)\d{1,2}[:./]\d{2}(?:[./]\d{0,4})?(?!\d)', text))
    tokens += list(re.finditer(r'(?<!\d)\d{1,2}\s+(?:' + '|'.join(months) + r')\b', text))
    if any(not any(m.start() <= t.start() and t.end() <= m.end() for m in numeric + named + ranges)
           for t in tokens):
        return None
    if len(dates) != 1 or len(hours) != 1:
        return None
    y, m, d = next(iter(dates))
    first_h, first_m, last_h, last_m = map(int, next(iter(hours)))
    try:
        start = datetime(y, m, d, first_h, first_m, tzinfo=TZ)
        end = datetime(y, m, d, last_h, last_m, tzinfo=TZ)
    except ValueError:
        return None
    return end if end > start else None


def with_validity(item: dict) -> dict:
    """Add explicit prose validity to generic news; never repair a bad field."""
    if any(not isinstance(item.get(field, ''), str) for field in ('title', 'description')):
        return item
    if requires_validity(item) and 'valid_until' not in item:
        expiry = service_expiry(item.get('title', '') + '\n' + item.get('description', ''))
        if expiry:
            return {**item, 'valid_until': expiry.isoformat()}
    return item


def service_validity_reason(item: dict, at: datetime) -> str | None:
    if 'valid_until' not in item:
        return 'missing_service_validity' if requires_validity(item) else None
    expiry = parse_date(item['valid_until'])
    published = parse_date(item.get('published_at'))
    if not expiry or (item.get('kind') == 'news' and (not published or expiry <= published)):
        return 'invalid_service_validity'
    if expiry <= at:
        return 'expired_service_notice'
    return None


def publication_reason(item: dict, at: datetime) -> str | None:
    """Recheck stored items for every destination, including legacy queues."""
    if reason := news_quality_reason(item):
        return reason
    if reason := service_validity_reason(item, at):
        return reason
    if item.get('kind') == 'news':
        if undated_event_invitation(item):
            return 'missing_event_date'
        published = parse_date(item.get('published_at'))
        if not published or published > at + timedelta(minutes=5):
            return 'outdated_or_missing_date'
        if at - published > timedelta(hours=48):
            return 'expired_news'
    elif item.get('kind') == 'event':
        start, end = parse_date(item.get('start')), parse_date(item.get('end'))
        if not start or not end or end < start or type(item.get('time_known')) is not bool:
            return 'missing_event_date'
        # Cancellation/postponement does not give the old occurrence a new life.
        if item['time_known']:
            if end <= at:
                return 'expired_event'
        elif end.date() < at.date():
            return 'expired_event'
        elif end.date() == at.date():
            # A calendar day is not evidence that the event is still running.
            return 'unconfirmed_event_time'
    else:
        return 'invalid_item'
    return None
