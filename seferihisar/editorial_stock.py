"""Owned generic scenes, bound to an exact subject AND fixed scene brief.

This is a local file fallback, not a source photograph or a quota override.
The normal lettering and all rendered-crop subject checks still run on it.
"""
import hashlib
import json
from pathlib import Path
import re

from .image_safety import validate_jpeg

DIRECTORY = Path(__file__).parent/'assets/editorial-scenes'

# Reviewed 26 Oct 2026 at 1080x436, 1080x506 and 1080x586: the complete
# blank desk calendar, admission tickets and pen remain visible. CLIP confuses
# intentionally blank stationery with an administrative desk. Approve only
# these immutable generic-calendar pixels; no other subject/image inherits it.
REVIEWED_CALENDAR_SHA256 = '68:63:17:cf:61:8d:08:b9:28:61:4a:54:70:b3:7d:dc:d3:8e:e4:ab:13:14:03:df:41:71:05:16:29:ef:3a:8b'


def reviewed_calendar(data, expected):
    return expected == 'event_calendar' and hashlib.sha256(data).digest().hex(':') == REVIEWED_CALENDAR_SHA256


def stock_image(expected, brief):
    try:
        manifest = json.loads((DIRECTORY/'manifest.json').read_text(encoding='utf8'))
        if manifest['version'] != 1 or not 1 <= len(manifest['scenes']) <= 40:
            return None
        matches = [r for r in manifest['scenes'] if r['subject'] == expected
                   and r['brief_sha256'] == hashlib.sha256(brief.encode()).digest().hex(':')]
        if len(matches) != 1:
            return None
        row = matches[0]
        if (row['origin'] != 'owned-generated-generic-scene'
                or not re.fullmatch(r'[a-z_]+\.jpg', row['file'])
                or row['file'] != expected+'.jpg'):
            return None
        data = (DIRECTORY/row['file']).read_bytes()
        validate_jpeg(data)
        return data if hashlib.sha256(data).digest().hex(':') == row['sha256'] else None
    except (OSError, ValueError, KeyError, TypeError):
        return None
