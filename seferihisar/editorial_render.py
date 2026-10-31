"""Approved ivory cards with navy/teal headings and measured, separate text fields.

All text is drawn by the renderer; an image generator never lays out headlines.
Photo framing remains identical to the three subject-reviewed crop sizes.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

from .brand import VERSION as BRAND_VERSION, logo_path
from .card_layout import CAPTION_NOTE
from .editor import event_type_label, news_type_label
from .render import NAVY, IVORY, ORANGE, TURQUOISE, font, wrap, ellipsis, graphic_body, graphic_title, readable_date_line, upper_tr
from .text_quality import TextRenderError, plain_display, ensure_glyphs

TEAL = '#08717a'
BODY = '#18364a'
LEFT, RIGHT = 80, 1000
# One size per role on every card. Only a headline or essential facts that cannot
# fit step down once; a shortened summary stays at its size.
SCALE = {'heading': (52, 44), 'date': (34,), 'details': (30, 28), 'summary': (30,), 'note': (26,), 'label': (28, 24)}
# Claimed v1 cards keep the per-card fitting they were published with.
FITTED_SCALE = {'heading': (76, 70, 64, 58, 54, 50, 46, 42), 'date': (40, 36, 34, 32, 30),
                'details': (36, 34, 32, 30, 28), 'summary': (40, 38, 36, 34, 32, 30),
                'note': (28, 26, 24), 'label': (28, 26, 24, 22)}


class TextFields:
    """Check actual ink bounds as well as reserved field bounds before saving."""

    def __init__(self, draw):
        self.draw = draw
        self.bounds = []

    def line(self, value, x, y, size, color, role, box, bold=False):
        face = font(size, bold)
        ensure_glyphs(value, face)
        bounds = self.draw.textbbox((x, y), value, font=face, anchor='lt')
        # Some glyphs (for example a bold y) have a negative left bearing.
        # Align the actual ink with the field rather than clipping that glyph.
        if bounds[0] < box[0]:
            x += box[0] - bounds[0]
            bounds = self.draw.textbbox((x, y), value, font=face, anchor='lt')
        l, t, r, b = bounds
        if l < box[0] or t < box[1] or r > box[2] or b > box[3] or l >= r or t >= b:
            raise TextRenderError('Editorial text exceeds its reserved field')
        for old, _ in self.bounds:
            if max(l, old[0]) < min(r, old[2]) and max(t, old[1]) < min(b, old[3]):
                raise TextRenderError('Editorial text fields overlap')
        self.draw.text((x, y), value, font=face, fill=color, anchor='lt')
        self.bounds.append((bounds, role))

    def block(self, value, box, sizes, role, *, bold=False, color=BODY, complete=False, heading=False, max_lines=None):
        value = '\n'.join(plain_display(line) for line in value.splitlines()).strip()
        if not value:
            if heading:
                raise TextRenderError('Empty editorial heading')
            return box[1]
        for size in sizes:
            face = font(size, bold)
            ensure_glyphs(value, face)
            lines = wrap(self.draw, value, face, box[2] - box[0] - 4)
            step = size + 12
            capacity = max(0, (box[3] - box[1]) // step)
            if max_lines is not None:
                capacity = min(capacity, max_lines)
            if len(lines) <= capacity:
                break
        if capacity < 1 or (complete and len(lines) > capacity):
            raise TextRenderError('Editorial heading or essential facts do not fit')
        visible = lines[:capacity]
        if len(lines) > capacity:
            visible[-1] = ellipsis(self.draw, visible[-1], face, box[2] - box[0])
        for i, line in enumerate(visible):
            if not line:
                continue
            # Only heading lines get the accent; summary/date/venue/fee remain
            # separate fields. Never derive body copy from a colored title.
            ink = (NAVY if i == 0 else TEAL) if heading else color
            if heading and len(visible) == 1 and ' ' in line:
                # Even a short event name keeps the chosen two-color identity.
                # Split only at a word boundary, without adding/rewording text.
                words = line.split(' ')
                split = max(1, len(words) // 2)
                first = ' '.join(words[:split])
                last = ' '.join(words[split:])
                self.line(first, box[0], box[1], size, NAVY, role, box, bold)
                # A trailing space contributes advance but is not heading ink.
                # DejaVu's next capital may have a negative bearing; measuring
                # the space as ink falsely reports two adjacent words overlap.
                advance = self.draw.textlength(first + ' ', font=face)
                self.line(last, box[0] + advance, box[1], size, TEAL, role, box, bold)
                continue
            self.line(line, box[0], box[1] + i * step, size, ink, role, box, bold)
        return box[1] + len(visible) * step


def _footer_band(image):
    width, height = image.size
    scale, band_height = 4, 180
    mask = Image.new('L', (width * scale, band_height * scale), 0)
    points = [(0, height - 42), (width, height - 98),
              (width, height - 74), (0, height - 18)]
    ImageDraw.Draw(mask).polygon([(x * scale, (y - height + band_height) * scale) for x, y in points], fill=255)
    mask = mask.resize((width, band_height), Image.Resampling.LANCZOS)
    image.paste(TURQUOISE, (0, height - band_height, width, height), mask)


def _event_body(value):
    """Retain literal facts; put fee before optional organizer/address overflow."""
    lines = [plain_display(line) for line in value.splitlines() if plain_display(line)]
    fees = [line for line in lines if line.startswith(('Ücret:', 'Ücretsiz', 'Ücretli'))]
    organizers = [line for line in lines if line.startswith('Düzenleyen:')]
    venues = [line for line in lines if line not in fees and line not in organizers]
    return '\n'.join(venues + fees + organizers)


def editorial_card(title: str, body: str, category: str, target: Path, *, story=False, index='',
                   illustration=None, preview=False, event_details=False, photo_centering=(0.5, 0.5),
                   story_details=False, source_photo=False, caption_note=False, brand_version=BRAND_VERSION,
                   fixed_scale=True):
    sizes = SCALE if fixed_scale else FITTED_SCALE
    width, height = 1080, 1920 if story else 1350
    top, bottom = (260, 1600) if story else (0, 1260)
    brand_top = bottom - 70
    image = Image.new('RGB', (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    fields = TextFields(draw)
    header_bottom = top + 144
    header = (LEFT, top, RIGHT, header_bottom - 12)
    fields.line('SEFERİHİSAR', LEFT, top + 35, 34, IVORY, 'brand', header, True)
    fields.line('OFFICIAL', LEFT, top + 80, 24, TURQUOISE, 'brand', header)
    with Image.open(logo_path(brand_version)) as original:
        logo = ImageOps.fit(original.convert('RGB'), (116, 116), method=Image.Resampling.LANCZOS)
    mask = Image.new('L', logo.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 115, 115), fill=255)
    image.paste(logo, (RIGHT - 116, top + 12), mask)
    draw.rectangle((0, header_bottom - 5, width, header_bottom), fill=ORANGE)

    hero_bottom = header_bottom + 20
    if illustration is not None:
        hero_bottom = top + (650 if story and story_details else 730 if story else 580)
        with Image.open(illustration) as original:
            photo = (ImageOps.pad(original.convert('RGB'), (width, hero_bottom - header_bottom),
                                 method=Image.Resampling.LANCZOS, color=NAVY) if source_photo
                     else ImageOps.fit(original.convert('RGB'), (width, hero_bottom - header_bottom),
                                       method=Image.Resampling.LANCZOS, centering=photo_centering))
        image.paste(photo, (0, header_bottom))
    draw.rectangle((0, hero_bottom, width, brand_top - 12), fill=IVORY)
    draw.rectangle((0, hero_bottom, width, hero_bottom + 5), fill=TURQUOISE)

    display_title, notice = graphic_title(title, category, event_details)
    display_title = plain_display(display_title)
    label = 'TASARIM ÖRNEĞİ' if preview else upper_tr(event_type_label(category, display_title) if event_details else news_type_label(category, display_title))
    if notice and not preview:
        label += ' • ' + notice
    category_top = hero_bottom + 30
    for size in sizes['label']:
        label_width = int(draw.textlength(label, font=font(size, True))) + 36
        if label_width <= RIGHT - LEFT:
            break
    if label_width > RIGHT - LEFT:
        raise TextRenderError('Editorial category does not fit')
    draw.rounded_rectangle((LEFT, category_top, LEFT + label_width, category_top + 44), radius=8, fill=ORANGE)
    fields.line(label, LEFT + 18, category_top + 7, size, NAVY, 'category',
                (LEFT, category_top, RIGHT, category_top + 44), True)
    title_top = category_top + 66
    photo = illustration is not None
    heading_height = (180 if event_details else 228) if photo else 350
    # Footer and note are reserved before fitting any content. The title can
    # never borrow space from the following date, body or caption note.
    content_bottom = brand_top - 28 - (52 if caption_note else 0)
    title_end = fields.block(display_title,
                            (LEFT, title_top, RIGHT, min(title_top + heading_height, content_bottom - 150)),
                            sizes['heading'], 'heading',
                            bold=True, complete=True, heading=True, max_lines=4 if not photo else 3)
    content = graphic_body(body, display_title)
    y = title_end + 24
    if event_details:
        date_line, _, rest = content.partition('\n')
        date_end = fields.block(readable_date_line(date_line),
                               (LEFT, y, RIGHT, min(y + 100, content_bottom - 40)),
                               sizes['date'], 'date', bold=True, color=NAVY, complete=True)
        y = date_end + 20
        details = _event_body(rest)
        # Every venue and fee is literal source-derived text. If the minimum
        # readable size cannot hold the essential details, withhold the card.
        try:
            content_end = fields.block(details, (LEFT, y, RIGHT, content_bottom),
                                       sizes['details'], 'details', complete=True)
        except TextRenderError:
            # An organizer is supplementary on the card; it stays complete in
            # the caption. Do not discard a date, venue or fee to retain it.
            if 'Düzenleyen:' not in details:
                raise
            essential = '\n'.join(line for line in details.splitlines() if not line.startswith('Düzenleyen:'))
            content_end = fields.block(essential, (LEFT, y, RIGHT, content_bottom),
                                       sizes['details'], 'details', complete=True)
    else:
        # This is an explicitly shortened on-card excerpt, not a rewritten
        # claim. The complete factual text and source remain in the caption.
        content_end = fields.block(content, (LEFT, y, RIGHT, content_bottom),
                                   sizes['summary'], 'summary', max_lines=7 if not photo else 5)
    if caption_note:
        fields.block(CAPTION_NOTE, (LEFT, content_end + 12, RIGHT, brand_top - 24),
                     sizes['note'], 'note', color=TEAL, complete=True)
    draw.line((LEFT, brand_top - 8, RIGHT, brand_top - 8), fill=TURQUOISE, width=2)
    fields.line('@seferihisarofficial', LEFT, brand_top + 23, 23, IVORY, 'handle',
                (LEFT, brand_top, RIGHT, bottom), True)
    if index and index != '1/1':
        face = font(23)
        fields.line(index, RIGHT - draw.textlength(index, font=face), brand_top + 23, 23, ORANGE,
                    'page', (LEFT, brand_top, RIGHT, bottom))
    _footer_band(image)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'JPEG', quality=95, subsampling=0)
