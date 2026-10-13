"""Bounded rejected-image evidence, outside Pages and durable public state."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .image_safety import validate_jpeg

ROOT = Path(__file__).resolve().parents[1]
MAX_REVIEW_IMAGES = 4


def save_rejected_image(key: str, data: bytes, findings: list):
    if os.getenv('ILLUSTRATION_REVIEW_ENABLED') != 'true' or not re.fullmatch(r'[a-f0-9]{24}', key):
        return
    directory = ROOT / 'work' / 'illustration-review'
    # Evidence can never be redirected into dist/state/site through a symlink.
    if directory.resolve() != directory or any(p.is_symlink() for p in (directory, directory.parent)):
        return
    try:
        validate_jpeg(data)
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / (key + '.jpg')).exists() or len(list(directory.glob('*.jpg'))) >= MAX_REVIEW_IMAGES:
            return
        with (directory / (key + '.jpg')).open('xb') as image:
            image.write(data)
        report = json.dumps({
            'image_key': key, 'code': 'illustration_lettering_rejected',
            'approved_for_publication': False, 'findings': findings[:32],
        }, ensure_ascii=False, indent=2)
        with (directory / (key + '.json')).open('x', encoding='utf-8') as document:
            document.write(report)
    except (OSError, ValueError, TypeError):
        # Review evidence is optional and can never make a rejected image pass.
        return

