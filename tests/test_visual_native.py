"""Real CPU-model regression, independent of mock-based pipeline tests."""
import os
from pathlib import Path

import pytest

from seferihisar.visual_match import MatchRejected, validate_match

pytestmark=pytest.mark.skipif(os.getenv('RUN_VISUAL_NATIVE')!='true',reason='Explicit pinned CPU visual model job')
ROOT=Path('tests/fixtures/visual-match')


@pytest.mark.parametrize('file,expected',[
    ('traffic-meeting','theatre'),('hall-outage','theatre'),('dry-road-flood','festival'),
    ('yoga','yoga'),('theatre','theatre'),('tile-art','tile_art'),
    ('tile_art-accepted','tile_art'),
])
def test_observed_unrelated_scenes_are_rejected(file,expected):
    with pytest.raises(MatchRejected):validate_match((ROOT/(file+'.jpg')).read_bytes(),expected)


@pytest.mark.parametrize('expected',['festival','concert','yoga'])
def test_reviewed_current_matching_scenes_pass_both_crops(expected):
    proof=validate_match((ROOT/(expected+'-accepted.jpg')).read_bytes(),expected)
    assert proof['subject']==expected
