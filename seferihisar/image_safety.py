"""Strict metadata-free JPEG boundary; standard library for the state writer."""
from __future__ import annotations

MAX_IMAGE_BYTES = 512 * 1024
MAX_CACHE_BYTES = 12 * 1024 * 1024
MAX_CACHED_IMAGES = 80
MAX_OCR_FINDINGS = 32
MAX_OCR_TEXT = 160

# Visual review confirmed invented stall lettering in this exact cleaned JPEG,
# although OCR missed it. Block those bytes permanently before OCR; this does
# not imply that OCR finds every lettering defect in other generated photos.
REVIEWED_LETTERING_SHA256 = frozenset({
    '5cc335d268a834ecdd538a7e8e68f9be979640e164132e33906acd52e407dada',
})


class IllustrationTextRejected(ValueError):
    """Rejected lettering, with bounded evidence for a private review artifact.

    Findings never enter the exception message, logs or public durable state.
    """

    def __init__(self, message='Illustration lettering rejected', *, findings=None):
        super().__init__(message)
        self.findings = [
            {'text': finding['text'][:MAX_OCR_TEXT],
             'confidence': finding['confidence'], 'box': dict(finding['box'])}
            for finding in (findings or [])[:MAX_OCR_FINDINGS]
        ]


class IllustrationCheckUnavailable(ValueError):
    """OCR could not verify the scene; callers must use their branded fallback."""


def ocr_available() -> bool:
    # Lazy, standard-library imports keep the durable-state writer independent
    # of both Pillow and installed system programs.
    import shutil
    import subprocess
    binary = shutil.which('tesseract')
    if not binary:
        return False
    try:
        result = subprocess.run([binary, '--list-langs'], check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10)
        languages = result.stdout.decode('utf-8', errors='strict').splitlines()
        return {'eng', 'tur'} <= {language.strip() for language in languages}
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False


def _scan_words(binary: str, data: bytes, mode: int) -> list[dict]:
    """Read one complete, bounded TSV result without treating scene texture as text."""
    import csv
    import io
    import math
    import subprocess
    try:
        result = subprocess.run([binary, 'stdin', 'stdout', '-l', 'eng+tur', '--psm', str(mode), 'tsv'],
                                input=data, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=15)
        if len(result.stdout) > 256 * 1024:
            raise IllustrationCheckUnavailable('Illustration text check unavailable')
        reader = csv.DictReader(io.StringIO(result.stdout.decode('utf-8', errors='strict')), delimiter='\t')
        expected = ['level', 'page_num', 'block_num', 'par_num', 'line_num', 'word_num',
                    'left', 'top', 'width', 'height', 'conf', 'text']
        if reader.fieldnames != expected:
            raise IllustrationCheckUnavailable('Illustration text check unavailable')
        saw_page = False
        words = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise IllustrationCheckUnavailable('Illustration text check unavailable')
            confidence = float(row['conf'])
            if not math.isfinite(confidence):
                raise IllustrationCheckUnavailable('Illustration text check unavailable')
            box = {field: int(row[field]) for field in ('left', 'top', 'width', 'height')}
            if any(not 0 <= value <= 768 for value in box.values()):
                raise IllustrationCheckUnavailable('Illustration text check unavailable')
            saw_page |= row['level'] == '1'
            letters = ''.join(char for char in row['text'] if char.isalnum())
            if letters:
                words.append({'text': row['text'], 'letters': letters,
                              'token': ''.join(char for char in letters.casefold() if char.isalnum()),
                              'confidence': confidence, 'box': box})
        if not saw_page:
            raise IllustrationCheckUnavailable('Illustration text check unavailable')
        return words
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, csv.Error):
        raise IllustrationCheckUnavailable('Illustration text check unavailable') from None


def _same_region(first: dict, second: dict) -> bool:
    """Require overlap covering at least half of the smaller positive-area box."""
    area = min(first['width'] * first['height'], second['width'] * second['height'])
    if area <= 0:
        return False
    width = max(0, min(first['left'] + first['width'], second['left'] + second['width']) -
                max(first['left'], second['left']))
    height = max(0, min(first['top'] + first['height'], second['top'] + second['height']) -
                 max(first['top'], second['top']))
    return 2 * width * height >= area


def _contrast_words(binary: str, data: bytes) -> list[list[dict]]:
    """Read lettering that colour-page segmentation can skip as photo graphics.

    A fixed full-image black/white view separates ink-like shapes from colour
    texture. Temporary pixels stay in memory; the cached/rendered photo stays
    untouched. Both scans use full-scene modes, never a forced single word.
    """
    import io
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as image:
            contrast = image.convert('L').point(lambda value: 255 if value >= 128 else 0)
            pixels = Image.new('RGB', image.size)
            pixels.paste(contrast.convert('RGB'))
            target = io.BytesIO()
            pixels.save(target, format='PNG')
        return [_scan_words(binary, target.getvalue(), mode) for mode in (11, 6)]
    except (OSError, ValueError):
        raise IllustrationCheckUnavailable('Illustration text check unavailable') from None


