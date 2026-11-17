"""Owner decision, 17 Nov 2026: the recurring tile ("çini") workshops are never shared again."""
import json
import re
from copy import deepcopy
from datetime import timedelta

import pytest

from seferihisar import publication_policy
from seferihisar.domain import digest
from seferihisar.facebook import current_post
from seferihisar.instagram import prepare_story_jobs, publish_one
from seferihisar.publication_policy import owner_exclusion, post_reason
from seferihisar.schedule import prepare
from seferihisar.timeliness import publication_reason
from test_automatic_publication import api


def cini(event, at, title='Ayşin Koruk ile Çini Atölyeleri (Yetişkin)', days=2):
    item = deepcopy(event)
    url = 'https://biletinial.com/tr-tr/egitim/aysin-koruk-ile-cini-atolyeleri-yetiskin'
    item.update(identity=url, url=url, sources=[url], title=title, category='culture',
                location='Bademler Sanat Köyü · Urla', description='Etkinlik duyurusu. ' + title,
                start=(at + timedelta(days=days)).replace(hour=14).isoformat(),
                end=(at + timedelta(days=days)).replace(hour=17).isoformat())
    return item


def other(event, at):
    return {**event, 'start': (at + timedelta(days=3)).replace(hour=20).isoformat(),
            'end': (at + timedelta(days=3)).replace(hour=22).isoformat()}


@pytest.mark.parametrize('title', [
    'Ayşin Koruk ile Çini Atölyeleri (Yetişkin)',
    'Ayşin Koruk ile Ebeveyn - Çocuk Çini Etkinliği',
    'Ebeveyn & Çocuk Çini Etkinliği',
    'Ayşin Koruk İle Çocuk Çini Etkinliği',
    'ÇİNİ ATÖLYESİ',
    'ÇINI ATÖLYESİ',
    'cini atolyesi',
    "Bademler'de Çini'ye giriş",
])
def test_every_spelling_of_the_word_is_excluded(event, at, title):
    item = cini(event, at, title)
    assert owner_exclusion(item) == 'owner_excluded'
    assert publication_reason(item, at) == 'owner_excluded'


@pytest.mark.parametrize('title', [
    'Çinili Köşk gezisi',
    'Çinicilik tarihi söyleşisi',
    'Hint ve Çin kültürü söyleşisi',
    'Seramik ve ebru atölyesi',
])
def test_other_words_are_not_caught(event, at, title):
    assert owner_exclusion(cini(event, at, title)) is None


def test_news_articles_and_the_other_owner_rule_are_unchanged(event, at):
    news = {'kind': 'news', 'title': 'Seferihisar’da çini sergisi açıldı'}
    assert owner_exclusion(news) is None
    assert owner_exclusion({**event, 'title': 'Canan Tutal İle Hatha Yoga'}) == 'owner_excluded'
    assert owner_exclusion(event) is None


def test_no_announcement_reminder_or_digest_row_is_prepared(store, event, at):
    key, _ = store.upsert(cini(event, at), at.isoformat())
    kept, _ = store.upsert(other(event, at), at.isoformat())
    prepare(store, at)
    posts = store.posts()
    assert posts and not [p for p in posts if p.get('item_id') == key]
    digests = [p for p in posts if p['kind'] in ('weekly', 'monthly')]
    assert {p['kind'] for p in digests} == {'weekly', 'monthly'}
    for post in digests:
        assert post['status'] == 'prepared' and post['event_ids'] == [kept]
        assert not any(publication_policy.CINI.search(publication_policy.normalized(s['title']))
                       for s in post['slides'])
        assert 'Çini' not in post['caption']


def queued_before_rule(store, event, at, monkeypatch):
    """Cards and digests prepared while the rule did not exist yet."""
    with monkeypatch.context() as patch:
        patch.setattr(publication_policy, 'CINI', re.compile(r'(?!)'))
        key, _ = store.upsert(cini(event, at), at.isoformat())
        kept, _ = store.upsert(other(event, at), at.isoformat())
        prepare(store, at)
        queued = [p for p in store.posts() if p.get('item_id') == key]
        assert {p['kind'] for p in queued} == {'announcement', 'reminder_3d'}
        assert all(p['status'] == 'prepared' for p in queued)
        weekly = next(p for p in store.posts() if p['kind'] == 'weekly')
        assert key in weekly['event_ids'] and weekly['status'] == 'prepared'
    # Every queued card is already due.
    with store.db:
        for row in store.rows('SELECT id,payload FROM posts'):
            payload = json.loads(row['payload'])
            payload['due_at'] = (at - timedelta(minutes=10)).isoformat()
            store.db.execute('UPDATE posts SET due_at=?,payload=? WHERE id=?',
                             (payload['due_at'], json.dumps(payload, ensure_ascii=False), row['id']))
    return key, kept


def test_digest_row_drops_out_when_the_edition_is_rebuilt(store, event, at, monkeypatch):
    key, kept = queued_before_rule(store, event, at, monkeypatch)
    later = at + timedelta(minutes=5)
    # Publication time: the queued edition still lists the event, so it stops.
    prepare(store, later, refresh_digests=False)
    for kind in ('weekly', 'monthly'):
        stale = next(p for p in store.posts() if p['kind'] == kind)
        assert stale['status'] == 'blocked_source' and key in stale['event_ids']
        assert post_reason(store, stale, later) == 'owner_excluded'
    # Research time: the same edition comes back without the row.
    prepare(store, later)
    for kind in ('weekly', 'monthly'):
        fresh = next(p for p in store.posts() if p['kind'] == kind)
        assert fresh['status'] == 'prepared' and fresh['event_ids'] == [kept]
        assert len(fresh['slides']) == 2 and post_reason(store, fresh, later) is None


def test_prepared_card_and_story_are_stopped_at_publication(store, event, at, monkeypatch):
    key, _ = queued_before_rule(store, event, at, monkeypatch)
    queued = [p for p in store.posts() if p.get('item_id') == key]
    later = at + timedelta(minutes=5)
    for post in queued:
        assert post_reason(store, post, later) == 'owner_excluded'
        assert current_post(store, post, later) is False
    assets = {p['id']: {'feed': [f"media/{p['id']}/feed-1.jpg"], 'story': [f"media/{p['id']}/story-1.jpg"]}
              for p in queued}
    adapter = api()
    for target in queued:
        result = publish_one(store, later, 'https://example.org/', assets, adapter=adapter, target_id=target['id'])
        assert result['status'] != 'published'
        result = publish_one(store, later, 'https://example.org/', assets, story=True, adapter=adapter,
                             target_id=digest(target['id'] + ':story:0'))
        assert result['status'] != 'published'
    adapter.container.assert_not_called()
    prepare_story_jobs(store, assets)
    for post in store.posts():
        if post.get('item_id') == key:
            assert post['status'] in ('blocked_source', 'superseded')
            assert post_reason(store, post, later) == 'owner_excluded'
