"""12 Nov: a publisher's headline band under its photograph is cropped away.

Bomba32's heroes carry two lines of headline on a dark band across the bottom.
The article's own picture is always used now, so that band reached our cards.
"""
import io
import random

import pytest
from PIL import Image, ImageDraw

from seferihisar import headline_band
from seferihisar.headline_band import band_edge, band_top, crop, without_band
from seferihisar.image_safety import validate_jpeg

WIDTH, HEIGHT, BAND = 768, 432, 316


def picture(band=BAND, backing='#101010', height=HEIGHT):
    """A busy photograph above a flat band, like a publisher's headline graphic."""
    dots = random.Random(7)
    image = Image.new('RGB', (WIDTH, height), backing)
    draw = ImageDraw.Draw(image)
    for _ in range(2500):
        x, y = dots.randrange(WIDTH), dots.randrange(band - 14)
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


def test_a_band_is_large_lettering_that_closes_the_bottom_of_the_frame():
    assert band_top(headline(), WIDTH, HEIGHT) == BAND + 16
    # A collage with lettering above the photograph, a caption-sized credit,
    # a single word, a narrow corner label and unsure reads are not a band.
    assert band_top(headline() + [word('ISPARTA', 200, 12)], WIDTH, HEIGHT) is None
    assert band_top([word(w['text'], w['box']['left'], w['box']['top'], height=12) for w in headline()], WIDTH, HEIGHT) is None
    assert band_top(headline()[:1], WIDTH, HEIGHT) is None
    assert band_top([word('HABER', 600, 360, 70), word('AJANSI', 680, 360, 70)], WIDTH, HEIGHT) is None
    assert band_top([{**w, 'confidence': 30} for w in headline()], WIDTH, HEIGHT) is None
    assert band_top(headline(top=200), WIDTH, HEIGHT) is None


def test_the_crop_ends_where_the_bands_backing_colour_ends():
    with Image.open(io.BytesIO(picture())) as image:
        assert abs(band_edge(image.convert('RGB'), BAND + 16) - BAND) <= 3
    cropped = crop(picture(), [headline(), []])
    validate_jpeg(cropped)
    with Image.open(io.BytesIO(cropped)) as image:
        assert image.width == WIDTH and abs(image.height - BAND) <= 3


@pytest.mark.parametrize('case', ['no_lettering', 'too_little_left', 'too_wide_a_strip'])
def test_a_picture_that_cannot_lose_a_band_stays_as_it_is(case):
    if case == 'no_lettering':
        data, scans = picture(), [[], []]
    elif case == 'too_little_left':
        data, scans = picture(band=240, height=300), [headline(top=250), []]
    else:
        data, scans = picture(band=290, height=520), [headline(top=300), []]
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
