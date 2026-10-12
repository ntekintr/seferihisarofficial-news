"""Strict metadata-free JPEG boundary; standard library for the state writer."""
from __future__ import annotations

MAX_IMAGE_BYTES = 512 * 1024
MAX_CACHE_BYTES = 12 * 1024 * 1024
MAX_CACHED_IMAGES = 80


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
