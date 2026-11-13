"""A publisher's headline bands at the edge of its own picture are cropped away.

12 Nov: Bomba32's heroes carry two lines of headline on a band across the bottom.
13 Nov: live cards still showed Haber32's headline across the top and Ajans32's
bottom band with the site's address, so both edges are checked.
"""
import io
import random

import pytest
from PIL import Image, ImageDraw

from seferihisar import headline_band
from seferihisar.headline_band import band_edge, bottom_band, crop, lettering, top_band, top_edge, without_band
from seferihisar.image_safety import validate_jpeg

WIDTH, HEIGHT, BAND, TOP = 768, 432, 316, 80


def picture(band=BAND, backing='#101010', height=HEIGHT, top=0):
    """A busy photograph between flat bands, like a publisher's headline graphic."""
    dots = random.Random(7)
    image = Image.new('RGB', (WIDTH, height), backing)
    draw = ImageDraw.Draw(image)
    for _ in range(2500):
        x, y = dots.randrange(WIDTH), dots.randrange(top, band - 14)
        draw.rectangle((x, y, x + 24, y + 13), fill=tuple(dots.randrange(256) for _ in range(3)))
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=90)
    return out.getvalue()


def word(text, left, top, width=150, height=34, confidence=92):
    return {'text': text, 'letters': text, 'token': text.lower(), 'confidence': confidence,
            'box': {'left': left, 'top': top, 'width': width, 'height': height}}


def headline(top=BAND + 16):
    return [word('SÜRÜCÜLER', 60, top), word('ŞAŞKINLIKLA', 230, top), word('İZLEDİ', 420, top),
            word('ELMA', 80, top + 48), word('YÜKÜ', 250, top + 48), word('SAÇILDI', 560, top + 48)]


def masthead(top=4):
    return [word('ISPARTA’NIN', 60, top), word('1985', 230, top), word('YILINDAKİ', 420, top),
            word('GÖRENLERİ', 80, top + 38), word('GEÇMİŞE', 300, top + 38)]


def test_a_bottom_band_is_large_lettering_that_closes_the_frame():
    big = lettering([headline()], HEIGHT)
    assert bottom_band(big, WIDTH, HEIGHT) == BAND + 16
    # A caption-sized credit, a single word, a narrow corner label, unsure reads
    # and lettering in the middle of the photograph are not a band.
    small = [word(w['text'], w['box']['left'], w['box']['top'], height=12) for w in headline()]
    assert bottom_band(lettering([small], HEIGHT), WIDTH, HEIGHT) is None
    assert bottom_band(lettering([headline()[:1]], HEIGHT), WIDTH, HEIGHT) is None
    assert bottom_band(lettering([[word('HABER', 600, 360, 70), word('AJANSI', 680, 360, 70)]], HEIGHT), WIDTH, HEIGHT) is None
    assert bottom_band(lettering([[{**w, 'confidence': 30} for w in headline()]], HEIGHT), WIDTH, HEIGHT) is None
    assert bottom_band(lettering([headline(top=230)], HEIGHT), WIDTH, HEIGHT) is None


def test_a_top_band_takes_the_site_name_printed_under_it():
    big = lettering([masthead()], HEIGHT)
    assert top_band(big, [], WIDTH, HEIGHT) == 4 + 38 + 34
    logo = word('HABER32', 330, 80, width=120, height=16, confidence=70)
    assert top_band(big, [logo], WIDTH, HEIGHT) == 96
    # A word far below the band is part of the photograph.
    assert top_band(big, [word('Arşivi', 600, 200, height=16)], WIDTH, HEIGHT) == 76
    assert top_band(lettering([masthead(top=120)], HEIGHT), [], WIDTH, HEIGHT) is None


def test_the_crop_ends_where_the_bands_backing_colour_ends():
    with Image.open(io.BytesIO(picture())) as image:
        assert abs(band_edge(image.convert('RGB'), BAND + 16) - BAND) <= 3
    with Image.open(io.BytesIO(picture(top=TOP))) as image:
        assert abs(top_edge(image.convert('RGB'), 60) - TOP) <= 3
    cropped = crop(picture(), [headline(), []])
    validate_jpeg(cropped)
    with Image.open(io.BytesIO(cropped)) as image:
        assert image.width == WIDTH and abs(image.height - BAND) <= 3


