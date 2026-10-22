"""One exact owner-requested editorial still life; never incident photography.

The actual source bytes and all three production crops were visually reviewed.
This allowlist cannot approve another story, revision text or generated image.
Automatic general-news scene generation remains prohibited.
"""
import hashlib
from pathlib import Path

URL = 'https://www.toplumsal.com.tr/haber/seferihisar-mandalinasi-kabuklari-mamaya-yagi-aromaterapiye-donusecek_30774/'
TITLE = 'Seferihisar mandalinası kabukları mamaya, yağı aromaterapiye dönüşecek'
SUBJECT = 'owner-curated-mandarin-reuse-v1'
IMAGE_SHA = '182bea0bb2f06feaf93411b1cff1a88429de827521528e70f3f2e036022faec7'
TEXT_SHA = '302c95e99f0601dd86786facbe756fc527929cf60cd7dd7eb12c3ce70797c007'


def matches(item):
    return (item.get('kind') == 'news' and item.get('source_id') == 'toplumsal-mandalina-review'
            and item.get('url') == URL and item.get('title') == TITLE
            and item.get('published_at') == '2026-10-22T10:14:00+03:00'
            and isinstance(item.get('description'), str)
            and hashlib.sha256(item.get('description', '').encode()).hexdigest() == TEXT_SHA)


def image_bytes():
    data = (Path(__file__).with_name('assets')/'owner-mandarin-reuse-20261022.jpg').read_bytes()
    validate(data)
    return data


def validate(data):
    from .image_safety import validate_jpeg
    validate_jpeg(data)
    if hashlib.sha256(data).hexdigest() != IMAGE_SHA:
        raise ValueError('Owner-curated image bytes changed')

