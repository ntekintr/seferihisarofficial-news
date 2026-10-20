"""User-approved headline colors, real ink separation and immutable old claims."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from seferihisar import render
from seferihisar.card_layout import VERSION, LEGACY, prepare
from seferihisar.editorial_render import BODY, TEAL, TextFields, editorial_card
from seferihisar.security import validate_state
from seferihisar.schedule import queue_item
from seferihisar.text_quality import TextRenderError


@pytest.mark.parametrize('story', [False, True])
@pytest.mark.parametrize('scene', ['news', 'long_news', 'event', 'photo_event', 'outage'])
def test_actual_text_ink_never_crosses_heading_date_content_note_or_footer(tmp_path, monkeypatch, story, scene):
    drawn = []
    original = TextFields.line
    def capture(self, value, x, y, size, color, role, box, bold=False):
        original(self, value, x, y, size, color, role, box, bold)
        drawn.append((value, self.bounds[-1][0], role, color))
    monkeypatch.setattr(TextFields, 'line', capture)
    title = 'Seferihisar’da yerel üretime ulaşım ve sakız ağacı yetiştiriciliği desteği açıklandı'
    body = 'Her pazar ücretsiz pazar otobüsü seferleri ve üretime yönelik yeni proje açıklandı.'
    event = scene in ('event', 'photo_event', 'outage')
    category = 'news'
    photo = None
    if scene == 'long_news':
        body *= 80
    if event:
        category = 'theatre'
        title = 'Kralın Çiçekleri — Tiyatro oyunu'
        body = '25.10.2026 · 11:00\n\nUrla Atatürk Kültür Merkezi\n\nDüzenleyen: Nar Sahne\n\nÜcret: 536 TL'
    if scene == 'photo_event':
        photo = Path('tests/fixtures/visual-match/concert-accepted.jpg')
    if scene == 'outage':
        category = 'outage'
        title = 'Urla’da planlı elektrik kesintisi'
        body = '25.10.2026 · 09:30 – 17:30\n\nEtkilenen bölge: Altıntaş, İçmeler\n\nAyrıntılı sokak listesi açıklamada.'
    target = tmp_path/'card.jpg'
    editorial_card(title, body, category, target, story=story, event_details=event,
                   illustration=photo, story_details=True, caption_note=True)
    with Image.open(target) as image:
        assert image.size == (1080, 1920 if story else 1350)
        if not photo:
            sample = image.getpixel((20, 700))
            assert max(abs(v - expected) for v, expected in zip(sample, (244, 239, 228))) <= 3
    heading = [b for _, b, role, _ in drawn if role == 'heading']
    content = [b for _, b, role, _ in drawn if role in ('date', 'details', 'summary')]
    note = [b for text, b, _, _ in drawn if text == 'Detaylar açıklamada.']
    assert heading and content and len(note) == 1
    assert max(b[3] for b in heading) < min(b[1] for b in content)
    assert max(b[3] for b in content) < note[0][1]
    assert note[0][3] < min(b[1] for _, b, role, _ in drawn if role == 'handle')
    for i, (_, a, _, _) in enumerate(drawn):
        assert 0 <= a[0] < a[2] <= 1080
        assert (260 if story else 0) <= a[1] < a[3] <= (1600 if story else 1260)
        for _, b, _, _ in drawn[i+1:]:
            assert not (max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]))
    assert {color for _, _, role, color in drawn if role == 'heading'} == {render.NAVY, TEAL}
    assert {color for _, _, role, color in drawn if role in ('details', 'summary')} == {BODY}
    if scene == 'long_news':
        assert any(text.endswith('…') for text, _, role, _ in drawn if role == 'summary')
    if event:
        visible = ' '.join(t for t, _, _, _ in drawn)
        for fact in (('25 Ekim 2026', '09:30', '17:30', 'Altıntaş, İçmeler') if scene == 'outage'
                     else ('25 Ekim 2026', '11:00', 'Urla Atatürk Kültür Merkezi', '536 TL')):
            assert fact in visible


@pytest.mark.parametrize('problem', ['heading', 'glyph_heading', 'glyph_body', 'date', 'venue'])
def test_unrenderable_heading_or_essential_fact_never_produces_ready_jpeg(tmp_path, problem):
    title, body = 'Urla’da tiyatro', '25.10.2026 · 11:00\nUrla Kültür Merkezi\nÜcret: 250 TL'
    if problem == 'heading': title *= 100
    if problem == 'glyph_heading': title += '\U0010ffff'
    if problem == 'glyph_body': body += '\U0010ffff'
    if problem == 'date': body = '25.10.2026 · 11:00 ' * 100 + '\nUrla Kültür Merkezi'
    if problem == 'venue': body = '25.10.2026 · 11:00\n' + 'Urla Kültür Merkezi ' * 100 + '\nÜcret: 250 TL'
    with pytest.raises(TextRenderError):
        editorial_card(title, body, 'theatre', tmp_path/'bad.jpg', event_details=True, caption_note=True)
    assert not (tmp_path/'bad.jpg').exists()


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
@pytest.mark.parametrize('policy', [None, LEGACY, VERSION])
def test_every_claim_keeps_its_original_layout_and_payload(tmp_path, monkeypatch, status, policy):
    post = {'id': 'a'*24, 'kind': 'news', 'category': 'news', 'status': status,
            'slides': [{'title': 'Seferihisar gündemi', 'body': 'Haberin ayrıntıları'}]}
    if policy: post['card_layout'] = policy
    before = deepcopy(post)
    prepare(post)
    assert post == before
    calls = []
    monkeypatch.setattr(render, 'card', lambda *a, **kw: calls.append(kw))
    render.render_post(post, tmp_path)
    assert calls and all(c['editorial_layout'] == (policy == VERSION) for c in calls)
    assert all(c['caption_note'] == (policy is not None) for c in calls)


@pytest.mark.parametrize('policy', [LEGACY, VERSION])
def test_durable_boundary_accepts_both_known_layouts(store, event, at, policy):
    store.upsert(event, at.isoformat())
    queue_item(store, store.items()[0], 'announcement', at, at)
    post = store.posts()[0]
    post['card_layout'] = policy
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(post), post['id']))
    validate_state(store.path)


@pytest.mark.parametrize('index', ['1/1', '2/3'])
def test_single_card_has_no_redundant_counter_and_carousel_counter_clears_ribbon(tmp_path, monkeypatch, index):
    drawn = []
    original = TextFields.line
    def capture(self, value, x, y, size, color, role, box, bold=False):
        original(self, value, x, y, size, color, role, box, bold)
        if role == 'page': drawn.append(self.bounds[-1][0])
    monkeypatch.setattr(TextFields, 'line', capture)
    editorial_card('Seferihisar gündemi', 'Güncel bilgiler açıklandı.', 'news', tmp_path/'card.jpg', index=index)
    if index == '1/1':
        assert drawn == []
    else:
        assert len(drawn) == 1 and drawn[0][3] < 1350 - 98
