"""Owner limits and the unchanged-card source-revision regression."""
import json
from copy import deepcopy
from datetime import timedelta

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.instagram import prepare_story_jobs, publish_automatic, publish_one
from seferihisar.publication_policy import daily_limit_reason, duplicate_reason, owner_exclusion
from seferihisar.schedule import prepare
from seferihisar.store import Store
from test_automatic_publication import api, claim, news


def all_assets(store):
    return {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"],
                      'story': [f"media/{p['id']}/story-1.jpg", f"media/{p['id']}/story-2.jpg"]}
            for p in store.posts() if not p.get('publish_format')}


def test_third_news_pair_is_allowed_and_fourth_attempt_cannot_use_manual_entrypoint(store):
    at = parse_date('2026-10-24T15:10:00+03:00')
    assets = {}
    for name in 'abcd': assets.update(news(store, at, name))
    parents = [p for p in store.posts() if not p.get('publish_format')]
    claim(store, parents[0], at.replace(hour=8, minute=35))
    claim(store, parents[1], at.replace(hour=12, minute=35), 'uncertain')
    adapter = api()
    assert publish_automatic(store, at, 'https://example.org/', assets, adapter)['status'] == 'complete'
    later = at.replace(hour=18, minute=35)
    for item in store.items():
        with store.db: store.db.execute('UPDATE items SET last_seen=? WHERE id=?', (later.isoformat(), item['id']))
    assert publish_one(store, later, 'https://example.org/', assets, adapter=adapter)['status'] == 'daily_limit'
    assert adapter.container.call_count == 2


def test_news_and_story_limits_are_separate_and_do_not_include_weather_or_pharmacy(store):
    at = parse_date('2026-10-24T15:10:00+03:00')
    with store.db:
        store.db.execute("INSERT INTO weather_stories(day,status,checked_at,last_result) VALUES(?,'published',?,'published')", (at.date().isoformat(), at.isoformat()))
        store.db.execute("INSERT INTO pharmacy_stories(day,status,checked_at,last_result) VALUES(?,'published',?,'published')", (at.date().isoformat(), at.isoformat()))
    assert daily_limit_reason(store, at) is None
    assert daily_limit_reason(store, at, story=True) is None
    for index, status in enumerate(('published', 'publishing', 'uncertain')):
        p = {'id': digest(str(index)), 'kind': 'news', 'revision': 1, 'due_at': at.isoformat(),
             'publish_format': 'story', 'published_at': at.isoformat()}
        store.queue(p)
        with store.db: store.db.execute('UPDATE posts SET status=? WHERE id=?', (status, p['id']))
    assert daily_limit_reason(store, at) is None
    assert daily_limit_reason(store, at, story=True) == 'daily_limit'


def outage(at):
    return {'kind': 'event', 'identity': 'https://example.org/outage/1',
            'title': 'Seferihisar’da planlı elektrik kesintisi', 'category': 'outage',
            'description': 'GDZ tarafından açıklanan Akarca ve Sığacık kesintisi.',
            'url': 'https://example.org/outage/1', 'sources': ['https://example.org/outage/1'],
            'source_name': 'GDZ', 'source_id': 'example',
            'start': at.replace(hour=10, minute=0).isoformat(),
            'end': at.replace(hour=17, minute=0).isoformat(), 'time_known': True,
            'location': 'Seferihisar · Akarca, Sığacık', 'status': 'scheduled',
            'organizer': None, 'free': None, 'price': None, 'currency': None,
            'ticket_url': None, 'previous_start': None}


def test_unchanged_outage_card_cannot_repeat_under_new_source_revision_or_story_id(store):
    morning = parse_date('2026-10-23T09:09:48+03:00')
    item = outage(morning)
    store.upsert(item, morning.isoformat())
    prepare(store, morning)
    adapter = api()
    assert publish_automatic(store, morning, 'https://example.org/', all_assets(store), adapter)['status'] == 'complete'
    frozen = store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id")
    afternoon = morning.replace(hour=12, minute=44, second=33)
    # Source metadata can change the item revision without changing displayed facts.
    store.upsert({**item, 'source_name': 'GDZ Elektrik Dağıtım'}, afternoon.isoformat())
    prepare(store, afternoon)
    assert publish_automatic(store, afternoon, 'https://example.org/', all_assets(store), adapter)['status'] == 'empty'
    assert adapter.container.call_count == 2
    assert store.rows("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain') ORDER BY id") == frozen
    old = next(p for p in store.posts() if p['status'] == 'published' and p.get('publish_format') == 'story')
    other = {**old, 'id': digest('other-story-revision'), 'parent_post_id': digest('other-parent')}
    assert duplicate_reason(store, other) == 'duplicate_story'


