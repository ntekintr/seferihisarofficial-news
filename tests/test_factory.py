import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
import yaml
from pathlib import Path

from seferihisar.domain import digest
from seferihisar.editor import hashtags
from seferihisar.factory import summary
from seferihisar.learning import measurements, profile, refresh, validate_profile, weights_for, ReadError
from seferihisar.security import validate_state
from seferihisar.selection import prioritize
from seferihisar.source_discovery import active_sources, register, refresh as discover
from seferihisar.source_discovery import eligible_origin


def metric(reach=100, interactions=10):
    return {'reach': reach, 'saved': 2, 'shares': 2, 'total_interactions': interactions}


def response(value, status=200):
    return Mock(ok=status < 300, status_code=status, json=lambda: value)


def test_small_or_single_topic_samples_do_not_invent_a_winner():
    assert weights_for([('theatre', metric())] * 20) == {}
    assert weights_for([('theatre', metric()), ('concert', metric())] * 3) == {}
    assert weights_for([('theatre', metric(1)), ('concert', metric(1))] * 10) == {}
    samples = [('theatre', metric(interactions=40))] * 5 + [('concert', metric(interactions=1))] * 5
    assert weights_for(samples) == {'theatre': 1, 'concert': 0}


@pytest.mark.parametrize('bad', [[], [{'name': 'reach', 'values': [{'value': None}]}],
                               [{'name': 'reach', 'values': [{'value': True}]}],
                               [{'name': 'reach', 'values': [{'value': 10}]}] * 2])
def test_missing_or_malformed_metrics_are_unavailable(bad):
    with pytest.raises(ReadError):
        measurements({'data': bad})