def validate_text_free_illustration(data: bytes):
    """Reject lettering before the account's own text/logo is added.

    Two full-scene segmentations distinguish short apparent words from natural
    texture. Possible years and strongly recognized whole words remain unsafe
    in either scan; other candidates need matching text in the same image area.
    A fixed full-image contrast view also checks years and whole words that
    colour-page segmentation can skip as part of a graphic. This extra view
    needs agreement between both segmentations, because binarization can turn
    scene texture into strongly recognized apparent words.
    OCR is an extra safeguard, not proof of the depicted scene's factual truth.
    Missing programs, missing language data and malformed output fail closed.
    Bounded evidence stays on the exception for a separate review artifact.
    """
    import hashlib
    import re
    import shutil
    validate_jpeg(data)
    if hashlib.sha256(data).hexdigest() in REVIEWED_LETTERING_SHA256:
        raise IllustrationTextRejected()
    binary = shutil.which('tesseract')
    if not binary:
        raise IllustrationCheckUnavailable('Illustration text check unavailable')
    # Both complete TSV results must be valid before any acceptance decision.
    scans = [_scan_words(binary, data, mode) for mode in (11, 6)]
    findings, seen = [], set()

    def remember(word):
        signature = (word['text'], word['confidence'], tuple(word['box'].values()))
        if signature not in seen and len(findings) < MAX_OCR_FINDINGS:
            seen.add(signature)
            findings.append(word)

    def directly_unsafe(word):
        # An uncertain 19xx/20xx must not become a fabricated event date.
        year = bool(re.search(r'(?:19|20)\d{2}', word['letters']))
        return ((year and word['confidence'] >= 0) or
                (len(word['letters']) >= 4 and word['confidence'] >= 80))

    for words in scans:
        for word in words:
            if directly_unsafe(word):
                remember(word)

    def candidate(word):
        length, confidence = len(word['letters']), word['confidence']
        return (length >= 2 and confidence >= 20) or (length == 1 and confidence >= 80)

    def confirm(results, predicate):
        second_candidates = {}
        for word in results[1]:
            if predicate(word):
                second_candidates.setdefault(word['token'], []).append(word)
        for first in results[0]:
            if predicate(first):
                for second in second_candidates.get(first['token'], []):
                    if _same_region(first['box'], second['box']):
                        remember(first)
                        remember(second)
                        break

    confirm(scans, candidate)
    if findings:
        raise IllustrationTextRejected(findings=findings)
    # A clear colour-image rejection needs no extra CPU work. Acceptance also
    # requires valid contrast scans: native OCR can classify an obvious date
    # label as photo graphics even when both colour-image TSVs are well formed.
    confirm(_contrast_words(binary, data), directly_unsafe)
    if findings:
        raise IllustrationTextRejected(findings=findings)


def validate_photo_not_text_graphic(data: bytes):
    """Allow incidental scene text in a real photo, never a headline graphic.

    An article-bound photograph may show a shop sign or a banner, but a collage
    of headline lettering or a date card is not a photograph of the story.
    Words count only when both full-scene segmentations agree on the same
    token in the same area. Missing OCR fails closed.
    """
    import io
    import re
    import shutil
    from PIL import Image
    validate_jpeg(data)
    binary = shutil.which('tesseract')
    if not binary:
        raise IllustrationCheckUnavailable('Illustration text check unavailable')
    first, second = (_scan_words(binary, data, mode) for mode in (11, 6))
    confirmed = [word for word in first
                 if len(word['letters']) >= 3 and word['confidence'] >= 60
                 and any(other['token'] == word['token'] and _same_region(word['box'], other['box'])
                         for other in second)]
    with Image.open(io.BytesIO(data)) as image:
        area = image.width * image.height
    lettering = sum(word['box']['width'] * word['box']['height'] for word in confirmed)
    if (len(confirmed) >= 4 or lettering >= area * 0.03
            or any(re.search(r'(?:19|20)\d{2}', word['letters']) for word in confirmed)):
        raise IllustrationTextRejected('Text graphic rejected', findings=confirmed)


def validate_jpeg(data: bytes):
    if not isinstance(data, bytes) or not 20 <= len(data) <= MAX_IMAGE_BYTES or data[:2] != b'\xff\xd8':
        raise ValueError('Invalid illustration bytes')
    position, frame = 2, False
    while position < len(data):
        if data[position] != 255 or position + 4 > len(data):
            raise ValueError('Invalid illustration header')
        marker = data[position + 1]
        length = int.from_bytes(data[position + 2:position + 4], 'big')
        end = position + 2 + length
        if length < 2 or end > len(data):
            raise ValueError('Invalid illustration segment')
        segment = data[position + 4:end]
        # Only Pillow's baseline RGB output. EXIF, comments, thumbnails and
        # arbitrary APP metadata cannot carry private text into public state.
        if marker == 0xe0:
            if len(segment) != 14 or segment[:5] != b'JFIF\x00' or segment[-2:] != b'\x00\x00':
                raise ValueError('Unexpected illustration metadata')
        elif marker == 0xc0:
            if len(segment) != 15 or segment[0] != 8 or segment[5] != 3:
                raise ValueError('Invalid illustration frame')
            height, width = int.from_bytes(segment[1:3], 'big'), int.from_bytes(segment[3:5], 'big')
            if not 1 <= width <= 768 or not 1 <= height <= 768:
                raise ValueError('Oversized illustration')
            frame = True
        elif marker == 0xda:
            if not frame or len(segment) != 10:
                raise ValueError('Invalid illustration scan')
            # Baseline entropy data allows stuffed FF and restart markers only.
            position = end
            while position < len(data):
                position = data.find(b'\xff', position)
                if position < 0 or position + 1 >= len(data):
                    break
                following = data[position + 1]
                if following == 0xd9 and position == len(data) - 2:
                    return
                if following != 0 and not 0xd0 <= following <= 0xd7:
                    raise ValueError('Unexpected illustration trailer')
                position += 2
            raise ValueError('Truncated illustration')
        elif marker not in (0xdb, 0xc4, 0xdd):
            raise ValueError('Unexpected illustration metadata')
        position = end
    raise ValueError('Missing illustration scan')
