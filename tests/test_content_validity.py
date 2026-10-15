import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest
from seferihisar.editor import verify
from seferihisar.facebook import publish_recent
from seferihisar.instagram import prepare_story_jobs, publish_one
from seferihisar.pipeline import run
from seferihisar.schedule import prepare, source_current
from seferihisar.timeliness import publication_reason, service_expiry, with_validity


def notice(at, **changes):
    return {'kind': 'news', 'title': 'Seferihisar elektrik kesintisi',
            'description': '10 Ekim 2026 saat 09:00–12:00 arasında elektrik kesintisi.',
            'category': 'outage', 'url': 'https://seferihisar.bel.tr/notice',
            'sources': ['https://seferihisar.bel.tr/notice'],
            'source_id': 'seferihisar-belediye', 'source_name': 'Belediye',
            'published_at': (at - timedelta(hours=1)).isoformat(), **changes}


@pytest.mark.parametrize('prose', [
    '10.10.2026 09:00–12:00', '10 EKİM 2026 saat 09.00-12.00',
])
def test_explicit_full_year_same_day_service_period(prose):
    assert service_expiry(prose).isoformat() == '2026-10-10T12:00:00+03:00'


@pytest.mark.parametrize('prose', [
    '10 Ekim 09:00–12:00', 'bugün 09:00–12:00', '10.10.2026 25:00–26:00',
    '31.02.2026 09:00–12:00', '10.10.2026 12:00–09:00', '10.10.2026 23:00–02:00',
    '10.10.2026 09:00–12:00, 11.10.2026 13:00–15:00',
    '10.10.2026 09:00–12:00, 11 Ekim 13:00–15:00',
    '10.10.2026 09:00–12:00, 11.10. duyuru',
    '10.10.2026 duyurusu, yarın 09:00–12:00',
    '10.10.2026 08:00 duyurusu: 09:00–12:00',
])
def test_ambiguous_or_incomplete_service_period_is_not_guessed(prose):
    assert service_expiry(prose) is None


def test_validity_does_not_renew_on_recrawl_or_replace_bad_field(at, source):
    item = notice(at)
    dated = with_validity(item)
    assert 'valid_until' not in item
    assert dated['published_at'] == item['published_at']
    assert dated['valid_until'] == '2026-10-10T12:00:00+03:00'
    assert verify(dated, source, at) is None
    end = at.replace(hour=12)
    assert verify(dated, source, end) == 'expired_service_notice'
    assert not source_current({**dated, 'last_seen': end.isoformat()}, end, set())
    assert with_validity({**item, 'valid_until': 'bad'})['valid_until'] == 'bad'


@pytest.mark.parametrize('category,title', [
    ('weather', 'Seferihisar hava uyarısı'), ('outage', 'Seferihisar su kesintisi'),
    ('festival', 'Seferihisar festivali için fırtına uyarısı'),
    ('transport', 'Seferihisar yol kapatılacak'),
])
def test_unverified_warning_cannot_use_ordinary_48_hour_lifetime(at, source, category, title):
    item = notice(at, category=category, title=title, description='Kaynak bitiş zamanı açıklamadı.')
    assert verify(item, source, at) == 'missing_service_validity'
    assert not source_current({**item, 'last_seen': at.isoformat()}, at, set())


def test_ordinary_transport_project_keeps_original_48_hour_limit(at):
    item = notice(at, category='transport', title='Seferihisar çevre yolu projesi',
                  description='Yeni yolun yapımında sona gelindi.')
    assert with_validity(item) == item and publication_reason(item, at) is None
    item['published_at'] = (at - timedelta(hours=48)).isoformat()
    assert publication_reason(item, at) is None
    assert publication_reason(item, at + timedelta(seconds=1)) == 'expired_news'
    assert not source_current({**item, 'last_seen': (at + timedelta(seconds=1)).isoformat()},
                              at + timedelta(seconds=1), set())


@pytest.mark.parametrize('category,description,blocked', [
    ('concert', 'Seferihisar konseri başlayacak, biletler satışta.', True),
    ('municipality', 'Seferihisar tiyatro gösterisine davetlisiniz.', True),
    ('festival', 'Seferihisar festivalinde dün konser gerçekleşti.', False),
])
def test_invitation_without_parsed_occurrence_cannot_fall_back_to_news(at, source, category, description, blocked):
    item = notice(at, title='Seferihisar kültür haberi', category=category, description=description)
    assert (verify(item, source, at) == 'missing_event_date') is blocked
    assert (publication_reason(item, at) == 'missing_event_date') is blocked


def test_generic_warning_is_dated_before_pipeline_verification(tmp_path, at):
    fixture = tmp_path / 'items.json'
    fixture.write_text(json.dumps([notice(at)]), encoding='utf-8')
    result = run(tmp_path / 'state.sqlite', tmp_path / 'public',
                 Path('config/sources.json'), at, fixture)
    assert result['collected'] == 1
    data = json.loads((tmp_path / 'public/data.json').read_text(encoding='utf-8'))
    assert data['news'][0]['valid_until'] == '2026-10-10T12:00:00+03:00'


