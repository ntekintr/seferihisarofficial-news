"""Crop a publisher's headline bands off its own article picture.

Owner request, 12 Nov 2026: the article's real picture is always used, and the
headline a publisher printed over its edge is cut away. 13 Nov: live cards still
showed headlines printed across the top (Haber32) and a bottom band with the
site's address (Ajans32), so both edges are checked and every scan, including
the black/white contrast view that reads outlined coloured letters, is used.

This is a plain crop of the actual file. Nothing is redrawn; lettering in the
middle of the photograph stays as the publisher made it.
"""
import io

from PIL import Image

MIN_KEEP = 0.5    # the photograph between the bands stays at least half the frame
MIN_HEIGHT = 200
MAX_ASPECT = 3.6  # wider than this and the card would show a thin strip
EDGE = 0.5        # a band lies wholly in its own half of the frame


def footer_band(image):
    """Top of an outlined headline standing on a black address strip, or None.

    Ajans32 prints its headline in coloured letters with a white outline over
    the photograph, above a black strip with the site's address. OCR cannot
    read those letters (13 Nov), so this template is found from its pixels: a
    near-black strip closes the frame, and the rows just above it hold both
    strongly coloured fill and white outline. Natural photographs rarely do.
    """
    import colorsys
    rgb = image.convert('RGB')
    width, height = rgb.size
    pixels = rgb.load()
    step = 2

    def share(row, test):
        return sum(test(pixels[x, row]) for x in range(0, width, step)) * step / width

    dark = lambda p: max(p) < 40
    white = lambda p: min(p) > 225
    def coloured(p):
        if min(p) > 225:
            return False
        _, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in p))
        return s > .6 and v > .45
    # The strip may carry a thin coloured rule along its edges.
    strip = [y for y in range(height - 1, int(height * .86), -1) if share(y, dark) > .6]
    if len(strip) < height * .05:
        return None
    row = min(strip) - 1
    lettering, gap, top = 0, 0, None
    while row >= 0 and gap <= 20:
        if share(row, white) >= .03 and share(row, lambda p: white(p) or coloured(p)) >= .25:
            lettering, gap, top = lettering + 1, 0, row
        else:
            gap += 1
            if top is None and gap > 16:
                return None
        row -= 1
    if top is None or lettering < height * .12:
        return None
    return max(0, top - 6)


def lettering(scans, height):
    """Large, confidently read words from every scan."""
    return [w for words in scans for w in words
            if w['confidence'] >= 55 and len(w['letters']) >= 3 and w['box']['height'] >= height * .035]


def spread(words, width):
    return max(w['box']['left'] + w['box']['width'] for w in words) - min(w['box']['left'] for w in words) >= width * .4


def bottom_band(words, width, height):
    """Top of large lettering that closes the bottom of the frame, or None."""
    low = [w for w in words if w['box']['top'] >= height * EDGE]
    if len(low) < 2 or not spread(low, width):
        return None
    if max(w['box']['top'] + w['box']['height'] for w in low) < height * .8:
        return None
    return min(w['box']['top'] for w in low)


def top_band(words, small, width, height):
    """Bottom of large lettering that opens the top of the frame, or None.

    A site name printed just under the band (a logo line) goes with it.
    """
    high = [w for w in words if w['box']['top'] + w['box']['height'] <= height * EDGE]
    if len(high) < 2 or not spread(high, width) or min(w['box']['top'] for w in high) > height * .15:
        return None
    bottom = max(w['box']['top'] + w['box']['height'] for w in high)
    for word in small:
        box = word['box']
        if bottom <= box['top'] + box['height'] <= height * EDGE and box['top'] <= bottom + height * .08:
            bottom = max(bottom, box['top'] + box['height'])
    return bottom


def flat(grey, row):
    width = grey.size[0]
    line = sorted(grey.crop((0, row, width, row + 1)).tobytes())
    return line[int(len(line) * .9)] - line[int(len(line) * .1)] <= 36


def band_edge(image, top):
    """Walk up from bottom lettering through the band's flat backing colour."""
    grey = image.convert('L')
    limit = max(0, top - int(image.size[1] * .12))
    row = top
    while row > limit and flat(grey, row - 1):
        row -= 1
    return row


def top_edge(image, bottom):
    """Walk down from top lettering through the band's flat backing colour."""
    grey = image.convert('L')
    height = image.size[1]
    limit = min(height, bottom + int(height * .12))
    row = bottom
    while row < limit and flat(grey, row):
        row += 1
    return row


def crop(data, scans):
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert('RGB')
    width, height = image.size
    words = lettering(scans, height)
    small = [w for ws in scans for w in ws if w['confidence'] >= 50 and len(w['letters']) >= 3]
    low, high = bottom_band(words, width, height), top_band(words, small, width, height)
    footer = footer_band(image)
    if low is None and high is None and footer is None:
        return data
    top = top_edge(image, high) if high is not None else 0
    bottom = band_edge(image, low) if low is not None else height
    if footer is not None:
        bottom = min(bottom, footer)
    kept = bottom - top
    if kept < height * MIN_KEEP or kept < MIN_HEIGHT or width / kept > MAX_ASPECT:
        return data
    from .image_safety import validate_jpeg
    target = io.BytesIO()
    image.crop((0, top, width, bottom)).save(target, format='JPEG', quality=82, optimize=True)
    result = target.getvalue()
    validate_jpeg(result)
    return result


def without_band(data):
    """The same cleaned JPEG without headline bands at its top or bottom.

    Unchanged when no band is found, the rest would be too small for a card, or
    the text reader is missing: a picture is never held back for its lettering.
    """
    import shutil
    from .image_safety import IllustrationCheckUnavailable, _contrast_words, _scan_words, ocr_available
    binary = shutil.which('tesseract')
    if not binary or not ocr_available():
        return data
    try:
        scans = [_scan_words(binary, data, mode) for mode in (11, 6)] + _contrast_words(binary, data)
        return crop(data, scans)
    except (IllustrationCheckUnavailable, ValueError, OSError):
        return data
