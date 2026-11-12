"""Crop a publisher's headline band off the bottom of its own article picture.

Owner request, 12 Nov 2026: the article's real picture is always used, and the
headline a publisher printed under it is cut away. This is a plain crop of the
actual file. Nothing is redrawn, and a logo or a band elsewhere in the frame
leaves the picture exactly as the publisher made it.
"""
import io

from PIL import Image

MIN_KEEP = 0.55   # the photograph above the band stays most of the frame
MIN_HEIGHT = 280
MAX_ASPECT = 2.6  # the widest picture the card can still show whole


def band_top(words, width, height):
    """Top of large lettering that closes the bottom of the frame, or None."""
    large = [w for w in words if w['confidence'] >= 60 and len(w['letters']) >= 3
             and w['box']['height'] >= height * .04]
    if len(large) < 2:
        return None
    top = min(w['box']['top'] for w in large)
    bottom = max(w['box']['top'] + w['box']['height'] for w in large)
    span = max(w['box']['left'] + w['box']['width'] for w in large) - min(w['box']['left'] for w in large)
    # Lettering higher up means a collage, not a band under a photograph.
    if top < height * MIN_KEEP or bottom < height * .82 or span < width * .45:
        return None
    return top


def band_edge(image, top):
    """Walk up from the lettering through the band's flat backing colour."""
    grey = image.convert('L')
    width, height = grey.size
    limit = max(0, top - int(height * .12))
    row = top
    while row > limit:
        line = sorted(grey.crop((0, row - 1, width, row)).tobytes())
        if line[int(len(line) * .9)] - line[int(len(line) * .1)] > 36:
            break  # a row of the photograph, not of the band
        row -= 1
    return row


def crop(data, scans):
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert('RGB')
    width, height = image.size
    tops = [top for top in (band_top(words, width, height) for words in scans) if top is not None]
    if not tops:
        return data
    edge = band_edge(image, min(tops))
    if edge < height * MIN_KEEP or edge < MIN_HEIGHT or width / edge > MAX_ASPECT:
        return data
    from .image_safety import validate_jpeg
    target = io.BytesIO()
    image.crop((0, 0, width, edge)).save(target, format='JPEG', quality=82, optimize=True)
    result = target.getvalue()
    validate_jpeg(result)
    return result


def without_band(data):
    """The same cleaned JPEG without a bottom headline band.

    Unchanged when no band is found, the rest would be too small for a card, or
    the text reader is missing: a picture is never held back for its lettering.
    """
    import shutil
    from .image_safety import IllustrationCheckUnavailable, _scan_words, ocr_available
    binary = shutil.which('tesseract')
    if not binary or not ocr_available():
        return data
    try:
        return crop(data, [_scan_words(binary, data, mode) for mode in (11, 6)])
    except (IllustrationCheckUnavailable, ValueError, OSError):
        return data
