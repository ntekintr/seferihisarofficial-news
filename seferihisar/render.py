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


def event_scene(image, draw, category: str, box) -> bool:
    """Text-free symbols for an event type, without inventing its real venue."""
    if category not in ('theatre', 'concert', 'cinema', 'festival'):
        return False
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    def p(x, y):
        return (left + int(w * x), top + int(h * y))
    def rect(a, b):
        return (*p(*a), *p(*b))
    draw.rectangle(box, fill='#092b46')
    beams = ImageDraw.Draw(image, 'RGBA')
    beams.polygon([p(.26, .04), p(.38, .89), p(.68, .89)], fill=(246, 217, 153, 68))
    beams.polygon([p(.76, .04), p(.31, .89), p(.60, .89)], fill=(32, 184, 201, 62))
    draw.polygon([p(.12, .86), p(.88, .86), p(1, 1), p(0, 1)], fill='#99623f')
    draw.line([p(.05, .95), p(.95, .95)], fill='#d0a574', width=3)
    if category in ('theatre', 'concert'):
        draw.rectangle(rect((0, 0), (1, .07)), fill='#b84425')
        for side in (0, 1):
            edge = left if side == 0 else right - int(w * .19)
            draw.rectangle((edge, top, edge + int(w * .19), bottom), fill='#c5552b')
            for i, shade in enumerate(('#ef873b', '#a83629', '#d7662b', '#9e3427')):
                x = edge + int(w * .19 * i / 4)
                draw.rectangle((x, top, x + int(w * .027), bottom), fill=shade)
        draw.pieslice(rect((.01, -.25), (.49, .22)), 0, 180, fill='#ef873b')
        draw.pieslice(rect((.51, -.25), (.99, .22)), 0, 180, fill='#d7662b')
    if category == 'theatre':
        for x, y, smile in ((.38, .29, True), (.55, .40, False)):
            outline = [p(x + .015, y + .025), p(x + .04, y), p(x + .10, y),
                       p(x + .13, y + .025), p(x + .13, y + .19),
                       p(x + .11, y + .31), p(x + .072, y + .40),
                       p(x + .03, y + .31), p(x + .005, y + .19)]
            draw.polygon(outline, fill='#f5e6c5')
            draw.line(outline + [outline[0]], fill='#ddb96c', width=3)
            for eye in (x + .025, x + .085):
                draw.ellipse(rect((eye, y + .12), (eye + .025, y + .15)), fill=NAVY)
            draw.line([p(x + .068, y + .15), p(x + .056, y + .205), p(x + .08, y + .205)],
                      fill='#bd975a', width=3)
            mouth = rect((x + .03, y + (.19 if smile else .25)),
                         (x + .105, y + (.31 if smile else .37)))
            draw.arc(mouth, 0 if smile else 180, 180 if smile else 360, fill=NAVY, width=7)
    elif category == 'concert':
        draw.line([p(.57, .33), p(.57, .84)], fill='#d8e7eb', width=8)
        draw.line([p(.48, .86), p(.65, .86)], fill='#d8e7eb', width=7)
        draw.rounded_rectangle(rect((.545, .20), (.595, .37)), int(h * .04), fill='#f4efe4')
        draw.ellipse(rect((.34, .49), (.47, .83)), fill=ORANGE)
        draw.ellipse(rect((.355, .36), (.455, .60)), fill=ORANGE)
        draw.rectangle(rect((.39, .19), (.42, .60)), fill='#d8aa70')
        draw.ellipse(rect((.385, .52), (.425, .61)), fill=NAVY)
        for x in (.397, .407):
            draw.line([p(x, .2), p(x, .76)], fill=IVORY, width=2)
    elif category == 'cinema':
        draw.rounded_rectangle(rect((.25, .16), (.78, .75)), int(h * .025), fill=IVORY, outline='#85d4d8', width=5)
        draw.polygon([p(.47, .33), p(.47, .57), p(.60, .45)], fill=ORANGE)
        draw.ellipse(rect((.08, .46), (.24, .80)), fill='#c1d7d8')
        for x, y in ((.145, .50), (.105, .60), (.18, .60), (.145, .70)):
            draw.ellipse(rect((x, y), (x + .036, y + .072)), fill=NAVY)
    else:
        for start_y in (.16, .37):
            draw.line([p(.1, start_y), p(.9, start_y + .12)], fill=IVORY, width=3)
            for i in range(8):
                x = .12 + i * .095
                y = start_y + (x - .1) * .15
                draw.polygon([p(x, y), p(x + .055, y + .01), p(x + .028, y + .14)],
                             fill=(ORANGE, TURQUOISE, '#e1b95d')[i % 3])
        draw.rounded_rectangle(rect((.35, .47), (.67, .88)), int(h * .025), fill='#12516a', outline=ORANGE, width=5)
        draw.line([p(.52, .58), p(.52, .85)], fill=IVORY, width=5)
        draw.ellipse(rect((.50, .51), (.54, .60)), fill=IVORY)
    for i in range(10):
        x = .06 + .092 * i
        draw.rounded_rectangle(rect((x, .93), (x + .07, 1.12)), int(h * .035), fill=NAVY)
    return True


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
        label = 'Temsili çizim'
        label_width = int(draw.textlength(label, font=font(23))) + 32
        draw.rounded_rectangle((right - label_width, hero_bottom - 46, right, hero_bottom - 10), 8, fill=NAVY)
        draw.text((right - label_width + 16, hero_bottom - 40), label, font=font(23), fill=IVORY, anchor='lt')
    elif event_details and category in ('theatre', 'concert', 'cinema', 'festival'):
        scene = Image.new('RGB', (width, hero_bottom - header_bottom), NAVY)
        event_scene(scene, ImageDraw.Draw(scene), category, (0, 0, width, scene.height))
        image.paste(scene, (0, header_bottom))
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

    # Attribution has its own reserved line; a long excerpt cannot push it off.
    paragraphs = body.split('\n')
    source_lines = [line for line in paragraphs if line.startswith('Kaynak: ')]
    content = '\n'.join(line for line in paragraphs if not line.startswith('Kaynak: ')).strip()
    source_top = bottom - 100
    if event_details:
        date_line, _, rest = content.partition('\n')
        date_end = text_block(draw, readable_date_line(date_line), (margin, title_end + 28, right, min(source_top - 24, title_end + 136)),
                              (42, 38, 34, 30), True, color=ORANGE)
        text_block(draw, rest.strip(), (margin, date_end + 28, right, source_top - 24), (34, 32, 30, 28), color='#d8e7eb')
    else:
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
            is_event = post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation') or (post['kind'] in ('weekly', 'monthly') and i > 0)
            card(slide['title'], slide['body'], slide.get('category', post['category']), public_dir / relative,
                 fmt == 'story', f'{i+1}/{len(slides)}', illustration=(illustrations or {}).get(i),
                 event_details=is_event and i < len(post['slides']))
            assets[fmt].append(relative)
    return assets
