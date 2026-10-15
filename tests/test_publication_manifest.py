"""The publisher consumes data.json, not the render function's return value."""
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from seferihisar.domain import digest
from seferihisar.instagram import publish_automatic
from seferihisar.pipeline import export


@pytest.mark.parametrize('history', ['expired', 'superseded', 'story', 'prepared'])
def test_manifest_keeps_oldest_due_media_after_large_history(
        store, event, at, tmp_path, monkeypatch, history):
    at = at.replace(hour=15, minute=5)
    # These synthetic jobs are news. An event fixture would legitimately add
    # new event reminders at publish-time, outside this manifest regression.
    event = {k: event[k] for k in ('title', 'description', 'url', 'sources', 'source_id', 'source_name')}
    event.update(kind='news', category='public', published_at=at.isoformat())
    item_id, _ = store.upsert(event, at.isoformat())
    source_config = json.loads(Path('config/sources.json').read_text())
    monkeypatch.delenv('ILLUSTRATIONS_ENABLED', raising=False)

    def queue(label, due, status='prepared', **fields):
        post = {'id': digest(label), 'item_id': item_id, 'revision': 1,
                'kind': 'news', 'due_at': due.isoformat(), 'created_at': at.isoformat(),
                'title': 'Seferihisar duyurusu', 'caption': 'Kaynak: Belediye\n' + event['url'],
                'category': 'public', 'source_urls': [event['url']],
                'slides': [{'title': 'Seferihisar duyurusu', 'body': 'Güncel duyuru.'}],
                **fields}
        store.queue(post)
        with store.db:
            store.db.execute('UPDATE posts SET status=? WHERE id=?', (status, post['id']))
        return post['id']

    target = queue('oldest-due', at - timedelta(minutes=10))
    frozen = queue('previously-published', at - timedelta(days=1), 'published',
                   published_at=(at - timedelta(days=1)).isoformat())
    frozen_before = store.rows('SELECT * FROM posts WHERE id=?', (frozen,))[0]
    history_ids = set()
    for index in range(105):
        fields = {'publish_format': 'story', 'parent_post_id': target} if history == 'story' else {}
        history_ids.add(queue('history-' + str(index), at + timedelta(minutes=index + 1),
                              'prepared' if history == 'story' else history, **fields))

    # Small local JPEGs keep the large-queue test fast; no provider or real
    # social account is contacted. Real card layout has separate render tests.
    def render(post, directory, illustrations):
        assets = {}
        for kind in ('feed', 'story'):
            relative = f"media/{post['id']}/{kind}-1.jpg"
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGB', (8, 8), '#123456').save(path, 'JPEG')
            assets[kind] = [relative]
        return assets

    monkeypatch.setattr('seferihisar.pipeline.render_post', render)
    directory = tmp_path / 'public'
    rendered = export(store, directory, source_config, at)
    snapshot = json.loads((directory / 'data.json').read_text(encoding='utf-8'))
    manifest = {p['id']: p['assets'] for p in snapshot['posts']}
    assert manifest[target] == rendered[target]
    assert manifest[frozen] == rendered[frozen]
    assert all((directory / path).is_file() for assets in manifest.values()
               for paths in assets.values() for path in paths)
    assert store.rows('SELECT * FROM posts WHERE id=?', (frozen,))[0] == frozen_before
    if history == 'prepared':
        assert history_ids <= manifest.keys()  # Active queues may exceed 100 parents too.
    else:
        assert not history_ids & manifest.keys()

    api = Mock()
    api.enabled.return_value = True
    api.account = '1234'
    api.session.head.return_value = SimpleNamespace(
        status_code=200, headers={'Content-Type': 'image/jpeg'})
    api.container.return_value = 'synthetic-container'
    api.call.return_value = {'id': 'synthetic-media'}
    result = publish_automatic(store, at, 'https://example.org/', manifest, adapter=api)
    assert result == {'status': 'complete', 'feed': 'published', 'story': 'published'}
    assert api.container.call_count == 2
    assert api.container.call_args_list[0].args[0] == [
        'https://example.org/' + manifest[target]['feed'][0]]
    assert store.rows('SELECT * FROM posts WHERE id=?', (frozen,))[0] == frozen_before
