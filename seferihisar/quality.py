"""Conservative publication holds for incomplete or superseded social notices."""
import re

from .domain import normalized
from .text_quality import plain_display, source_body


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


def news_editorial_reason(item: dict) -> str | None:
    """Publication hold, separate from immutable source intake/provenance."""
    if item.get('kind') != 'news':
        return None
    from .domain import local
    from .editorial_voice import neutral_terms, source_voice
    if not isinstance(item.get('title'),str) or not isinstance(item.get('description'),str):
        return 'editorial_copy_required'
    title = plain_display(item.get('title',''))
    value = normalized(title)
    vague = re.search(r'^(?:böyle\b.*\bhep olsun|iyi ki varsiniz\b.*|'
                      r'dikkat(?: dikkat)*|bekle\b.*|engelli canlara öncelik|'
                      r'elleri minik\b.*|harika haber\b.*|müjde(?: müjde)*)$', value)
    if (not value or len(title)>160 or vague or title.endswith(('…','...'))
            or source_voice(neutral_terms(title))):
        return 'editorial_headline_required'
    body = source_body(item)
    if len(re.findall(r'\w+',body)) < 5 or normalized(body) == value:
        return 'editorial_copy_required'
    outside_quotes = re.sub(r'“[^”]*”|"[^"]*"','',body)
    if re.search(r'\b(?:takip etmeyi|abone olmayı|yorumlarda buluş|iyi ki varsınız|'
                 r'hep olsun|paylaşmayı unutmayın)\b',outside_quotes,re.I):
        return 'editorial_copy_required'
    from .editor import news_body
    if 'Kaynak açıklamasında “' in news_body(item):
        # The old fallback could turn unreviewed institutional/campaign voice
        # into a long quotation card. It is not an edited news summary.
        return 'editorial_copy_required'
    if item.get('source_id','').startswith('instagram-') and not local(
            title+' '+body+' '+(item.get('location') or '')):
        return 'editorial_context_required'
    return None


def publication_copy_reason(post: dict, items: dict) -> str | None:
    """Recheck the frozen draft at the actual destination, before any claim."""
    if post.get('kind') != 'news':
        return None
    item = items.get(post.get('item_id'),{})
    if item.get('kind') != 'news' or news_editorial_reason(item):
        return 'editorial_review_required'
    from .editor import headline, caption
    from .schedule import slide_body
    title = headline(item,'news')
    if (post.get('title') != title or post.get('caption') != caption(item,title)
            or post.get('slides') != [{'title':title,'body':slide_body(item)}]):
        return 'editorial_copy_stale'
    return None
