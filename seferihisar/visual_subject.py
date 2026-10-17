"""Conservative subject selection. A category is never evidence of an incident."""
from .editor import event_activity


def subject(item: dict) -> str | None:
    # These require the actual source photograph. A plausible generated scene
    # cannot establish who met, what flooded, or where an incident happened.
    if item.get('category') == 'outage':
        return None
    if item.get('kind') != 'event':
        # Broad news categories (transport, municipality, public) do not prove
        # that generic stock-like scenery illustrates this particular story.
        return None
    if activity := event_activity(item.get('category'), item.get('title', '')):
        return activity
    category = item.get('category')
    return category if category in (
        'theatre', 'concert', 'cinema', 'festival', 'culture', 'family',
        'sport', 'market', 'food', 'education') else None
