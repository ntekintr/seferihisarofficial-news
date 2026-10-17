"""Conservative display cleanup; never infer an actor, place or occurrence date."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from .domain import normalized


class TextRenderError(ValueError):
    """A new card cannot be read with the selected production font/layout."""


_ORNAMENTS = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF]')
_CLOSING = re.compile(
    r'^(?:iyi ki varsınız(?: sevgili çocuklar)?|'
    r'örnek davranışları, insanlığı ve merhameti hatırlattıkları için onları sevgiyle kucaklıyoruz|'
    r'destekleriniz için teşekkürler|yorumlarda buluşalım)[.!…\s]*$', re.I)
_FOLLOW = re.compile(
    r'^(?:kanalımızı|sayfamızı|bizi)\s+takip etmeyi,?\s*(?:beğenmeyi,?\s*)?'
    r'(?:abone olmayı ve\s*)?(?:sevdiklerinizle\s*)?paylaşmayı unutmayın[.!…\s]*$', re.I)


def plain_display(value: str) -> str:
    """Remove decorative emoji/control codes, preserving digits and letters."""
    value = unicodedata.normalize('NFC', value).translate(str.maketrans({'🔟':'10','➕':'+','➖':'−','✖':'×','➗':'÷'}))
    value = _ORNAMENTS.sub(' ', value)
    value = re.sub('[\ufe0e\ufe0f\u200d\u20e3]', '', value)
    value = ''.join(' ' if unicodedata.category(c) in ('Cc','Cf') else c for c in value)
    return ' '.join(value.split())


def source_lines(item: dict) -> list[str]:
    description = item.get('description') or ''
    lines = [plain_display(line) for line in description.splitlines()]
    lines = [line for line in lines if line]
    brand = normalized(re.sub(r'\bInstagram\b', '', item.get('source_name') or '', flags=re.I))
    if lines and brand and normalized(lines[-1]) in {brand+' '+town for town in ('seferihisar','urla','güzelbahçe','izmir')}:
        lines.pop()
    # A trailing brand+town signature identifies the source, not the occurrence.
    if len(lines) >= 2 and brand and normalized(lines[-2]) == brand and re.fullmatch(
            r'(?:seferihisar|urla|güzelbahçe|izmir)', normalized(lines[-1])):
        lines = lines[:-2]
    if lines and brand and normalized(lines[-1]) == brand:
        lines.pop()
    title = normalized(plain_display(item.get('title','')))
    if lines and normalized(lines[0]) == title:
        lines.pop(0)
    cleaned = []
    for line in lines:
        # Remove whole, reviewed non-factual sentences only; quoted statements
        # and factual clauses/commitments are not discarded as "promotion".
        parts = [line] if re.search('[“”"]',line) else re.split(r'(?<=[.!?])\s+',line)
        cleaned.append(' '.join(part for part in parts
                               if not _CLOSING.fullmatch(part) and not _FOLLOW.fullmatch(part)))
    return [line for line in cleaned if line]


def source_body(item: dict) -> str:
    lines = source_lines(item)
    value = ' '.join(lines)
    # Reviewed rhetorical prefix only; retain the entire factual continuation.
    value = re.sub(r'^Elleri minik kalpleri kocaman\s+', '', value, flags=re.I)
    return value[:1].translate(str.maketrans({'i':'İ','ı':'I'})).upper() + value[1:]


@lru_cache(maxsize=4096)
def _mask(typeface, character):
    value = typeface.getmask(character)
    return value.size, bytes(value)


def ensure_glyphs(value: str, typeface):
    missing = _mask(typeface, '\U0010ffff')
    for character in set(value) - set(' \n\t'):
        if character in '\ufffd\u25a1\u25af' or _mask(typeface, character) == missing:
            raise TextRenderError('Unsupported card character')
