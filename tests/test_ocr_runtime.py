import io
import shutil

import pytest
from PIL import Image, ImageDraw

from seferihisar.image_safety import (IllustrationTextRejected, ocr_available,
                                    validate_text_free_illustration)
from seferihisar.illustrations import clean_image
from seferihisar.render import font


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='CPU OCR is installed in cloud validation')
def test_real_cpu_ocr_rejects_a_year_and_accepts_an_empty_scene():
    assert ocr_available(), 'English and Turkish OCR language data are required'
    plain = Image.new('RGB', (600, 180), 'white')
    empty = io.BytesIO()
    plain.save(empty, format='PNG')
    validate_text_free_illustration(clean_image(empty.getvalue()))
    ImageDraw.Draw(plain).text((25, 45), 'FESTIVAL 2021', font=font(58, True), fill='black')
    lettering = io.BytesIO()
    plain.save(lettering, format='PNG')
    with pytest.raises(IllustrationTextRejected):
        validate_text_free_illustration(clean_image(lettering.getvalue()))
