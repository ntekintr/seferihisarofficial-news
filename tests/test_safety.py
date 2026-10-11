import json
from pathlib import Path

from PIL import Image

from seferihisar.editor import caption, verify
from seferihisar.pipeline import run
from seferihisar.store import Store


def test_sensitive_content_requires_human_and_never_persists(event, source, at, tmp_path):
    event["title"] = "Seferihisar yolsuzluk iddiası ÖZEL İSİM"
    assert verify(event, source, at) == "human_review_required"
    fixture = tmp_path / 'input.json'
    fixture.write_text(json.dumps([event]))
    run(tmp_path/'state.sqlite', tmp_path/'public', Path('config/sources.json'), at, fixture)
    assert "ÖZEL İSİM" not in (tmp_path/'public/data.json').read_text()
    assert "ÖZEL İSİM".encode() not in (tmp_path/'state.sqlite').read_bytes()


def test_untrusted_source_not_verified(event, source, at):
    assert verify(event, {**source, "trusted": False}, at) == "unverified_source"


def test_missing_details_remain_unknown(event):
    event["free"] = None
    event["organizer"] = None
    event["location"] = None
    content = caption(event, "Duyuru")
    assert "Ücret bilgisi açıklanmadı" in content
    assert "Organizatör: Açıklanmadı" in content


def test_demo_end_to_end_dimensions_and_idempotency(at, tmp_path):
    args = (tmp_path/'state.sqlite', tmp_path/'public', Path('config/sources.json'), at, Path('tests/fixtures/items.json'))
    first = run(*args)
    second = run(*args)
    assert first["collected"] == 4 and second["collected"] == 0
    data = json.loads((tmp_path/'public/data.json').read_text())
    assert data['demo'] and not data['publishing_enabled']
    assert len(data['events']) == 3
    post = data['posts'][0]
    for fmt, size in [('feed', (1080,1350)), ('story',(1080,1920))]:
        with Image.open(tmp_path/'public'/post['assets'][fmt][0]) as image:
            assert image.size == size
    assert b'BEGIN:VEVENT' in (tmp_path/'public/events.ics').read_bytes()


def test_sensitive_revision_revokes_previous_public_copy(event, at, tmp_path):
    fixture = tmp_path/'input.json'
    fixture.write_text(json.dumps([event]))
    args = (tmp_path/'state.sqlite', tmp_path/'public', Path('config/sources.json'), at, fixture)
    run(*args)
    event['title'] = 'Seferihisar suç iddiası'
    fixture.write_text(json.dumps([event]))
    run(*args)
    data = json.loads((tmp_path/'public/data.json').read_text())
    assert not data['events']
    assert not any('suç' in p['title'] for p in data['posts'])


def test_tokens_not_in_public_state(event, at, tmp_path):
    event['url'] += '?access_token=VERYSECRET'
    event['sources'] = [event['url']]
    fixture = tmp_path/'input.json'
    fixture.write_text(json.dumps([event]))
    run(tmp_path/'state.sqlite', tmp_path/'public', Path('config/sources.json'), at, fixture)
    assert b'VERYSECRET' not in (tmp_path/'state.sqlite').read_bytes()
    assert 'VERYSECRET' not in (tmp_path/'public/data.json').read_text()
