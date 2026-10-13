"""Disclose generated imagery in captions without importing source hashtags."""
from __future__ import annotations

import re

from .editor import caption_with_hashtags

GENERATED_IMAGE_NOTE = "Görsel: yapay zekâyla hazırlanmış temsili görsel."


def generated_image_caption(caption: str, generated: bool) -> str:
    """Idempotent note, with complete source and hashtag footer reserved."""
    paragraphs = [part for part in caption.split("\n\n") if part != GENERATED_IMAGE_NOTE]
    if not generated and GENERATED_IMAGE_NOTE not in caption:
        return caption
    tags = []
    if paragraphs and re.fullmatch(r"#[a-z0-9_]+(?: #[a-z0-9_]+)*", paragraphs[-1]):
        tags = paragraphs.pop().split()
    source = paragraphs.pop() if paragraphs and paragraphs[-1].startswith("Kaynak: ") else ""
    footer = "\n\n".join(part for part in (GENERATED_IMAGE_NOTE if generated else "", source) if part)
    return caption_with_hashtags("\n\n".join(paragraphs), tags, footer=footer)

