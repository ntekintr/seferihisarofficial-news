import io
import subprocess
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.image_safety import (IllustrationCheckUnavailable, IllustrationTextRejected,
                                     ocr_available, validate_text_free_illustration)


HEADER = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
PAGE = '1\t1\t0\t0\t0\t0\t0\t0\t768\t768\t-1\t\n'


def jpeg():
    target = io.BytesIO()
    Image.new('RGB', (768, 768), '#f58220').save(target, format='JPEG')
    return target.getvalue()


def output(word='', confidence=90):
    row = f'5\t1\t1\t1\t1\t1\t100\t100\t180\t32\t{confidence}\t{word}\n' if word else ''
    return (HEADER + PAGE + row).encode()


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/tesseract')
    call = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output(), stderr=b''))
    monkeypatch.setattr('subprocess.run', call)
    return call


def test_plain_scene_has_no_detected_text_and_input_stays_off_command_line(engine):
    data = jpeg()
    validate_text_free_illustration(data)
    args, kwargs = engine.call_args
    assert args[0] == ['/usr/bin/tesseract', 'stdin', 'stdout', '-l', 'eng+tur', '--psm', '11', 'tsv']
    assert kwargs['input'] == data and kwargs['timeout'] == 15 and kwargs['check'] is True
    assert kwargs['stdout'] == subprocess.PIPE and kwargs['stderr'] == subprocess.PIPE


@pytest.mark.parametrize('word,confidence', [('2021', 2), ('FESTİVALİ', 46), ('festival', 90), ('15.10.2026', 1), ('S', 99)])
def test_text_and_year_are_rejected_even_when_no_factual_matching_is_attempted(engine, word, confidence):
    engine.return_value.stdout = output(word, confidence)
    with pytest.raises(IllustrationTextRejected, match='lettering rejected'):
        validate_text_free_illustration(jpeg())


@pytest.mark.parametrize('bad', [b'', b'not TSV', HEADER.encode() + b'malformed\n', output('abc', 'NaN'), b'X' * (256 * 1024 + 1)],
                         ids=['empty', 'wrong-format', 'incomplete-row', 'invalid-confidence', 'oversized'])
def test_malformed_ocr_output_fails_closed(engine, bad):
    engine.return_value.stdout = bad
    with pytest.raises(IllustrationCheckUnavailable):
        validate_text_free_illustration(jpeg())


def test_engine_timeout_and_diagnostics_do_not_escape(engine):
    engine.side_effect = subprocess.TimeoutExpired(['tesseract'], 15, stderr=b'private provider-like text')
    with pytest.raises(IllustrationCheckUnavailable) as caught:
        validate_text_free_illustration(jpeg())
    assert 'private' not in str(caught.value)


def test_missing_engine_returns_fallback_condition(monkeypatch):
    monkeypatch.setattr('shutil.which', lambda name: None)
    assert ocr_available() is False
    with pytest.raises(IllustrationCheckUnavailable):
        validate_text_free_illustration(jpeg())


def test_language_preflight_requires_both_turkish_and_english(engine):
    engine.return_value.stdout = b'List of available languages:\neng\nosd\n'
    assert ocr_available() is False
    engine.return_value.stdout = b'List of available languages:\neng\ntur\nosd\n'
    assert ocr_available() is True


def test_corrupt_jpeg_is_rejected_before_engine_execution(engine):
    with pytest.raises(ValueError, match='Invalid illustration bytes'):
        validate_text_free_illustration(b'not an image')
    engine.assert_not_called()
