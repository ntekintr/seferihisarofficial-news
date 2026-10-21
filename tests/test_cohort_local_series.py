import json
from datetime import timedelta
from pathlib import Path

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.learning import due
from seferihisar.learning_cohorts import cohort_for, pending, record, weights
from seferihisar.local_series import prepare, edition, expired, current_copy
from seferihisar.quality import publication_copy_reason
from seferihisar.security import validate_state
from seferihisar.selection import prioritize


@pytest.mark.parametrize('hours,expected', [(23.9, None), (24, 'day1'), (29.99, 'day1'), (30, None),
    (150, None), (168, 'day7'), (173.99, 'day7'), (174, None)])
def test_ages_are_never_mixed_or_backfilled(at, hours, expected):
    assert cohort_for(at - timedelta(hours=hours), at) == expected


def published(store, at, index=0, category='theatre', age=25):
    p = {'id': digest('post' + str(index)), 'item_id': digest('item' + str(index)), 'revision': 1,
         'kind': 'news', 'due_at': at.isoformat(), 'published_at': (at - timedelta(hours=age)).isoformat(),
         'category': category}
    store.queue(p)
    store.db.execute("UPDATE posts SET status='published',media_id=? WHERE id=?", (str(1000 + index), p['id']))
    store.db.commit()
    return p


def values(score=10):
    return {'reach': 123791, 'total_interactions': score * 1238, 'saved': 0, 'shares': 0}


def test_first_cohort_is_frozen_without_raw_counters_or_claim_changes(store, at):
    p = published(store, at)
    old = store.rows('SELECT * FROM posts')
    assert len(pending(store, at)) == 1
    record(store, p, 'day1', values(10), at)
    first = store.rows('SELECT * FROM learning_samples')
    record(store, p, 'day1', values(40), at + timedelta(hours=1))
    assert store.rows('SELECT * FROM learning_samples') == first
    assert '123791' not in json.dumps(first)
    assert not pending(store, at)
    assert store.rows('SELECT * FROM posts') == old
    validate_state(store.path)


def test_pending_age_window_wakes_feedback_without_waiting_until_midnight(store, at):
    published(store, at)
    store.db.execute('INSERT INTO learning_profile VALUES (?,?)', ('instagram', json.dumps({
        'version': 'topic-feedback-v2', 'checked_at': (at - timedelta(hours=2)).isoformat(),
        'status': 'insufficient_data', 'weights': {}})))
    assert due(store, at)
    with pytest.raises(ValueError, match='window'):
        record(store, {'id': digest('x'), 'category': 'theatre', 'published_at': (at - timedelta(hours=60)).isoformat()}, 'day1', values(), at)


def test_minimum_samples_are_required_within_one_age_cohort(store, at):
    for index in range(10):
        age = 25 if index < 5 else 169
        p = published(store, at, index, 'theatre' if index < 5 else 'concert', age)
        record(store, p, 'day1' if age == 25 else 'day7', values(30 if index < 5 else 2), at)
    assert weights(store, at) == {}
    for index in range(10, 15):
        p = published(store, at, index, 'concert', 25)
        record(store, p, 'day1', values(2), at)
    assert weights(store, at) == {'theatre': 1, 'concert': 0}


def add_events(store, event, at, starts, free_values):
    items = []
    for index, (start, free) in enumerate(zip(starts, free_values)):
        value = {**event, 'title': 'Seferihisar çocuk tiyatrosu ' + str(index),
                 'url': 'https://seferihisar.bel.tr/program-' + str(index),
                 'sources': ['https://seferihisar.bel.tr/program-' + str(index)],
                 'source_id': 'seferihisar-belediye', 'source_name': 'Seferihisar Belediyesi',
                 'start': start.isoformat(), 'end': (start + timedelta(hours=2)).isoformat(),
                 'time_known': True, 'status': 'scheduled', 'category': 'theatre',
                 'location': 'Seferihisar kültür merkezi', 'free': free, 'price': None, 'currency': None}
        value.pop('identity', None)
        key, _ = store.upsert(value, at.isoformat())
        items.append(next(i for i in store.items() if i['id'] == key))
    return items


def test_weekend_edition_contains_actual_events_and_sources_then_freezes(store, event, tmp_path):
    at = parse_date('2026-10-23T12:40:00+03:00')
    starts = [parse_date('2026-10-24T14:00:00+03:00'), parse_date('2026-10-25T15:00:00+03:00')]
    items = add_events(store, event, at, starts, [True, False])
    prepare(store, at)
    post = next(p for p in store.posts() if p['kind'] == 'weekend')
    assert len(post['slides']) == 3 and all(url in post['caption'] for url in post['source_urls'])
    assert post['slides'][0]['body'].startswith('24.10.2026 – 25.10.2026')
    assert current_copy(post, {i['id']: i for i in items})
    from seferihisar.render import render_post
    assets = render_post(post, tmp_path / 'cards')
    assert len(assets['feed']) == 3
    store.db.execute("UPDATE posts SET status='uncertain',container_id='444' WHERE id=?", (post['id'],))
    store.db.commit()
    old = store.rows('SELECT * FROM posts')
    prepare(store, at + timedelta(minutes=10))
    assert store.rows('SELECT * FROM posts') == old
    assert expired(post, parse_date('2026-10-24T13:30:00+03:00'))
    validate_state(store.path)


def test_free_guide_never_invents_free_admission_and_rechecks_changes(store, event):
    at = parse_date('2026-10-20T12:40:00+03:00')
    starts = [at + timedelta(days=1, hours=i) for i in range(4)]
    items = add_events(store, event, at, starts, [True, True, False, None])
    prepare(store, at)
    post = next(p for p in store.posts() if p['kind'] == 'free_week')
    assert len(post['source_urls']) == 2
    by_id = {i['id']: i for i in items}
    assert publication_copy_reason(post, by_id) is None
    by_id[items[0]['id']]['free'] = False
    assert publication_copy_reason(post, by_id) == 'event_metadata_stale'


def test_a_single_event_does_not_create_a_fake_roundup(store, event):
    at = parse_date('2026-10-23T12:40:00+03:00')
    add_events(store, event, at, [at + timedelta(days=1)], [True])
    prepare(store, at)
    assert not store.posts()


def test_urgent_service_still_precedes_scheduled_series(store, event):
    at = parse_date('2026-10-23T12:40:00+03:00')
    add_events(store, event, at, [at + timedelta(days=1), at + timedelta(days=2)], [True, True])
    prepare(store, at)
    service = {'kind': 'news', 'title': 'Seferihisar elektrik kesintisi', 'category': 'outage',
               'description': 'Bugün Seferihisar merkezindeki planlı çalışma hakkında resmî açıklama.',
               'url': 'https://seferihisar.bel.tr/uyari', 'published_at': at.isoformat()}
    key, _ = store.upsert(service, at.isoformat())
    urgent = {'id': digest('urgent'), 'item_id': key, 'revision': 1, 'kind': 'news',
              'due_at': at.isoformat(), 'category': 'outage'}
    store.queue(urgent)
    assert prioritize(store, store.posts(), at)[0]['id'] == urgent['id']
