"""Regression from the delivered yoga card; no new source claims or social writes."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar import event_metadata
from seferihisar.domain import digest, parse_date
from seferihisar.editor import caption
from seferihisar.pipeline import _export
from seferihisar.quality import publication_copy_reason
from seferihisar.facebook import publish_recent
from seferihisar.instagram import publish_one
from seferihisar.schedule import prepare, queue_item, slide_body
from seferihisar.visual_gate import deployed, review


@pytest.fixture
def yoga():
    return json.loads(Path('tests/fixtures/event-yoga-metadata.json').read_text(encoding='utf-8'))


def test_actual_raw_yoga_roles_are_not_presented_as_verified_organizer(yoga):
    original = deepcopy(yoga)
    value = caption(yoga, yoga['title'])
    body = slide_body(yoga)
    assert 'Organizatör: Bubilet' not in value and 'Düzenleyen: Bubilet' not in body
    assert 'Organizatör: Doğrulanamadı' in value and 'Bilet platformu: Bubilet' in value
    assert 'İzmir İzmir' not in value
    assert 'Bademler Caddesi No:8 Bademler Mahallesi Urla İzmir' in value
    assert yoga['url'] in value and '560 TL' in body and '18.10.2026' in body
    assert yoga == original  # No rewrite of the source evidence or factual revision.


@pytest.mark.parametrize('name', ['Bubilet', 'BUBİLET', 'bubilet.com.tr', 'www.bubilet.com.tr',
                                  'Biletix', 'Biletinial', 'Biletino'])
def test_reviewed_platform_name_alone_is_not_producer_evidence(yoga, name):
    yoga['organizer'] = name
    assert event_metadata.organizer(yoga) is None


@pytest.mark.parametrize('name', ['İzmir Kent Tiyatrosu', 'Urla Rotary Kulübü',
                                  'Bubilet Kültür Derneği', 'Canan Tutal'])
def test_explicit_distinct_organizer_is_preserved_without_substring_guessing(yoga, name):
    yoga['organizer'] = name
    assert event_metadata.organizer(yoga) == name
    assert 'Organizatör: ' + name in caption(yoga, yoga['title'])
    assert 'Düzenleyen: ' + name in slide_body(yoga)


@pytest.mark.parametrize('url,expected', [
    ('https://bubilet.com.tr/izmir/etkinlik/yoga', 'Bubilet'),
    ('https://www.biletix.com/etkinlik/123', 'Biletix'),
    ('https://biletinial.com/tr-tr/tiyatro/123', 'Biletinial'),
    ('https://biletino.com/e-123/test/', 'Biletino'),
    ('https://bubilet.com.tr.example.org/123', None),
    ('https://example.org/bubilet.com.tr', None),
])
def test_ticket_platform_comes_from_exact_reviewed_host(url, expected):
    assert event_metadata.ticket_platform({'ticket_url': url}) == expected


@pytest.mark.parametrize('original,expected', [
    ('Bademler Sanat Köyü Urla İzmir İzmir', 'Bademler Sanat Köyü Urla İzmir'),
    ('Urla Atatürk Kültür Merkezi İzmir, İzmir', 'Urla Atatürk Kültür Merkezi İzmir'),
    ('Salon · Urla İzmir Urla İzmir', 'Salon · Urla İzmir'),
    ('Salon · Urla İzmir İzmir İzmir', 'Salon · Urla İzmir'),
    ('İzmir Caddesi No:8 Urla İzmir', 'İzmir Caddesi No:8 Urla İzmir'),
    ('İzmir Mahallesi İzmir', 'İzmir Mahallesi İzmir'),
    ('Salon No:8 8 Urla İzmir', 'Salon No:8 8 Urla İzmir'),
    ('Urla İzmir Urla 8 İzmir', 'Urla İzmir Urla 8 İzmir'),
    ('Salon 123 İzmir', 'Salon 123 İzmir'),
    ('Salon · Konak İzmir', 'Salon · Konak İzmir'),
])
def test_only_exact_geographic_suffix_repetitions_are_removed(original, expected):
    assert event_metadata.location({'location': original}) == expected


def test_unknown_organizer_is_not_invented_from_venue_source_or_teacher(yoga):
    yoga['organizer'] = None
    assert event_metadata.organizer(yoga) is None
    assert 'Düzenleyen:' not in slide_body(yoga)
    assert 'Organizatör: Açıklanmadı' in caption(yoga, yoga['title'])


@pytest.mark.parametrize('story', [False, True])
def test_old_bad_draft_is_rejected_before_media_fetch_even_with_new_visual_hash(store, yoga, story):
    at = parse_date('2026-10-18T08:30:00+03:00')
    store.upsert(yoga, at.isoformat()); item = store.items()[0]
    queue_item(store, item, 'reminder_day', at, at); parent = store.posts()[0]
    parent['caption'] = parent['caption'].replace('Organizatör: Doğrulanamadı', 'Organizatör: Bubilet')
    parent['visual_review'] = review(parent, {})
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(parent), parent['id']))
    post = {**parent, 'publish_format': 'story', 'parent_post_id': parent['id']} if story else parent
    client = Mock()
    assert deployed(store, post, 'https://example.org/', ['media/a/feed-1.jpg'], client, story=story) == 'event_metadata_stale'
    client.get.assert_not_called()


def test_normal_preparation_repairs_pending_drafts_but_freezes_all_claims(store, yoga):
    at = parse_date('2026-10-18T08:30:00+03:00')
    store.upsert(yoga, at.isoformat()); item = store.items()[0]
    queue_item(store, item, 'announcement', at, at)
    post = store.posts()[0]
    post['caption'] = 'Organizatör: Bubilet. İzmir İzmir'
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(post), post['id']))
    for status in ('published', 'publishing', 'uncertain'):
        frozen = {**post, 'id': digest(status), 'published_at': at.isoformat()}
        store.queue(frozen)
        with store.db:
            store.db.execute('UPDATE posts SET status=?,media_id=? WHERE id=?', (status, 'existing-media', frozen['id']))
    raw = store.rows('SELECT * FROM items')
    claims = store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id")
    prepare(store, at)
    assert store.rows('SELECT * FROM items') == raw
    assert store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id") == claims
    pending = next(p for p in store.posts() if p['id'] == post['id'])
    assert publication_copy_reason(pending, {item['id']: item}) is None
    assert 'Organizatör: Bubilet' not in pending['caption'] and 'İzmir İzmir' not in pending['caption']


def test_bad_calendar_slide_cannot_be_approved_from_its_own_hash(store, yoga):
    at = parse_date('2026-10-18T08:30:00+03:00')
    store.upsert(yoga, at.isoformat()); item = store.items()[0]
    prepare(store, at)
    digest = next(p for p in store.posts() if p['kind'] == 'monthly')
    assert publication_copy_reason(digest, {item['id']: item}) is None
    digest['slides'][1]['body'] += '\nDüzenleyen: Bubilet'
    assert publication_copy_reason(digest, {item['id']: item}) == 'event_metadata_stale'


def test_export_holds_old_bad_event_metadata_instead_of_rendering_a_ready_card(store, yoga, tmp_path):
    at = parse_date('2026-10-18T08:30:00+03:00')
    source = next(s for s in json.loads(Path('config/sources.json').read_text(encoding='utf-8'))
                  if s['id'] == yoga['source_id'])
    store.upsert(yoga, at.isoformat()); item = store.items()[0]
    queue_item(store, item, 'reminder_day', at, at); post = store.posts()[0]
    post['slides'][0]['body'] += '\nDüzenleyen: Bubilet'
    with store.db:
        store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(post), post['id']))
    _export(store, tmp_path/'public', [source], at)
    assert store.posts()[0]['status'] == 'blocked_source'
    assert store.rows('SELECT reason FROM withheld') == [{'reason': 'event_metadata_stale'}]


@pytest.mark.parametrize('destination', ['feed', 'story', 'facebook'])
def test_destination_makes_no_meta_write_for_stale_deployed_metadata(store, yoga, destination):
    at = parse_date('2026-10-18T08:30:00+03:00')
    store.upsert(yoga, at.isoformat()); item = store.items()[0]
    queue_item(store, item, 'reminder_day', at, at); post = store.posts()[0]
    # Publisher preparation corrects text, so the previous deployed proof is
    # invalid. A Facebook continuation of the old claim is held as stale copy.
    post['caption'] = post['caption'].replace('Organizatör: Doğrulanamadı', 'Organizatör: Bubilet')
    post['visual_review'] = review(post, {})
    paths = {post['id']: {fmt: [f"media/{post['visual_review']['edition']}/{fmt}-1.jpg"]
                         for fmt in ('feed', 'story')}}
    with store.db:
        if destination == 'facebook':
            post['published_at'] = at.isoformat()
            store.db.execute("UPDATE posts SET payload=?,status='published',media_id='existing' WHERE id=?",
                             (json.dumps(post), post['id']))
        else:
            store.db.execute('UPDATE posts SET payload=? WHERE id=?', (json.dumps(post), post['id']))
    api = Mock(); api.page = "synthetic-page"; api.enabled.return_value = api.check_identity.return_value = True
    result = (publish_recent(store, at, 'https://example.org/', paths, api, require_visual_review=True)
              if destination == 'facebook' else
              publish_one(store, at, 'https://example.org/', paths, story=destination=='story',
                          adapter=api, require_visual_review=True))
    assert result['status'] == ('event_metadata_stale' if destination=='facebook' else 'visual_review_missing')
    api.session.head.assert_not_called(); api.session.get.assert_not_called()
    api.container.assert_not_called(); api.publish.assert_not_called()
    api.upload.assert_not_called(); api.call.assert_not_called()
    assert not store.rows('SELECT * FROM facebook_deliveries')


def test_metadata_hold_survives_safe_operations_log(store, at):
    from seferihisar.operations import failed, record_check
    from seferihisar.security import validate_state
    result = {'status': 'event_metadata_stale'}
    assert failed(result)
    record_check(store, result, at, 'automatic')
    validate_state(store.path)
    assert json.loads(store.rows('SELECT result FROM publication_checks')[0]['result']) == result
