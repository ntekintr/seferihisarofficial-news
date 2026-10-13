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


def output(word='', confidence=90, box=(100, 100, 180, 32)):
    left, top, width, height = box
    row = f'5\t1\t1\t1\t1\t1\t{left}\t{top}\t{width}\t{height}\t{confidence}\t{word}\n' if word else ''
    return (HEADER + PAGE + row).encode()


def two_scans(engine, first, second):
    engine.side_effect = [subprocess.CompletedProcess([], 0, stdout=data, stderr=b'')
                          for data in (first, second)]


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/tesseract')
    call = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=output(), stderr=b''))
    monkeypatch.setattr('subprocess.run', call)
    return call


def test_plain_scene_has_no_detected_text_and_input_stays_off_command_line(engine):
    data = jpeg()
    validate_text_free_illustration(data)
    assert engine.call_count == 2
    for (args, kwargs), mode in zip(engine.call_args_list, ('11', '6')):
        assert args[0] == ['/usr/bin/tesseract', 'stdin', 'stdout', '-l', 'eng+tur', '--psm', mode, 'tsv']
        assert kwargs['input'] == data and kwargs['timeout'] == 15 and kwargs['check'] is True
        assert kwargs['stdout'] == subprocess.PIPE and kwargs['stderr'] == subprocess.PIPE


@pytest.mark.parametrize('word,confidence', [('2021', 2), ('FESTİVALİ', 46), ('festival', 90), ('15.10.2026', 1), ('S', 99)])
def test_text_and_year_are_rejected_even_when_no_factual_matching_is_attempted(engine, word, confidence):
    engine.return_value.stdout = output(word, confidence)
    with pytest.raises(IllustrationTextRejected, match='lettering rejected'):
        validate_text_free_illustration(jpeg())


@pytest.mark.parametrize('word,confidence', [('ab', 20), ('S', 80), ('2021', 0)])
def test_exact_existing_rejection_boundaries_include_private_evidence(engine, word, confidence):
    engine.return_value.stdout = output(word, confidence)
    with pytest.raises(IllustrationTextRejected) as caught:
        validate_text_free_illustration(jpeg())
    assert caught.value.findings == [
        {'text': word, 'confidence': float(confidence),
         'box': {'left': 100, 'top': 100, 'width': 180, 'height': 32}}
    ]
    assert caught.value.args == ('Illustration lettering rejected',)
    assert word not in repr(caught.value)


@pytest.mark.parametrize('word,confidence', [('ab', 19.99), ('S', 79.99), ('2021', -1), ('...', 99)])
def test_tokens_below_existing_rejection_boundaries_are_accepted(engine, word, confidence):
    engine.return_value.stdout = output(word, confidence)
    validate_text_free_illustration(jpeg())


def test_private_findings_are_bounded_without_skipping_later_validation(engine):
    rows = [output('x' * 200, 90, (index, 100, 180, 32)).decode().splitlines()[-1] + '\n'
            for index in range(40)]
    engine.return_value.stdout = (HEADER + PAGE + ''.join(rows)).encode()
    with pytest.raises(IllustrationTextRejected) as caught:
        validate_text_free_illustration(jpeg())
    assert len(caught.value.findings) == 32
    assert all(len(finding['text']) == 160 for finding in caught.value.findings)
    assert 'x' * 160 not in str(caught.value)
    # Reaching the evidence limit must not hide malformed later OCR output.
    engine.return_value.stdout += b'malformed\n'
    with pytest.raises(IllustrationCheckUnavailable):
        validate_text_free_illustration(jpeg())


@pytest.mark.parametrize('scan', [0, 1], ids=['sparse', 'block'])
@pytest.mark.parametrize('word,confidence', [('2021', 0), ('15.10.2026', 1), ('1999', 2)])
def test_possible_year_in_either_scan_is_rejected_without_confirmation(engine, scan, word, confidence):
    results = [output(), output()]
    results[scan] = output(word, confidence)
    two_scans(engine, *results)
    with pytest.raises(IllustrationTextRejected):
        validate_text_free_illustration(jpeg())


