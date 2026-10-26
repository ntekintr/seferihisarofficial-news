"""Actual deployed stock files must pass OCR and all three rendered crops."""
import json
import os
import pytest

from seferihisar.editorial_stock import DIRECTORY,reviewed_calendar
from seferihisar.image_safety import ocr_available,validate_text_free_illustration
from seferihisar.visual_match import validate_match

ROWS=json.loads((DIRECTORY/'manifest.json').read_text())['scenes']


@pytest.mark.skipif(os.getenv('RUN_VISUAL_NATIVE')!='true',reason='Pinned model and native OCR job')
@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['subject'])
def test_every_reviewed_stock_scene_passes_actual_ocr_and_crop_checks(row):
    assert ocr_available()
    data=(DIRECTORY/row['file']).read_bytes()
    validate_text_free_illustration(data)
    if row['subject']=='event_calendar':
        assert reviewed_calendar(data,row['subject'])
    else:
        assert validate_match(data,row['subject'])['subject']==row['subject']


@pytest.mark.skipif(os.getenv('RUN_VISUAL_NATIVE')!='true',reason='Native event-poster OCR')
@pytest.mark.parametrize('ident',['788d64a6aafa6d475aa1525c','c2e2f2e60c56fc4d4245c1f1'])
def test_actual_backlog_posters_match_the_original_session_text(ident):
    from pathlib import Path
    from seferihisar.event_image_text import validate
    folder=Path('tests/fixtures/backlog-posters')
    item=json.loads((folder/(ident+'.json')).read_text(encoding='utf8'))
    data=(folder/(ident+'.jpg')).read_bytes()
    if ident=='788d64a6aafa6d475aa1525c':
        # The stylized source title fails OCR. Keep that boundary closed;
        # the explicit musical genre receives a reviewed concert scene instead.
        with pytest.raises(ValueError,match='title'):
            validate(data,item,poster=True)
    else:
        assert validate(data,item,poster=True)