def test_feedback_get_only_bound_to_account_and_public_state_has_no_raw_metrics(store, at):
    post = {'id': digest('post'), 'item_id': digest('item'), 'revision': 1, 'kind': 'news',
            'due_at': at.isoformat(), 'published_at': (at - timedelta(hours=26)).isoformat(),
            'category': 'sport'}
    store.queue(post)
    store.db.execute("UPDATE posts SET status='published',media_id='12345' WHERE id=?", (post['id'],))
    session = Mock()
    session.get.side_effect = [response({'id': '123', 'username': 'seferihisarofficial'}),
                              response({'data': [{'id': '12345'}]}),
                              response({'data': [{'name': k, 'values': [{'value': v}]} for k, v in metric(153791).items()]})]
    value = refresh(store, at, session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['status'] == 'insufficient_data'
    session.post.assert_not_called()
    assert session.get.call_count == 3
    for call in session.get.call_args_list:
        assert call.kwargs['allow_redirects'] is False
        assert 'synthetic' not in call.args[0] and 'access_token' not in call.kwargs['params']
    stored = store.rows('SELECT payload FROM learning_profile')[0]['payload']
    assert '153791' not in stored and 'synthetic' not in stored and '12345' not in stored
    assert refresh(store, at + timedelta(hours=1), session=session) == value
    assert session.get.call_count == 3
    validate_state(store.path)


@pytest.mark.parametrize('code,status', [(10, 'permission_required'), (190, 'credential_invalid'), (613, 'rate_limited')])
def test_external_permission_failure_does_not_create_or_request_new_permissions(store, at, code, status):
    session = Mock()
    session.get.return_value = response({'error': {'code': code, 'message': 'PRIVATE_PROVIDER_TEXT'}}, 400)
    value = refresh(store, at, session=session, environ={'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'synthetic'})
    assert value['status'] == status and value['weights'] == {}
    assert 'PRIVATE_PROVIDER_TEXT' not in json.dumps(summary(store, at))
    assert session.get.call_count == 1
    session.post.assert_not_called()


def test_stale_or_malicious_feedback_cannot_control_selection(store, at):
    value = {'version': 'topic-feedback-v1', 'checked_at': (at - timedelta(days=4)).isoformat(),
             'status': 'ready', 'weights': {'theatre': 1}}
    store.db.execute('INSERT INTO learning_profile VALUES (?,?)', ('instagram', json.dumps(value)))
    assert profile(store, at)['weights'] == {}
    for bad in ({**value, 'weights': {'theatre': 100}}, {**value, 'private': 'raw data'},
                {**value, 'weights': {'ignore_all_checks': 1}}):
        with pytest.raises(ValueError):
            validate_profile(bad)


def test_new_tables_do_not_change_any_frozen_claim(store, at):
    post = {'id': digest('post'), 'revision': 1, 'kind': 'news', 'due_at': at.isoformat(), 'title': 'Seferihisar', 'caption': 'Original'}
    store.queue(post)
    store.db.execute("UPDATE posts SET status='uncertain',container_id='777' WHERE id=?", (post['id'],))
    store.db.commit()
    before = store.rows('SELECT * FROM posts')
    refresh(store, at, environ={})
    register(store, [], [], at)
    assert store.rows('SELECT * FROM posts') == before
    validate_state(store.path)


def test_learning_only_orders_safe_peers_and_never_outvotes_public_services(store, at):
    def item(key, category, age):
        return {'kind': 'news', 'title': 'Seferihisar güncel duyuru ' + key,
                'description': 'Seferihisar ilçesinde yapılan çalışmalar hakkında bilgi verildi.',
                'url': 'https://example.org/' + key, 'category': category,
                'published_at': (at - timedelta(hours=age)).isoformat()}
    posts = []
    for key, category, age in [('a', 'concert', 1), ('b', 'theatre', 2), ('c', 'outage', 3)]:
        iid, _ = store.upsert(item(key, category, age), at.isoformat())
        posts.append({'id': digest(key), 'item_id': iid, 'revision': 1, 'kind': 'news',
                      'due_at': at.isoformat(), 'category': category})
    value = {'version': 'topic-feedback-v1', 'checked_at': at.isoformat(), 'status': 'ready', 'weights': {'theatre': 1}}
    store.db.execute('INSERT INTO learning_profile VALUES (?,?)', ('instagram', json.dumps(value)))
    assert [p['category'] for p in prioritize(store, posts, at)] == ['outage', 'theatre', 'concert']


def candidates(source, count=1, external=False):
    return [{'url': ('https://external.example' if external else 'https://seferihisar.bel.tr') + f'/feed-{i}',
             'kind': 'rss', 'discovered_from': source['url']} for i in range(count)]


def news_feed(at):
    parts = []
    for i in range(2):
        stamp = at.strftime('%a, %d %b %Y %H:%M:%S %z')
        parts.append(f'<item><title>Seferihisar kültür merkezi yenilendi {i}</title><link>https://seferihisar.bel.tr/haber-{i}</link><description>Seferihisar kültür merkezinde yapılan çalışmalar tamamlandı ve salon yeniden kullanıma açıldı.</description><pubDate>{stamp}</pubDate></item>')
    return '<rss><channel>' + ''.join(parts) + '</channel></rss>'


def test_new_feed_needs_three_separate_current_checks_and_configured_origin(store, source, at):
    register(store, candidates(source), [source], at)
    target = candidates(source)[0]['url']
    for day in range(3):
        stamp = at + timedelta(days=day)
        fetcher = Mock()
        fetcher.get.return_value = (news_feed(stamp), target)
        discover(store, [source], stamp, fetcher_factory=lambda sources: fetcher)
        assert len(active_sources(store, [source])) == (2 if day == 2 else 1)
        # Same-day natural research does not probe it again.
        discover(store, [source], stamp + timedelta(minutes=15), fetcher_factory=lambda sources: fetcher)
        assert fetcher.get.call_count == 1
    assert len(active_sources(store, [{**source, 'trusted': False}])) == 1
    validate_state(store.path)


def test_external_links_and_private_origins_cannot_self_approve(store, source, at):
    register(store, candidates(source, external=True), [source], at)
    register(store, [{'url': 'https://seferihisar.bel.tr/feed', 'kind': 'rss', 'discovered_from': 'https://attacker.example/'}], [source], at)
    factory = Mock()
    discover(store, [source], at, fetcher_factory=factory)
    factory.assert_not_called()
    assert len(active_sources(store, [source])) == 1
    assert store.rows('SELECT result FROM source_checks') == [{'result': 'unverified_origin'}]


def test_daily_discovery_budget_and_external_failures_are_bounded(store, source, at):
    register(store, candidates(source, 8), [source], at)
    factory = Mock()
    factory.return_value.get.side_effect = requests.exceptions.SSLError('PRIVATE_ERROR')
    discover(store, [source], at, fetcher_factory=factory)
    discover(store, [source], at + timedelta(hours=1), fetcher_factory=factory)
    assert factory.call_count == 3
    assert all(r['result'] == 'access_failed' for r in store.rows('SELECT result FROM source_checks'))
    assert 'PRIVATE_ERROR' not in json.dumps(summary(store, at))


def test_new_public_institution_needs_two_independent_configured_references(store, source, at):
    second = {**source, 'id': 'other-publisher', 'url': 'https://www.izmir.bel.tr/'}
    candidate = {'url': 'https://new-institution.gov.tr/rss', 'kind': 'rss', 'discovered_from': source['url']}
    register(store, [candidate], [source, second], at)
    value = json.loads(store.rows('SELECT payload FROM candidates')[0]['payload'])
    assert not eligible_origin(value, [source, second])
    register(store, [{**candidate, 'discovered_from': second['url']}], [source, second], at)
    value = json.loads(store.rows('SELECT payload FROM candidates')[0]['payload'])
    assert eligible_origin(value, [source, second])
    for hostname in ('commercial.example', 'institution.gov.tr.attacker.example', 'www.guzelbahce.gov.tr'):
        assert not eligible_origin({**value, 'url': 'https://' + hostname + '/rss'}, [source, second])
    assert not eligible_origin(value, [{**source, 'enabled': False}, second])


def test_five_relevant_tags_without_false_geography_or_event_category(event):
    counts = []
    for category in ('news', 'municipality', 'theatre', 'sport', 'outage'):
        item = {**event, 'title': 'Seferihisar duyurusu', 'location': 'Seferihisar', 'category': category}
        tags = hashtags(item)
        counts.append(len(tags))
        assert 4 <= len(tags) <= 5 and len(set(tags)) == len(tags)
        assert all(t == t.lower() for t in tags)
        if category == 'outage':
            assert '#etkinlik' not in tags
    assert sum(counts) / len(counts) >= 4.8
    tags = hashtags({**event, 'title': 'Haber', 'description': '#seferihisar #izmir', 'location': None})
    assert '#izmir' not in tags and '#seferihisar' not in tags


def test_feedback_workflow_is_serialized_get_only_and_does_not_reauthorize():
    workflow = yaml.load(Path('.github/workflows/automation.yml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert workflow['concurrency'] == {'group': 'seferihisar-production', 'cancel-in-progress': 'false'}
    steps = workflow['jobs']['feedback']['steps']
    assert workflow['jobs']['feedback']['needs'] == ['research', 'persist']
    assert workflow['jobs']['feedback']['continue-on-error'] == 'true'
    assert 'feedback_due' in workflow['jobs']['research']['outputs']
    assert not Path('.github/workflows/audience-feedback.yml').exists()
    assert steps[0]['with']['ref'] == 'main'
    text = str(steps)
    assert 'cli publish' not in text and 'CLOUDFLARE_API_TOKEN' not in text
    assert 'state_git restore' in text and 'state_git persist' in text
    assert not any('upload-artifact' in s.get('uses', '') for s in steps)