@pytest.mark.parametrize('scan', [0, 1], ids=['sparse', 'block'])
def test_strong_whole_word_in_either_scan_is_rejected_without_confirmation(engine, scan):
    results = [output(), output()]
    results[scan] = output('FESTIVAL', 80)
    two_scans(engine, *results)
    with pytest.raises(IllustrationTextRejected):
        validate_text_free_illustration(jpeg())


def test_high_confidence_short_shapes_in_different_regions_are_not_words(engine):
    two_scans(engine, output('v', 84.65, (278, 0, 25, 99)), output('A', 93, (120, 320, 35, 60)))
    validate_text_free_illustration(jpeg())


@pytest.mark.parametrize('word,confidence', [('ab', 20), ('S', 80), ('abc', 99), ('word', 79.99)])
def test_candidate_seen_in_only_one_scan_needs_confirmation(engine, word, confidence):
    two_scans(engine, output(word, confidence), output())
    validate_text_free_illustration(jpeg())


def test_different_words_in_the_same_region_do_not_confirm_each_other(engine):
    two_scans(engine, output('ab', 55), output('abc', 60))
    validate_text_free_illustration(jpeg())


def test_same_word_in_distant_regions_does_not_confirm(engine):
    two_scans(engine, output('ab', 55, (10, 10, 20, 20)), output('ab', 60, (100, 100, 20, 20)))
    validate_text_free_illustration(jpeg())


def test_same_alphanumeric_token_with_case_and_punctuation_changes_confirms(engine):
    two_scans(engine, output('Ç-e!', 40, (10, 10, 20, 20)), output('çe', 45, (20, 10, 20, 20)))
    with pytest.raises(IllustrationTextRejected) as caught:
        validate_text_free_illustration(jpeg())
    assert {finding['text'] for finding in caught.value.findings} == {'Ç-e!', 'çe'}


@pytest.mark.parametrize('offset,rejected', [(10, True), (11, False)], ids=['half-overlap', 'below-half'])
def test_confirmation_requires_half_the_smaller_box_area(engine, offset, rejected):
    two_scans(engine, output('ab', 20, (10, 10, 20, 20)), output('ab', 20, (10 + offset, 10, 20, 20)))
    if rejected:
        with pytest.raises(IllustrationTextRejected):
            validate_text_free_illustration(jpeg())
    else:
        validate_text_free_illustration(jpeg())


def test_contained_smaller_box_confirms_even_if_larger_box_differs(engine):
    two_scans(engine, output('ab', 20, (10, 10, 100, 40)), output('ab', 20, (40, 20, 20, 10)))
    with pytest.raises(IllustrationTextRejected):
        validate_text_free_illustration(jpeg())


def test_zero_area_box_cannot_confirm_a_word(engine):
    two_scans(engine, output('ab', 30, (10, 10, 0, 20)), output('ab', 30, (10, 10, 0, 20)))
    validate_text_free_illustration(jpeg())


def test_confirmation_requires_original_confidence_boundaries_in_both_scans(engine):
    two_scans(engine, output('ab', 20), output('ab', 19.99))
    validate_text_free_illustration(jpeg())


def test_malformed_confirmation_scan_still_fails_closed_after_detected_year(engine):
    two_scans(engine, output('2021', 1), b'not TSV')
    with pytest.raises(IllustrationCheckUnavailable):
        validate_text_free_illustration(jpeg())


def test_confirmation_scan_timeout_fails_closed_without_leaking_diagnostics(engine):
    engine.side_effect = [subprocess.CompletedProcess([], 0, stdout=output('ab', 40), stderr=b''),
                          subprocess.TimeoutExpired(['tesseract'], 15, stderr=b'private OCR detail')]
    with pytest.raises(IllustrationCheckUnavailable) as caught:
        validate_text_free_illustration(jpeg())
    assert 'private' not in str(caught.value)


@pytest.mark.parametrize('left', ['invalid', '-1', '769'])
def test_malformed_or_unbounded_ocr_coordinates_fail_closed(engine, left):
    engine.return_value.stdout = output('word', 90).replace(b'\t100\t100\t', f'\t{left}\t100\t'.encode())
    with pytest.raises(IllustrationCheckUnavailable):
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

