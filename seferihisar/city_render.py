"""Cards for reviewed city features: a licensed photo, measured text, visible credit.

Same brand frame and text-field checks as the editorial cards. Every word on the
card comes from config/city-features.json; nothing is generated or inferred.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .brand import logo_path
from .editorial_render import BODY, LEFT, RIGHT, TEAL, TextFields, _footer_band
from .render import IVORY, NAVY, ORANGE, TURQUOISE, font
from .text_quality import TextRenderError, plain_display

HANDLE = '@seferihisarofficial'
BRAND = ('SEFERİHİSAR', 'OFFICIAL')


def credit_line(photo: dict) -> str:
    return 'Fotoğraf: ' + plain_display(photo['author']) + ' · ' + photo['license']


def render(entry: dict, photo: dict, photo_path: Path, target: Path):
    story = entry['format'] == 'story'
    width, height = 1080, 1920 if story else 1350
    top, bottom = (260, 1600) if story else (0, 1260)
    brand_top = bottom - 70
    image = Image.new('RGB', (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    fields = TextFields(draw)
    header_bottom = top + 144
    header = (LEFT, top, RIGHT, header_bottom - 12)
    fields.line(BRAND[0], LEFT, top + 35, 34, IVORY, 'brand', header, True)
    fields.line(BRAND[1], LEFT, top + 80, 24, TURQUOISE, 'brand', header)
    with Image.open(logo_path()) as original:
        logo = ImageOps.fit(original.convert('RGB'), (116, 116), method=Image.Resampling.LANCZOS)
    mask = Image.new('L', logo.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 115, 115), fill=255)
    image.paste(logo, (RIGHT - 116, top + 12), mask)
    draw.rectangle((0, header_bottom - 5, width, header_bottom), fill=ORANGE)

    hero_bottom = header_bottom + (620 if story else 440)
    with Image.open(photo_path) as original:
        hero = ImageOps.fit(original.convert('RGB'), (width, hero_bottom - header_bottom),
                            method=Image.Resampling.LANCZOS, centering=tuple(photo.get('centering', (0.5, 0.5))))
    image.paste(hero, (0, header_bottom))
    # Attribution stays on the picture itself, so a reshared card keeps it.
    credit = credit_line(photo)
    face = font(20)
    strip_top = hero_bottom - 40
    shade = Image.new('RGBA', (width, 40), (0, 0, 0, 120))
    image.paste(shade, (0, strip_top), shade)
    fields.line(credit, RIGHT - draw.textlength(credit, font=face), strip_top + 10, 20, IVORY, 'credit',
                (LEFT, strip_top, RIGHT, hero_bottom))

    draw.rectangle((0, hero_bottom, width, brand_top - 12), fill=IVORY)
    draw.rectangle((0, hero_bottom, width, hero_bottom + 5), fill=TURQUOISE)
    label = entry['label']
    label_top = hero_bottom + 30
    label_width = int(draw.textlength(label, font=font(28, True))) + 36
    if label_width > RIGHT - LEFT:
        raise TextRenderError('City feature label does not fit')
    draw.rounded_rectangle((LEFT, label_top, LEFT + label_width, label_top + 44), radius=8, fill=ORANGE)
    fields.line(label, LEFT + 18, label_top + 7, 28, NAVY, 'category', (LEFT, label_top, RIGHT, label_top + 44), True)

    content_bottom = brand_top - 28
    title_top = label_top + 66
    if story:
        # The question is the card: large, complete, never shortened.
        fields.block(entry['title'], (LEFT, title_top, RIGHT, content_bottom - 140),
                     (60, 54, 48), 'heading', bold=True, complete=True, heading=True, max_lines=4)
        box_top = content_bottom - 112
        draw.rounded_rectangle((LEFT - 16, box_top, RIGHT + 16, content_bottom + 8), radius=14, outline=TEAL, width=3)
        fields.block(entry['body'], (LEFT + 8, box_top + 18, RIGHT - 8, content_bottom - 4), (28, 26), 'note',
                     bold=True, color=TEAL, complete=True, max_lines=2)
    else:
        title_end = fields.block(entry['title'], (LEFT, title_top, RIGHT, title_top + 128),
                                 (52, 44), 'heading', bold=True, complete=True, heading=True, max_lines=2)
        body_end = fields.block(entry['body'], (LEFT, title_end + 20, RIGHT, content_bottom - 118), (30, 28, 26), 'summary',
                                color=BODY, complete=True, max_lines=6)
        box_top = max(body_end + 22, content_bottom - 104)
        draw.rounded_rectangle((LEFT - 16, box_top, RIGHT + 16, content_bottom + 8), radius=14, outline=TEAL, width=3)
        fields.block(entry['question'], (LEFT + 8, box_top + 18, RIGHT - 8, content_bottom - 4), (28, 26), 'note',
                     bold=True, color=TEAL, complete=True, max_lines=2)
    draw.line((LEFT, brand_top - 8, RIGHT, brand_top - 8), fill=TURQUOISE, width=2)
    fields.line(HANDLE, LEFT, brand_top + 23, 23, IVORY, 'handle', (LEFT, brand_top, RIGHT, bottom), True)
    _footer_band(image)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'JPEG', quality=92, subsampling=0)
