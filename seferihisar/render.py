from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .domain import CATEGORIES

NAVY, IVORY, ORANGE, TURQUOISE = '#06244a', '#f4efe4', '#f58220', '#20b8c9'
ASSETS = Path(__file__).with_name('assets')


@lru_cache(maxsize=32)
def font(size: int, bold: bool = False):
    suffix = '-Bold' if bold else ''
    candidates = (
        f'/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf',
        f'/usr/share/fonts/truetype/liberation2/LiberationSans{suffix}.ttf',
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def upper_tr(value: str) -> str:
    return value.translate(str.maketrans({'i': 'İ', 'ı': 'I'})).upper()


def wrap(draw: ImageDraw.ImageDraw, text: str, typeface, width: int) -> list[str]:
    lines = []
    for paragraph in text.splitlines():
        line = ''
        for word in paragraph.split():
            while draw.textlength(word, font=typeface) > width:
                split = len(word) - 1
                while split > 1 and draw.textlength(word[:split], font=typeface) > width:
                    split -= 1
                if line:
                    lines.append(line)
                    line = ''
                lines.append(word[:split])
                word = word[split:]
            trial = (line + ' ' + word).strip()
            if draw.textlength(trial, font=typeface) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def ellipsis(draw, value, typeface, width):
    value = value.rstrip()
    while value and draw.textlength(value + '…', font=typeface) > width:
        value = value[:-1]
    return value + '…'


def text_block(draw, text, box, sizes, bold=False, color=IVORY):
    """Fit a bounded text panel; visibly mark shortened excerpts."""
    left, top, right, bottom = box
    for size in sizes:
        typeface = font(size, bold)
        lines = wrap(draw, text, typeface, right - left)
        line_height = size + 12
        if len(lines) * line_height <= bottom - top:
            break
    capacity = max(0, (bottom - top) // line_height)
    visible = lines[:capacity]
    if len(lines) > capacity and visible:
        visible[-1] = ellipsis(draw, visible[-1], typeface, right - left)
    for i, line in enumerate(visible):
        draw.text((left, top + i * line_height), line, font=typeface, fill=color, anchor='lt')
    return top + len(visible) * line_height


def card(title: str, body: str, category: str, target: Path, story: bool = False,
         index: str = '', illustration: Path | None = None, preview: bool = False):
    """Fixed branding and a per-item illustration, never a shared news scene."""
    width, height = 1080, 1920 if story else 1350
    top, bottom = (260, 1600) if story else (0, 1260)
    margin, right = 64, width - 64
    image = Image.new('RGB', (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    header_bottom = top + 144
    draw.text((margin, top + 35), 'SEFERİHİSAR', font=font(34, True), fill=IVORY, anchor='lt')
    draw.text((margin, top + 80), 'OFFICIAL', font=font(24), fill=TURQUOISE, anchor='lt')
    logo_size, logo_xy = 116, (right - 116, top + 12)
    with Image.open(ASSETS / 'logo.png') as original:
        logo = ImageOps.fit(original.convert('RGB'), (logo_size, logo_size), method=Image.Resampling.LANCZOS)
    mask = Image.new('L', (logo_size, logo_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, logo_size - 1, logo_size - 1), fill=255)
    image.paste(logo, logo_xy, mask)
    draw.rectangle((0, header_bottom - 8, width, header_bottom), fill=ORANGE)

    hero_bottom = top + (730 if story else 580)
    if illustration is not None:
        with Image.open(illustration) as source:
            hero = ImageOps.fit(source.convert('RGB'), (width, hero_bottom - header_bottom),
                                method=Image.Resampling.LANCZOS)
        image.paste(hero, (0, header_bottom))
        label = 'Temsili çizim'
        label_width = int(draw.textlength(label, font=font(23))) + 32
        draw.rounded_rectangle((right - label_width, hero_bottom - 46, right, hero_bottom - 10), 8, fill=NAVY)
        draw.text((right - label_width + 16, hero_bottom - 40), label, font=font(23), fill=IVORY, anchor='lt')
    else:
        # No unrelated landscape or made-up event when a matching image is absent.
        draw.rectangle((0, header_bottom, width, hero_bottom), fill='#0b355a')
        draw.polygon([(0, hero_bottom), (0, header_bottom + 120), (width, hero_bottom - 90),
                      (width, hero_bottom)], fill='#0e5268')
        draw.polygon([(width - 340, header_bottom), (width, header_bottom),
                      (width, hero_bottom - 140)], fill='#a94b17')
        text_block(draw, upper_tr(CATEGORIES.get(category, 'Yerel gündem')),
                   (margin, header_bottom + 100, right, hero_bottom - 60), (58, 48, 40), True)
    draw.rectangle((0, hero_bottom, width, hero_bottom + 10), fill=TURQUOISE)

    category_top = hero_bottom + 35
    label = 'TASARIM ÖRNEĞİ' if preview else upper_tr(CATEGORIES.get(category, 'Yerel gündem'))
    label_width = min(right - margin, int(draw.textlength(label, font=font(26, True))) + 38)
    draw.rounded_rectangle((margin, category_top, margin + label_width, category_top + 48), 9, fill=ORANGE)
    draw.text((margin + 19, category_top + 9), label, font=font(26, True), fill=NAVY, anchor='lt')
    prefix = CATEGORIES.get(category, '') + ': '
    display_title = title[len(prefix):] if prefix.strip() != ':' and title.startswith(prefix) else title
    title_top = category_top + 70
    title_end = text_block(draw, upper_tr(display_title), (margin, title_top, right, title_top + 276),
                           (68, 60, 52, 46, 40), True)

    # Attribution has its own reserved line; a long excerpt cannot push it off.
    paragraphs = body.split('\n')
    source_lines = [line for line in paragraphs if line.startswith('Kaynak: ')]
    content = '\n'.join(line for line in paragraphs if not line.startswith('Kaynak: ')).strip()
    source_top = bottom - 100
    text_block(draw, content, (margin, title_end + 20, right, source_top - 24), (30, 28, 26), color='#d8e7eb')
    draw.line((margin, source_top - 8, right, source_top - 8), fill=TURQUOISE, width=2)
    attribution = ' · '.join(source_lines) if source_lines else 'Kaynaklı bilgi · Yerel yaşam'
    text_block(draw, attribution, (margin, source_top + 5, right - 100, source_top + 43), (23, 21))
    draw.text((margin, source_top + 53), '@seferihisarofficial', font=font(23, True), fill=IVORY, anchor='lt')
    if index:
        draw.text((right, source_top + 53), index, font=font(23), fill=ORANGE, anchor='rt')
    # Decorative footer only; story content leaves top/bottom UI safe zones.
    draw.polygon([(0, height - 50), (width, height - 160), (width, height - 120),
                  (0, height - 10)], fill=TURQUOISE)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'JPEG', quality=92)


def render_post(post: dict, public_dir: Path, illustrations: dict[int, Path] | None = None) -> dict:
    """Explicit slide-to-illustration mapping, with no category-wide stock scene."""
    assets = {'feed': [], 'story': []}
    slides = post['slides']
    if post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation'):
        slides = slides + [{'title': 'Kaynağı takip edin',
                           'body': 'Güncel tarih ve bilet bilgisi için kaynak duyurusunu kontrol edin.\n\n' + '\n'.join(post['source_urls'])}]
    for fmt in assets:
        for i, slide in enumerate(slides):
            relative = f"media/{post['id']}/{fmt}-{i+1}.jpg"
            card(slide['title'], slide['body'], post['category'], public_dir / relative,
                 fmt == 'story', f'{i+1}/{len(slides)}', illustration=(illustrations or {}).get(i))
            assets[fmt].append(relative)
    return assets