@pytest.mark.parametrize('change', ['time', 'location', 'cancelled'])
def test_real_outage_fact_change_is_eligible_and_is_not_an_identical_card(store, change):
    morning = parse_date('2026-10-23T09:09:48+03:00')
    item = outage(morning)
    store.upsert(item, morning.isoformat())
    prepare(store, morning)
    adapter = api()
    assert publish_automatic(store, morning, 'https://example.org/', all_assets(store), adapter)['status'] == 'complete'
    afternoon = morning.replace(hour=12, minute=44, second=33)
    changed = {**item}
    if change == 'time': changed['end'] = afternoon.replace(hour=16, minute=0).isoformat()
    elif change == 'location': changed['location'] = 'Seferihisar · Yalnız Akarca'
    else: changed['status'] = 'cancelled'
    store.upsert(changed, afternoon.isoformat())
    prepare(store, afternoon)
    assert publish_automatic(store, afternoon, 'https://example.org/', all_assets(store), adapter)['status'] == 'complete'
    assert adapter.container.call_count == 4


def test_story_cannot_resurrect_yesterdays_expired_outage_or_old_revision(store):
    morning = parse_date('2026-10-23T09:09:48+03:00')
    item = outage(morning)
    store.upsert(item, morning.isoformat())
    prepare(store, morning)
    parent = next(p for p in store.posts() if p['kind'] == 'announcement')
    claim(store, parent, morning)
    frozen = store.rows("SELECT * FROM posts WHERE status='published'")
    tomorrow = morning + timedelta(days=1)
    # The source URL now advertises a different occurrence; the old frozen card stays old.
    store.upsert({**item, 'start': (parse_date(item['start']) + timedelta(days=1)).isoformat(),
                  'end': (parse_date(item['end']) + timedelta(days=1)).isoformat()}, tomorrow.isoformat())
    assets = {parent['id']: {'feed': [], 'story': [f"media/{parent['id']}/story-1.jpg"]}}
    adapter = api()
    result = publish_one(store, tomorrow, 'https://example.org/', assets, story=True,
                         adapter=adapter, target_id=digest(parent['id'] + ':story:0'), paired_story=True)
    assert result['status'] == 'empty'
    adapter.container.assert_not_called()
    assert store.rows("SELECT * FROM posts WHERE status='published'") == frozen


def test_declined_yoga_is_excluded_from_individual_cards_and_calendar(store, event, at):
    yoga = deepcopy(event)
    yoga.update(title='Canan Tutal İle Hatha Yoga', category='sport',
                start=(at + timedelta(days=2)).isoformat(), end=(at + timedelta(days=2, hours=1)).isoformat())
    key, _ = store.upsert(yoga, at.isoformat())
    prepare(store, at)
    assert owner_exclusion(yoga) == 'owner_excluded'
    assert not store.posts()
    # An unrelated yoga/sport class is not silently removed from the whole policy.
    assert owner_exclusion({**yoga, 'title': 'Başka bir eğitmenle yoga'}) is None
    assert store.items()[0]['id'] == key


def test_old_declined_yoga_claim_stays_immutable_but_no_new_story_is_created(store, event, at):
    event.update(title='Canan Tutal ile Hatha Yoga')
    key, _ = store.upsert(event, at.isoformat())
    parent = {'id': digest('old-yoga-parent'), 'item_id': key, 'kind': 'announcement', 'revision': 1,
              'title': event['title'], 'caption': 'Frozen caption', 'source_urls': event['sources'],
              'due_at': at.isoformat(), 'created_at': at.isoformat(), 'published_at': at.isoformat(),
              'slides': [{'title': event['title'], 'body': 'Frozen event card'}]}
    store.queue(parent)
    with store.db: store.db.execute("UPDATE posts SET status='published'")
    before = store.rows("SELECT * FROM posts WHERE status='published'")
    adapter = api()
    assets = {parent['id']: {'feed': [], 'story': [f"media/{parent['id']}/story-1.jpg"]}}
    assert publish_one(store, at, 'https://example.org/', assets, story=True, adapter=adapter)['status'] == 'rate_limited'
    adapter.container.assert_not_called()
    assert store.rows("SELECT * FROM posts WHERE status='published'") == before
