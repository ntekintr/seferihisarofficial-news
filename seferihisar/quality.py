"""Conservative publication holds for incomplete or superseded social notices."""
import re

from .domain import normalized


def news_quality_reason(item: dict) -> str | None:
    if item.get('kind') != 'news':
        return None
    title = item.get('title', '')
    if not isinstance(title, str) or not re.search(r'[^\W\d_]', title):
        # A contact number, punctuation or emoji alone cannot describe a story.
        return 'insufficient_headline'
    if (item.get('source_id') == 'instagram-sehayder'
            and re.search(r'\b(?:ailesi|sahibi) bulundu\b|\b(?:sahiplendirildi|yuvalandirildi)\b', normalized(title))):
        # This source retains the earlier appeal/contact instructions below its
        # resolved heading. Do not republish that old call for help as current.
        return 'resolved_community_notice'
    return None
