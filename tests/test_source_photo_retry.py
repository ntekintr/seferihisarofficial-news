"""Bad pictures do not consume later runs; cooldowns remain bounded public data."""
from contextlib import closing
from datetime import timedelta
import json

import pytest

from test_source_photo_queue import item, manager, page, AT
from seferihisar.security import validate_state
from seferihisar.source_photo_retry import active, remember, prune, MAX_ROWS
from seferihisar.store import Store
from seferihisar.visual_match import MatchRejected


def test_persisted_rejections_leave_next_run_for_later_photograph(tmp_path, monkeypatch):
    monkeypatch.setattr('seferihisar.source_photos.MAX_READS',2)
    path=tmp_path/'state.sqlite'
    with closing(Store(path)) as store:
        rows=[item(store,n) for n in range(3)]
        photos,fetcher=manager(store,tmp_path,monkeypatch)
        fetcher.get.side_effect=[(page(row,photo=True),row['url']) for row in rows]
        def reject(*args):raise MatchRejected('Private diagnostic must not persist')
        monkeypatch.setattr('seferihisar.source_photos.validate_news_photo',reject)
        monkeypatch.setattr('seferihisar.visual_match.validate_headline_photo',reject)
        assert all(photos.image(row) is None for row in rows)
        assert photos.reads==2
        checks=store.rows('SELECT * FROM source_photo_retries')
        assert len(checks)==2 and 'Private' not in json.dumps(checks)
        validate_state(path)
    with closing(Store(path)) as store:
        photos,fetcher=manager(store,tmp_path,monkeypatch)
        photos.at=AT+timedelta(minutes=30)
        fetcher.get.return_value=(page(rows[2],photo=True),rows[2]['url'])
        assert photos.image(rows[0]) is None and photos.image(rows[1]) is None
        assert photos.image(rows[2]) is not None
        assert photos.stats['cooldown']==2
        assert photos.reads==fetcher.image.call_count==fetcher.get.call_count==1
        assert store.posts()==[]
        validate_state(path)


@pytest.mark.parametrize('stage,minutes', [('visual_subject',360),('source_binding',360),
    ('source_read',60),('image_read',60),('checker_unavailable',15)])
def test_cooldowns_expire_and_new_revision_is_not_suppressed(tmp_path,stage,minutes):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        row=item(store,1)
        remember(store,row,AT,stage)
        assert active(store,row,AT+timedelta(minutes=minutes-1))
        assert not active(store,row,AT+timedelta(minutes=minutes))
        assert not active(store,{**row,'revision':row['revision']+1},AT)
        assert not active(store,row,AT-timedelta(hours=1))
        validate_state(store.path)


def test_retry_cache_is_bounded_and_pruned_without_touching_publications(tmp_path):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        for n in range(MAX_ROWS+3):
            remember(store,{'id':format(n,'024x'),'revision':1},AT+timedelta(seconds=n),'source_binding')
        rows=store.rows('SELECT * FROM source_photo_retries')
        assert len(rows)==MAX_ROWS
        assert format(0,'024x') not in {r['item_id'] for r in rows}
        keep=rows[-1]['item_id']
        prune(store,{keep})
        assert len(store.rows('SELECT * FROM source_photo_retries'))==1
        assert store.posts()==[]
        validate_state(store.path)


@pytest.mark.parametrize('change', ['id','stage','revision','naive','interval'])
def test_state_writer_rejects_invalid_retry_records(tmp_path,change):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        row=item(store,1);remember(store,row,AT,'visual_subject')
        field,value={'id':('item_id','invalid'),'stage':('stage','arbitrary provider text'),
            'revision':('revision',0),'naive':('checked_at','2026-10-26T08:40:00'),
            'interval':('retry_at',(AT+timedelta(days=99)).isoformat())}[change]
        with store.db:store.db.execute('UPDATE source_photo_retries SET '+field+'=?',(value,))
        with pytest.raises(ValueError):validate_state(store.path)
