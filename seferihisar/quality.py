"""Conservative publication holds for incomplete or superseded social notices."""
import re

from .domain import normalized
from .text_quality import plain_display, source_body

# One phrase can appear in real news, such as a public discount. Three different
# ones in a story mean a shop or developer sales text.
SALES_PHRASES = ('ayricalikli', 'konforlu', 'modern yaşam', 'yaşam alan', 'yaşam kalite', 'yeni adres', 'prestijli',
                 'lüks', 'daire seçenek', 'satiş ofis', 'uygun fiyat', 'müşteri memnuniyet', 'kaliteli hizmet',
                 'varan indirim', 'indirim kampanya', 'indirim firsat', 'kaçirilmayacak firsat', 'alişveriş tutkun',
                 'cazip fiyat')
SALES_THRESHOLD = 3


# Owner, 26 Nov 2026 ("Barınakta", instagram-sehayder): a one-word heading cut
# from an Instagram caption, over a shelter adoption appeal with a private
# mobile number, went out as a news card. Neither is a news story.
MIN_HEADLINE_WORDS = 3
# Turkish mobile numbers: 05xx / +90 5xx / 90 5xx / 5xx, with or without
# spaces, dots, dashes or brackets. Landlines (0232..., 0246...), 444 lines and
# short codes (112, 153) never start with 5 after the optional 0/90 prefix.
MOBILE_NUMBER = re.compile(r'(?<![\d+])(?:\+\s*90|\b90)?[\s.\-]*\(?\s*0?\s*5\d{2}\s*\)?[\s.\-]*'
                           r'\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2}(?!\d)')
SOCIAL_SOURCES = ('instagram-', 'facebook-')


def mobile_number(text: str) -> bool:
    return bool(MOBILE_NUMBER.search(text or ''))


def headline_words(title: str) -> int:
    return sum(bool(re.search(r'\w', word)) for word in (title or '').split())


def caption_fragment(item: dict) -> bool:
    """A heading that is only the cut first line of a social media caption."""
    title = (item.get('title') or '').strip()
    if title.endswith(('…', '...')):
        return True
    if not str(item.get('source_id', '')).startswith(SOCIAL_SOURCES):
        return False
    prose = (item.get('description') or '').strip()
    if not title or not prose.startswith(title):
        return False
    rest = prose[len(title):]
    # The caption goes on with an ellipsis, or the length cap cut a word/sentence.
    return bool(re.match(r'\s*(?:…|\.\.)', rest) or re.match(r'\w', rest))


def headline_gate_reason(item: dict, display_title: str) -> str | None:
    if caption_fragment(item):
        return 'headline_caption_fragment'
    if headline_words(display_title) < MIN_HEADLINE_WORDS:
        return 'headline_too_short'
    return None


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
    combined = normalized(title + ' ' + str(item.get('description') or ''))
    if sum(phrase in combined for phrase in SALES_PHRASES) >= SALES_THRESHOLD:
        return 'promotional_copy_requires_review'
    return None


def news_editorial_reason(item: dict) -> str | None:
    """Publication hold, separate from immutable source intake/provenance."""
    if item.get('kind') != 'news':
        return None
    from .domain import local
    from .editorial_voice import neutral_terms, source_voice
    if not isinstance(item.get('title'),str) or not isinstance(item.get('description'),str):
        return 'editorial_copy_required'
    if mobile_number(item['title'] + '\n' + item['description']):
        # A private contact number marks an adoption/help appeal, not news.
        return 'personal_mobile_number'
    title = plain_display(item.get('title',''))
    value = normalized(title)
    vague = re.search(r'\bböyle\b.*\bhep olsun$|\biyi ki varsiniz\b|^(?:'
                      r'dikkat(?: dikkat)*|bekle\b.*|engelli canlara öncelik|'
                      r'elleri minik\b.*|harika haber\b.*|müjde(?: müjde)*)$', value)
    if (not value or len(title)>160 or vague or title.endswith(('…','...'))
            or source_voice(neutral_terms(title))):
        return 'editorial_headline_required'
    from .editor import news_title
    if reason := headline_gate_reason(item, news_title(item)):
        return reason
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
    from . import event_metadata
    from .editor import caption
    from .schedule import slide_body
    if post.get('kind') in ('weekend', 'free_week'):
        from .local_series import current_copy
        if not current_copy(post, items):
            return 'event_metadata_stale'
    item = items.get(post.get('item_id'), {})
    if item and post.get('session_ids'):
        from .schedule import session_card
        item = session_card(item, post, items)
        if item is None:
            return 'event_metadata_stale'
    if item.get('kind') == 'event' and item.get('category') != 'outage' and event_metadata.needs_review(item):
        if (post.get('caption') != caption(item, post.get('title', ''))
                or post.get('slides') != [{'title': post.get('title'), 'body': slide_body(item)}]):
            return 'event_metadata_stale'
    if post.get('kind') in ('weekly', 'monthly', 'weekend', 'free_week'):
        urls = post.get('source_urls', [])
        slides = post.get('slides', [])
        for index, url in enumerate(urls, 1):
            matches = [i for i in items.values() if i.get('kind') == 'event'
                       and url in i.get('sources', []) + [i.get('url')]]
            if any(event_metadata.needs_review(i) for i in matches):
                if (len(slides) != len(urls) + 1
                        or not any(slides[index].get('body') == slide_body(i) for i in matches)):
                    return 'event_metadata_stale'
    if post.get('kind') != 'news':
        return None
    item = items.get(post.get('item_id'),{})
    if item.get('kind') != 'news' or news_editorial_reason(item):
        return 'editorial_review_required'
    from .editor import headline, caption
    from .media_caption import without_photo_credit
    from .schedule import slide_body
    title = headline(item,'news')
    if (post.get('title') != title
            or without_photo_credit(post.get('caption', '')) != without_photo_credit(caption(item,title))
            or post.get('slides') != [{'title':title,'body':slide_body(item)}]):
        return 'editorial_copy_stale'
    return None
