"""Confirmed bad provider bytes stay rejected even when OCR misses lettering."""
import base64
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.image_safety import (IllustrationTextRejected, validate_jpeg,
                                    validate_text_free_illustration)


def fixture(name):
    path = Path(__file__).parent / 'fixtures' / name
    return base64.b64decode(''.join(path.read_text(encoding='ascii').split()), validate=True)


def empty_ocr():
    header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
    page = '1\t1\t0\t0\t0\t0\t0\t0\t768\t768\t-1\t\n'
    return subprocess.CompletedProcess([], 0, stdout=(header + page).encode(), stderr=b'')


@pytest.mark.parametrize('binary', ['/usr/bin/tesseract', None], ids=['ocr-would-miss', 'ocr-unavailable'])
def test_reviewed_stall_lettering_is_rejected_before_any_ocr_call(monkeypatch, binary):
    data = fixture('festival-photo-reviewed-lettering.jpg.b64')
    assert hashlib.sha256(data).hexdigest() == '5cc335d268a834ecdd538a7e8e68f9be979640e164132e33906acd52e407dada'
    validate_jpeg(data)
    lookup = Mock(return_value=binary)
    engine = Mock(return_value=empty_ocr())
    monkeypatch.setattr('shutil.which', lookup)
    monkeypatch.setattr('subprocess.run', engine)
    with pytest.raises(IllustrationTextRejected) as caught:
        validate_text_free_illustration(data)
    assert caught.value.args == ('Illustration lettering rejected',)
    assert caught.value.findings == []
    lookup.assert_not_called()
    engine.assert_not_called()


def test_reviewed_rejection_does_not_block_other_real_provider_photo_bytes(monkeypatch):
    data = fixture('family-photo-no-lettering.jpg.b64')
    engine = Mock(return_value=empty_ocr())
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/tesseract')
    monkeypatch.setattr('subprocess.run', engine)
    validate_text_free_illustration(data)
    assert engine.call_count == 4
