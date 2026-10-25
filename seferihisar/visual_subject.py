"""Conservative subject selection. A category is never evidence of an incident."""
from .editor import event_activity


def subject(item: dict) -> str | None:
    from .owner_curated import matches, SUBJECT
    if matches(item):
        return SUBJECT
    from .visual_topics import news_subjects
    if item.get('visual_calendar') is True and item.get('kind') == 'event':
        return 'event_calendar'
    if item.get('kind') != 'event' or item.get('category') == 'outage':
        return news_subjects(item)[1]
    if activity := event_activity(item.get('category'), item.get('title', '')):
        return activity
    category = item.get('category')
    return category if category in (
        'theatre', 'concert', 'cinema', 'festival', 'culture', 'family',
        'sport', 'market', 'food', 'education') else None