@pytest.mark.parametrize('status', ['scheduled', 'cancelled', 'postponed', 'rescheduled'])
def test_existing_event_cards_and_digests_expire_at_exact_end(store, event, at, status):
    end = at + timedelta(minutes=15)
    event.update(start=at.isoformat(), end=end.isoformat(), status=status)
    store.upsert(event, at.isoformat())
    prepare(store, at)
    assert any(p['status'] == 'prepared' for p in store.posts())
    # Recrawling does not extend the original occurrence, including corrections.
    store.upsert(event, end.isoformat())
    prepare(store, end)
    assert not any(p['status'] == 'prepared' for p in store.posts())
    assert not source_current(store.items()[0], end, set())


def test_unknown_clock_is_held_on_last_day_then_can_be_confirmed(store, event, at):
    tomorrow = (at + timedelta(days=1)).replace(hour=0)
    event.update(start=tomorrow.isoformat(), end=tomorrow.isoformat(), time_known=False)
    store.upsert(event, at.isoformat())
    prepare(store, at)
    assert any(p['status'] == 'prepared' for p in store.posts())
    store.upsert(event, tomorrow.isoformat())
    prepare(store, tomorrow)
    assert not any(p['status'] == 'prepared' for p in store.posts())
    event.update(start=tomorrow.replace(hour=20).isoformat(),
                 end=tomorrow.replace(hour=22).isoformat(), time_known=True)
    store.upsert(event, tomorrow.isoformat())
    prepare(store, tomorrow)
    assert any(p['status'] == 'prepared' for p in store.posts())


@pytest.mark.parametrize('story', [False, True])
@pytest.mark.parametrize('reason', ['past_cancellation', 'unknown_time', 'missing_validity', 'expired_warning'])
def test_legacy_queue_cannot_reach_instagram_after_validity_check(store, event, at, story, reason):
    item = notice(at) if 'validity' in reason or 'warning' in reason else event
    store.upsert(item, at.isoformat())
    # Construct an old prepared row to exercise migration without a fresh crawl.
    key = digest('legacy-parent')
    post = {'id': key, 'item_id': store.items()[0]['id'], 'revision': 1,
            'kind': 'news' if item['kind'] == 'news' else 'cancellation',
            'due_at': at.isoformat(), 'created_at': at.isoformat(), 'title': item['title'],
            'caption': 'Legacy caption', 'source_urls': item['sources'], 'category': item['category'],
            'formats': ['feed', 'story'], 'slides': [{'title': item['title'], 'body': 'Legacy body'}]}
    store.queue(post)
    assets = {key: {fmt: [f'media/{key}/{fmt}-1.jpg'] for fmt in ('feed', 'story')}}
    prepare_story_jobs(store, assets)
    if reason == 'past_cancellation':
        item.update(start=(at - timedelta(hours=2)).isoformat(), end=at.isoformat(), status='cancelled')
    elif reason == 'unknown_time':
        item.update(start=at.replace(hour=0).isoformat(), end=at.replace(hour=0).isoformat(), time_known=False)
    elif reason == 'expired_warning':
        item['valid_until'] = at.isoformat()
    # Keep revision unchanged, as in state created by the earlier software.
    with store.db:
        store.db.execute('UPDATE items SET payload=?', (json.dumps(item),))
    api = Mock()
    api.enabled.return_value = True
    result = publish_one(store, at, 'https://example.org/', assets, story=story, adapter=api)
    assert result['status'] == 'empty'
    api.container.assert_not_called()
    assert not any(p['status'] in ('publishing', 'published') for p in store.posts())


@pytest.mark.parametrize('reason', ['past_cancellation', 'unknown_time', 'missing_validity', 'expired_warning'])
def test_facebook_holds_both_deliveries_without_changing_instagram_claims(store, event, at, reason):
    item = notice(at) if 'validity' in reason or 'warning' in reason else event
    if reason == 'past_cancellation':
        item.update(start=(at - timedelta(hours=2)).isoformat(), end=at.isoformat(), status='cancelled')
    elif reason == 'unknown_time':
        item.update(start=at.replace(hour=0).isoformat(), end=at.replace(hour=0).isoformat(), time_known=False)
    elif reason == 'expired_warning':
        item['valid_until'] = at.isoformat()
    item_id, _ = store.upsert(item, at.isoformat())
    key = digest('frozen-parent')
    post = {'id': key, 'item_id': item_id, 'revision': 1, 'kind': 'news',
            'due_at': at.isoformat(), 'published_at': (at - timedelta(minutes=1)).isoformat(),
            'source_urls': item['sources'], 'caption': 'Frozen caption'}
    store.queue(post)
    store.queue({**post, 'id': digest(key + ':story:0'), 'publish_format': 'story',
                 'parent_post_id': key, 'story_asset': f'media/{key}/story-1.jpg'})
    with store.db:
        store.db.execute("UPDATE posts SET status='published',media_id='synthetic-media'")
    before = store.rows('SELECT * FROM posts ORDER BY id')
    api = Mock()
    api.enabled.return_value = api.check_identity.return_value = True
    assert publish_recent(store, at, 'https://example.org/', {}, api)['status'] == 'blocked_source'
    api.upload.assert_not_called()
    api.publish.assert_not_called()
    assert store.rows('SELECT * FROM facebook_deliveries') == []
    assert store.rows('SELECT * FROM posts ORDER BY id') == before
