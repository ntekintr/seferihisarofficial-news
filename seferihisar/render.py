from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .domain import CATEGORIES

COLORS = {"concert": "#8b5cf6", "festival": "#ea580c", "municipality": "#0284c7",
          "event": "#0d9488", "weather": "#d97706", "outage": "#dc2626", "news": "#2563eb"}


def font(size: int):
    candidates = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf")
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def wrap(draw: ImageDraw.ImageDraw, text: str, typeface, width: int) -> list[str]:
    lines = []
    for paragraph in text.splitlines():
        line = ""
        for word in paragraph.split():
            # Long URLs and names must not escape the canvas.
            while draw.textlength(word, font=typeface) > width:
                split = len(word) - 1
                while split > 1 and draw.textlength(word[:split], font=typeface) > width:
                    split -= 1
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:split])
                word = word[split:]
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=typeface) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def card(title: str, body: str, category: str, target: Path, story: bool = False, index: str = ""):
    width, height = 1080, 1920 if story else 1350
    image = Image.new("RGB", (width, height), "#071b29")
    draw = ImageDraw.Draw(image)
    accent = COLORS.get(category, "#0d9488")
    margin = 76
    top = 220 if story else 88  # Story safe zones protect text from Instagram chrome.
    draw.rounded_rectangle((margin, top, width - margin, top + 14), 7, fill=accent)
    draw.text((margin, top + 45), "SEFERİHİSAR", font=font(33), fill="#e2f0f4")
    draw.text((margin, top + 91), "OFFICIAL", font=font(24), fill="#79b2bf")
    draw.text((margin, top + 163), CATEGORIES.get(category, "Etkinlikler").upper(), font=font(24), fill=accent)
    y = top + 231
    for size in (58, 52, 46, 40, 34):
        title_font = font(size)
        title_lines = wrap(draw, title, title_font, width - 2 * margin)
        if len(title_lines) <= 6:
            break
    for line in title_lines[:6]:
        draw.text((margin, y), line, font=title_font, fill="#ffffff")
        y += size + 16
    y += 42
    body_font = font(30 if not story else 34)
    body_lines = wrap(draw, body, body_font, width - 2 * margin)
    bottom = height - (260 if story else 180)
    max_lines = max(0, (bottom - y) // 49)
    for n, line in enumerate(body_lines[:max_lines]):
        if n == max_lines - 1 and len(body_lines) > max_lines:
            line = line[:max(1, len(line) - 3)] + "…"
        draw.text((margin, y), line, font=body_font, fill="#bed1db")
        y += 49
    draw.line((margin, bottom + 38, width - margin, bottom + 38), fill="#254456", width=2)
    draw.text((margin, bottom + 65), "Kaynaklı bilgi · Yerel yaşam", font=font(23), fill="#79b2bf")
    draw.text((width - margin - 120, bottom + 65), index, font=font(23), fill=accent)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "JPEG", quality=92)


def render_post(post: dict, public_dir: Path) -> dict:
    assets = {"feed": [], "story": []}
    slides = post["slides"]
    # Event cards get a second slide with source and ticket details via caption.
    if post["kind"] in ("announcement", "reminder_3d", "reminder_day", "update", "cancellation"):
        slides = slides + [{"title": "Kaynağı takip edin", "body": "Güncel tarih ve bilet bilgisi için kaynak duyurusunu kontrol edin.\n\n" + "\n".join(post["source_urls"])}]
    for fmt in assets:
        for i, slide in enumerate(slides):
            relative = f"media/{post['id']}/{fmt}-{i+1}.jpg"
            card(slide["title"], slide["body"], post["category"], public_dir / relative, fmt == "story", f"{i+1}/{len(slides)}")
            assets[fmt].append(relative)
    return assets
