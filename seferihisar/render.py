from __future__ import annotations

from functools import lru_cache, partial
from pathlib import Path
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .domain import CATEGORIES
from .editor import event_activity, event_type_label, news_type_label
from .text_quality import TextRenderError, plain_display, ensure_glyphs
from .card_layout import CAPTION_NOTE, fixed_scale, inline_note, editorial
from .brand import VERSION as BRAND_VERSION, logo_path, version_for
from .publication_policy import story_only

NAVY, IVORY, ORANGE, TURQUOISE = '#06244a', '#f4efe4', '#f58220', '#20b8c9'
ASSETS = Path(__file__).with_name('assets')


@lru_cache(maxsize=32)
def font(size: int, bold: bool = False):
    suffix = '-Bold' if bold else ''
    candidates = (
        f'/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf',
        # A card made on any other machine keeps the production typeface.
        str(ASSETS / 'fonts' / f'DejaVuSans{suffix}.ttf'),
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


def text_block(draw, text, box, sizes, bold=False, color=IVORY, *, strict=False, complete=False):
    """Fit a bounded text panel; visibly mark shortened excerpts."""
    left, top, right, bottom = box
    if strict:
        text = '\n'.join(plain_display(line) for line in text.splitlines())
    for size in sizes:
        typeface = font(size, bold)
        lines = wrap(draw, text, typeface, right - left)
        line_height = size + 12
        if len(lines) * line_height <= bottom - top:
            break
    capacity = max(0, (bottom - top) // line_height)
    if strict:
        ensure_glyphs(text, typeface)
        if complete and len(lines) > capacity:
            raise TextRenderError('Card heading or date would be truncated')
    visible = lines[:capacity]
    if len(lines) > capacity and visible:
        visible[-1] = ellipsis(draw, visible[-1], typeface, right - left)
    for i, line in enumerate(visible):
        draw.text((left, top + i * line_height), line, font=typeface, fill=color, anchor='lt')
    return top + len(visible) * line_height


def readable_date_line(value: str) -> str:
    months = ('Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
              'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık')
    if match := re.match(r'^(\d{2}\.\d{2}\.\d{4}) – (\d{2}\.\d{2}\.\d{4})(.*)$', value):
        try:
            first, last = (datetime.strptime(match[i], '%d.%m.%Y') for i in (1, 2))
            if first < last and (first.year, first.month) == (last.year, last.month):
                return f'{first.day}–{last.day} {months[first.month - 1]} {first.year}' + match[3]
        except ValueError:
            pass
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


def graphic_title(title: str, category: str, event_details: bool = False):
    """Keep the event name prominent; put its reminder/update in the badge."""
    display = title
    for prefix in (CATEGORIES.get(category, '') + ': ', news_type_label(category, title) + ': '):
        if prefix.strip() != ':' and display.startswith(prefix):
            display = display[len(prefix):]
            break
    notice = ''
    if event_details:
        states = {'Etkinlik bilgisi güncellendi: ':'GÜNCELLENDİ', 'İptal duyurusu: ':'İPTAL',
                  'Bugün yakınınızda: ':'BUGÜN', 'Bölge takviminde: ':''}
        for prefix, value in states.items():
            if display.startswith(prefix):
                display, notice = display[len(prefix):], value
                break
        if match := re.match(r'([1-3]) gün kaldı: ', display):
            notice, display = match[1] + ' GÜN KALDI', display[match.end():]
        suffix = ' — ' + event_type_label(category, display)
        if display.endswith(suffix):
            display = display[:-len(suffix)]
    return display, notice


def card(title: str, body: str, category: str, target: Path, story: bool = False,
         index: str = '', illustration: Path | None = None, preview: bool = False,
         event_details: bool = False, photo_centering: tuple[float, float] = (0.5, 0.5), compact: bool = False,
         legacy_outage: bool = False, story_details: bool = False, text_review: bool = False, source_photo: bool = False,
         caption_note: bool = False, brand_version: str = BRAND_VERSION, editorial_layout: bool = False,
         one_scale: bool = True):
    """Fixed branding and a per-item illustration, never a shared news scene."""
    if editorial_layout:
        from .editorial_render import editorial_card
        return editorial_card(title, body, category, target, story=story, index=index,
                              illustration=illustration, preview=preview, event_details=event_details,
                              photo_centering=photo_centering, story_details=story_details,
                              source_photo=source_photo, caption_note=caption_note, brand_version=brand_version,
                              fixed_scale=one_scale)
    width, height = 1080, 1920 if story else 1350
    block = partial(text_block, strict=text_review)
    top, bottom = (260, 1600) if story else (0, 1260)
    margin, right = 64, width - 64
    image = Image.new('RGB', (width, height), NAVY)
    draw = ImageDraw.Draw(image)
    header_bottom = top + 144
    draw.text((margin, top + 35), 'SEFERİHİSAR', font=font(34, True), fill=IVORY, anchor='lt')
    draw.text((margin, top + 80), 'OFFICIAL', font=font(24), fill=TURQUOISE, anchor='lt')
    logo_size, logo_xy = 116, (right - 116, top + 12)
    with Image.open(logo_path(brand_version)) as original:
        logo = ImageOps.fit(original.convert('RGB'), (logo_size, logo_size), method=Image.Resampling.LANCZOS)
    mask = Image.new('L', (logo_size, logo_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, logo_size - 1, logo_size - 1), fill=255)
    image.paste(logo, logo_xy, mask)
    draw.rectangle((0, header_bottom - 8, width, header_bottom), fill=ORANGE)

    hero_bottom = top + (730 if story else 580)
    if story and story_details and illustration is not None:
        hero_bottom -= 80
    if illustration is not None:
        with Image.open(illustration) as source:
            hero = (ImageOps.pad(source.convert('RGB'), (width,hero_bottom-header_bottom),method=Image.Resampling.LANCZOS,color=NAVY)
                    if source_photo else ImageOps.fit(source.convert('RGB'), (width, hero_bottom - header_bottom),
                                method=Image.Resampling.LANCZOS, centering=photo_centering))
        image.paste(hero, (0, header_bottom))
    elif not compact:
        # A missing/rejected photo produces typography, never invented scenery.
        # Keep the same branded layout without a vector scene or category icon.
        draw.rectangle((0, header_bottom, width, hero_bottom), fill='#0b355a')
        text_block(draw, 'ETKİNLİK' if legacy_outage else upper_tr(event_type_label(category, title) if event_details else news_type_label(category, title)),
                   (margin, header_bottom + 100, right, hero_bottom - 60), (58, 48, 40), True)
    else:
        # A deliberate information card: no empty picture placeholder, no
        # duplicate category heading. Keep logo and the same brand colours.
        hero_bottom = header_bottom + 20
    draw.rectangle((0, hero_bottom, width, hero_bottom + 10), fill=TURQUOISE)

    category_top = hero_bottom + 35
    display_title, notice = graphic_title(title, category, event_details)
    label = 'TASARIM ÖRNEĞİ' if preview else 'ETKİNLİK' if legacy_outage else upper_tr(event_type_label(category, display_title) if event_details else news_type_label(category, display_title))
    if notice and not preview:
        label += ' • ' + notice
    label_width = min(right - margin, int(draw.textlength(label, font=font(30, True))) + 38)
    draw.rounded_rectangle((margin, category_top, margin + label_width, category_top + 48), 9, fill=ORANGE)
    draw.text((margin + 19, category_top + 9), label, font=font(30, True), fill=NAVY, anchor='lt')
    title_top = category_top + 70
    if text_review and not re.search(r'\w',plain_display(display_title)):
        raise TextRenderError('Empty card heading after decoration cleanup')
    information_card = compact and illustration is None
    detail_photo = story and story_details and illustration is not None and event_details
    title_height = 180 if detail_photo else 400 if information_card else 276
    title_end = block(draw, upper_tr(display_title),
                           (margin, title_top, right, title_top + title_height),
                           (84, 76, 68, 60, 52, 46, 40) if information_card else (68, 60, 52, 46, 40), True, complete=True)

    # Legacy queued slide bodies may contain attribution. It belongs only in
    # the caption; never paint it or a fallback source label on the graphic.
    content = graphic_body(body, display_title)
    brand_top = bottom - 70
    content_bottom = brand_top - 24 - (64 if caption_note else 0)
    content_end = title_end
    if event_details:
        date_line, _, rest = content.partition('\n')
        date_end = block(draw, readable_date_line(date_line), (margin, title_end + 28, right, min(content_bottom, title_end + 136)),
                              (42, 38, 34, 30), True, color=ORANGE, complete=True)
        content_end = date_end
        compact = re.sub(r'\n\s*\n', '\n', rest.strip())
        if detail_photo:
            # Preserve the useful date/venue/price summary before optional
            # organizer/address overflow. Full details stay in the caption.
            lines = [line for line in compact.splitlines() if line.strip()]
            prices = [line for line in lines if line.startswith(('Ücret:', 'Ücretsiz', 'Ücretli'))]
            venues = [line for line in lines if line not in prices and not line.startswith('Düzenleyen:')]
            organizers = [line for line in lines if line.startswith('Düzenleyen:')]
            y = date_end + 20
            if venues:
                content_end = block(draw, '\n'.join(venues), (margin, y, right, min(y+80, content_bottom)), (34,32,30,28), color='#d8e7eb')
                y = content_end + 12
            if prices:
                content_end = block(draw, prices[0], (margin, y, right, min(y+48, content_bottom)), (34,32,30,28), color=ORANGE, complete=True)
                y = content_end + 12
            if organizers:
                content_end = block(draw, '\n'.join(organizers), (margin, y, right, content_bottom), (32,30,28), color='#d8e7eb')
        else:
            content_end = block(draw, compact, (margin, date_end + 28, right, content_bottom), (34, 32, 30, 28), color='#d8e7eb')
    else:
        content_end = block(draw, content, (margin, title_end + 20, right, content_bottom),
                   (46, 42, 38, 34, 30, 28, 26) if information_card else (30, 28, 26), color='#d8e7eb')
    if caption_note:
        block(draw, CAPTION_NOTE, (margin, content_end + 12, right, brand_top - 24),
              (28,26,24), color=TURQUOISE, complete=True)
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
    note = inline_note(post)
    if not note and post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation'):
        # Keep stable frame indexes for existing story jobs; source links and
        # names stay in the caption instead of this supplementary frame.
        slides = slides + [{'title': 'Ayrıntılar açıklamada',
                           'body': 'Güncel bilgiler ve bağlantılar için gönderi açıklamasına bakın.'}]
    for fmt in assets:
        for i, slide in enumerate(slides):
            review = post.get('visual_review', {})
            edition = review.get('edition', post['id'])
            relative = f"media/{edition}/{fmt}-{i+1}.jpg"
            is_event = post['kind'] in ('announcement', 'reminder_3d', 'reminder_day', 'update', 'cancellation') or (post['kind'] in ('weekly', 'monthly', 'weekend', 'free_week') and i > 0)
            category = slide.get('category', post['category'])
            # Reviewed yoga scenes place mats/blocks on the floor. Preserve that
            # subject in wide cards; keep claimed media's original framing.
            mutable = post.get('status', 'prepared') in ('prepared', 'blocked_source')
            yoga = is_event and i < len(post['slides']) and event_activity(category, slide['title']) == 'yoga'
            card(slide['title'], slide['body'], slide.get('category', post['category']), public_dir / relative,
                 fmt == 'story', f'{i+1}/{len(slides)}', illustration=(illustrations or {}).get(i),
                 event_details=is_event and i < len(post['slides']),
                 photo_centering=(0.5, 1.0) if (mutable or review) and yoga else (0.5, 0.5),
                 compact=mutable or bool(review),
                 legacy_outage=category == 'outage' and not mutable and not review,
                 story_details=(review.get('version') in ('content-visual-v2','content-visual-v3') or mutable and not review),
                 text_review=review.get('version') == 'content-visual-v3' or mutable and not review,
                 source_photo=bool(post.get('source_photo_keys',{}).get(str(i))),
                 # A story-only card has no feed post whose caption it could point to.
                 caption_note=note and i==0 and not (fmt == 'story' and mutable and story_only(post)),
                 brand_version=version_for(post), editorial_layout=editorial(post),
                 one_scale=fixed_scale(post))
            assets[fmt].append(relative)
    return assets

