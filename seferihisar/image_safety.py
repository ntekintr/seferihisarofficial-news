"""Strict metadata-free JPEG boundary; standard library for the state writer."""
from __future__ import annotations

MAX_IMAGE_BYTES = 512 * 1024
MAX_CACHE_BYTES = 12 * 1024 * 1024
MAX_CACHED_IMAGES = 80
MAX_OCR_FINDINGS = 32
MAX_OCR_TEXT = 160


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


def validate_text_free_illustration(data: bytes):
    """Reject visible AI lettering before the account's own text/logo is added.

    OCR is an extra safeguard, not proof of the depicted scene's factual truth.
    Missing programs, missing language data and malformed output fail closed.
    Bounded rejected-word evidence is attached only to the rejection exception
    for a separate private review artifact; it is never written to public state.
    """
    import csv
    import io
    import math
    import re
    import shutil
    import subprocess
    validate_jpeg(data)
    binary = shutil.which('tesseract')
    if not binary:
        raise IllustrationCheckUnavailable('Illustration text check unavailable')
    try:
        result = subprocess.run([binary, 'stdin', 'stdout', '-l', 'eng+tur', '--psm', '11', 'tsv'],
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
        findings = []
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
            # A possible four-digit year is unsafe even when the stylized font
            # makes OCR uncertain. Other short tokens require modest confidence
            # to avoid treating every decorative stroke as a written word.
            year = bool(re.search(r'(?:19|20)\d{2}', letters))
            if letters and ((year and confidence >= 0) or
                            (len(letters) >= 2 and confidence >= 20) or
                            (len(letters) == 1 and confidence >= 80)):
                if len(findings) < MAX_OCR_FINDINGS:
                    findings.append({'text': row['text'][:MAX_OCR_TEXT],
                                     'confidence': confidence, 'box': box})
        if not saw_page:
            raise IllustrationCheckUnavailable('Illustration text check unavailable')
        if findings:
            raise IllustrationTextRejected(findings=findings)
    except IllustrationTextRejected:
        raise
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError, csv.Error):
        raise IllustrationCheckUnavailable('Illustration text check unavailable') from None


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

