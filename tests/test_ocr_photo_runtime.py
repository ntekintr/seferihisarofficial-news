"""Native cloud OCR regression for an inspected, text-free generated photo."""
import base64
import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from seferihisar.image_safety import (IllustrationTextRejected, _scan_words, ocr_available,
                                    validate_text_free_illustration)
from seferihisar.illustrations import clean_image
from seferihisar.render import font


pytestmark = pytest.mark.skipif(shutil.which('tesseract') is None,
                               reason='Native CPU OCR is installed in cloud validation')


def photo():
    path = Path(__file__).parent / 'fixtures' / 'family-photo-no-lettering.jpg.b64'
    return base64.b64decode(''.join(path.read_text(encoding='ascii').split()), validate=True)


def test_native_ocr_accepts_inspected_photo_instead_of_toy_and_kite_texture():
    assert ocr_available(), 'English and Turkish OCR language data are required'
    validate_text_free_illustration(photo())


def test_native_ocr_still_rejects_visible_year_on_the_same_photo():
    assert ocr_available(), 'English and Turkish OCR language data are required'
    with Image.open(io.BytesIO(photo())) as original:
        image = original.convert('RGB')
    draw = ImageDraw.Draw(image)
    draw.rectangle((520, 645, 755, 730), fill='white')
    draw.text((545, 655), '2021', font=font(56, True), fill='black')
    raw = io.BytesIO()
    image.save(raw, format='PNG')
    encoded = clean_image(raw.getvalue())
    try:
        validate_text_free_illustration(encoded)
    except IllustrationTextRejected:
        return
    # Only this synthetic, trusted test fixture may expose bounded OCR words in
    # a test failure. Production provider text still stays out of logs/state.
    binary = shutil.which('tesseract')
    fixture_path = Path('work/ocr-native-fixture.jpg')
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_bytes(encoded)
    scans = {
        str(mode): [{'text': word['text'][:160], 'confidence': word['confidence'], 'box': word['box']}
                    for word in _scan_words(binary, encoded, mode)[:32]]
        for mode in (11, 6, 3)
    }
    pytest.fail('Visible synthetic 2021 was accepted; fixture-only OCR: ' + json.dumps(scans, ensure_ascii=False))