def test_bands_at_both_edges_leave_the_photograph_between_them():
    # Bomba32, 12 Nov: "İŞTE HASTANEDEN İLK GÖRÜNTÜLER" above, two lines below.
    data = picture(band=372, top=TOP)
    with Image.open(io.BytesIO(crop(data, [masthead() + headline(top=385)[:3], []]))) as image:
        assert image.width == WIDTH and abs(image.height - (372 - TOP)) <= 6


@pytest.mark.parametrize('case', ['no_lettering', 'too_little_left', 'too_wide_a_strip'])
def test_a_picture_that_cannot_lose_a_band_stays_as_it_is(case):
    if case == 'no_lettering':
        data, scans = picture(), [[], []]
    elif case == 'too_little_left':
        data, scans = picture(band=200, height=300, top=120), [masthead(top=40) + headline(top=210), []]
    else:
        data, scans = picture(band=200, height=260), [headline(top=205), []]
    assert crop(data, scans) is data


def test_a_missing_text_reader_never_holds_the_picture_back(monkeypatch):
    data = picture()
    monkeypatch.setattr('shutil.which', lambda name: None)
    assert without_band(data) is data
    monkeypatch.setattr('shutil.which', lambda name: 'tesseract')
    monkeypatch.setattr('seferihisar.image_safety.ocr_available', lambda: True)
    from seferihisar.image_safety import IllustrationCheckUnavailable
    monkeypatch.setattr('seferihisar.image_safety._scan_words', lambda *args: (_ for _ in ()).throw(IllustrationCheckUnavailable()))
    assert without_band(data) is data
    monkeypatch.setattr('seferihisar.image_safety._scan_words', lambda binary, data, mode: headline() if mode == 11 else [])
    with Image.open(io.BytesIO(without_band(data))) as image:
        assert abs(image.height - BAND) <= 3


def test_outlined_letters_only_the_contrast_view_reads_are_still_a_band(monkeypatch):
    # Ajans32 prints blue letters with a white outline over the photograph.
    calls = []

    def scan(binary, data, mode):
        calls.append(data[:4])
        return headline() if data[:4] == b'\x89PNG' else []
    monkeypatch.setattr('shutil.which', lambda name: 'tesseract')
    monkeypatch.setattr('seferihisar.image_safety.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.image_safety._scan_words', scan)
    with Image.open(io.BytesIO(without_band(picture()))) as image:
        assert abs(image.height - BAND) <= 3
    assert len(calls) == 4


def test_an_articles_banner_graphic_is_bound_without_its_band(tmp_path, monkeypatch):
    from contextlib import closing
    from test_real_photo_first import AT, LOCAL, add, manager, page
    from seferihisar.store import Store
    monkeypatch.setattr(headline_band, 'without_band', lambda data: crop(data, [headline(), []]))
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        row = add(store, LOCAL, 'elma', 'Tırın kasasından yola elma döküldü')
        photos, fetcher = manager(store, tmp_path, monkeypatch,
                                  {row['url']: page(row, '<img src="https://paper.example/u/a.jpg" alt="Elma">')}, (LOCAL,))
        fetcher.image.return_value = (picture(), 'https://paper.example/u/a.jpg')
        assert photos.image(row)
        with Image.open(io.BytesIO(store.rows('SELECT image FROM source_photos')[0]['image'])) as image:
            assert image.width == WIDTH and abs(image.height - BAND) <= 3


def test_an_outlined_headline_on_a_black_address_strip_is_found_from_its_pixels():
    # Ajans32, 13 Nov: OCR read none of these letters; the template is in the pixels.
    from pathlib import Path
    from seferihisar.headline_band import footer_band
    folder = Path('tests/fixtures/headline-bands')
    with Image.open(folder / 'ajans32-bottom-band.jpg') as image:
        assert 250 <= footer_band(image.convert('RGB')) <= 275
    with Image.open(io.BytesIO(crop((folder / 'ajans32-bottom-band.jpg').read_bytes(), [[], []]))) as image:
        assert image.width == 768 and 250 <= image.height <= 275
    # A photograph without the strip, and one with headline boxes above it, are left alone here.
    with Image.open(folder / 'haber32-top-band.jpg') as image:
        assert footer_band(image.convert('RGB')) is None
    with Image.open(io.BytesIO(picture())) as image:
        assert footer_band(image.convert('RGB')) is None