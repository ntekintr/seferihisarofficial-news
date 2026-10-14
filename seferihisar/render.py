from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .domain import CATEGORIES
from .editor import event_type_label

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


def readable_date_line(value: str) -> str:
    months = ('Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
              'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık')
    def date(match):
        try:
            day = datetime.strptime(match[0], '%d.%m.%Y')
        except ValueError:
            return match[0]
        return f'{day.day} {months[day.month - 1]} {day.year}'
    return re.sub(r'\b\d{2}\.\d{2}\.\d{4}\b', date, value)


def footer_band(image: Image.Image):
    """Rasterize the diagonal brand strip with smooth, straight edges."""
    width, height = image.size
    band_height, scale = 180, 4
    top = height - band_height
    mask = Image.new('L', (width * scale, band_height * scale), 0)
    points = [(0, height - 50), (width, height - 160),
              (width, height - 120), (0, height - 10)]
    ImageDraw.Draw(mask).polygon([(x * scale, (y - top) * scale) for x, y in points], fill=255)
    mask = mask.resize((width, band_height), Image.Resampling.LANCZOS)
    image.paste(TURQUOISE, (0, top, width, height), mask)


def graphic_body(body: str, title: str = '') -> str:
    """Discard legacy source footers, including their standalone URL lines."""
    lines, attribution = [], False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('Kaynak:'):
            attribution = True
            continue
        if attribution and (not stripped or re.fullmatch(r'https?://\S+', stripped)):
            continue
        attribution = False
        lines.append(line)
    content = '\n'.join(lines).strip()
    if title:
        credit = re.escape(title) + r'\s+yazısı ilk önce\s+[^\n]+?\s+üzerinde ortaya çıktı\.?\s*$'
        content = re.sub(credit, '', content, flags=re.I).strip()
    return content


def card(title: str, body: str, category: str, target: Path, story: bool = False,
         index: str = '', illustration: Path | None = None, preview: bool = False,
         event_details: bool = False):
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
    else:
        # A missing/rejected photo produces typography, never invented scenery.
        # Keep the same branded layout without a vector scene or category icon.
        draw.rectangle((0, header_bottom, width, hero_bottom), fill='#0b355a')
        text_block(draw, upper_tr(event_type_label(category) if event_details else CATEGORIES.get(category, 'Yerel gündem')),
                   (margin, header_bottom + 100, right, hero_bottom - 60), (58, 48, 40), True)
    draw.rectangle((0, hero_bottom, width, hero_bottom + 10), fill=TURQUOISE)

    category_top = hero_bottom + 35
    label = 'TASARIM ÖRNEĞİ' if preview else upper_tr(event_type_label(category) if event_details else CATEGORIES.get(category, 'Yerel gündem'))
    label_width = min(right - margin, int(draw.textlength(label, font=font(30, True))) + 38)
    draw.rounded_rectangle((margin, category_top, margin + label_width, category_top + 48), 9, fill=ORANGE)
    draw.text((margin + 19, category_top + 9), label, font=font(30, True), fill=NAVY, anchor='lt')
    prefix = CATEGORIES.get(category, '') + ': '
    display_title = title[len(prefix):] if prefix.strip() != ':' and title.startswith(prefix) else title
    if event_details:
        if display_title.startswith('Bölge takviminde: '):
            display_title = display_title[len('Bölge takviminde: '):]
        suffix = ' — ' + event_type_label(category)
        if display_title.endswith(suffix):
            display_title = display_title[:-len(suffix)]
    title_top = category_top + 70
    title_end = text_block(draw, upper_tr(display_title), (margin, title_top, right, title_top + 276),
                           (68, 60, 52, 46, 40), True)

    # Legacy queued slide bodies may contain attribution. It belongs only in
    # the caption; never paint it or a fallback source label on the graphic.
    content = graphic_body(body, display_title)
    brand_top = bottom - 70
    if event_details:
        date_line, _, rest = content.partition('\n')
        date_end = text_block(draw, readable_date_line(date_line), (margin, title_end + 28, right, min(brand_top - 24, title_end + 136)),
                              (42, 38, 34, 30), True, color=ORANGE)
        text_block(draw, rest.strip(), (margin, date_end + 28, right, brand_top - 24), (34, 32, 30, 28), color='#d8e7eb')
    else:
        text_block(draw, content, (margin, title_end + 20, right, brand_top - 24), (30, 28, 26), color='#d8e7eb')
    draw.line((margin, brand_top - 8, right, brand_top - 8), fill=TURQUOISE, width=2)
    draw.text((margin, brand_top + 23), '@seferihisarofficial', font=font(23, True), fill=IVORY, anchor='lt')
    if index:
        draw.text((right, brand_top + 23), index, font=font(23), fill=ORANGE, anchor='rt')
    # Decorative footer only; story content leaves top/bottom UI safe zones.
    footer_band(image)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'JPEG', quality=92, subsampling=0)


def render_post(post: dict, public_dir: Path, illustrations: dict[int, Path] | None = None) -> dict:
    """Explicit slide-to-illustration mapping, with no category-wide stock scene."""
    assets = {'feed': [], 'story': []}
    slides = post['slides']
    if post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation'):
        # Keep stable frame indexes for existing story jobs; source links and
        # names stay in the caption instead of this supplementary frame.
        slides = slides + [{'title': 'Ayrıntılar açıklamada',
                           'body': 'Güncel bilgiler ve bağlantılar için gönderi açıklamasına bakın.'}]
    for fmt in assets:
        for i, slide in enumerate(slides):
            relative = f"media/{post['id']}/{fmt}-{i+1}.jpg"
            is_event = post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation') or (post['kind'] in ('weekly', 'monthly') and i > 0)
            card(slide['title'], slide['body'], slide.get('category', post['category']), public_dir / relative,
                 fmt == 'story', f'{i+1}/{len(slides)}', illustration=(illustrations or {}).get(i),
                 event_details=is_event and i < len(post['slides']))
            assets[fmt].append(relative)
    return assets

