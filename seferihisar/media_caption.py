"""Keep attribution in captions without image-production boilerplate."""
from __future__ import annotations

import re

from .editor import caption_with_hashtags

GENERATED_IMAGE_NOTE = "Görsel: yapay zekâyla hazırlanmış temsili görsel."


def generated_image_caption(caption: str, generated: bool) -> str:
    """Remove the legacy note; preserve news text, source links and hashtags.

    The generation flag remains compatible with research/publisher callers.
    Actual news discussing AI is content, so only our exact old note is removed.
    """
    paragraphs = [part for part in caption.split("\n\n") if part.strip() != GENERATED_IMAGE_NOTE]
    if GENERATED_IMAGE_NOTE not in caption:
        return caption
    tags = []
    if paragraphs and re.fullmatch(r"#[a-z0-9_]+(?: #[a-z0-9_]+)*", paragraphs[-1]):
        tags = paragraphs.pop().split()
    source = paragraphs.pop() if paragraphs and paragraphs[-1].startswith("Kaynak: ") else ""
    return caption_with_hashtags("\n\n".join(paragraphs), tags, footer=source)

