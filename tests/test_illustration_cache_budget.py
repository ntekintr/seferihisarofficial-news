import io
from datetime import datetime, timedelta, timezone
import pytest
from PIL import Image
from seferihisar.store import Store
from seferihisar.illustrations import Illustrator
from seferihisar.domain import digest

@pytest.mark.parametrize("limit", ["count", "bytes"])
def test_old_frozen_images_reserve_capacity_before_recent_drafts(tmp_path, monkeypatch, limit):
    store=Store(tmp_path/'state.sqlite')
    at=datetime(2026,10,29,tzinfo=timezone.utc)
    output=io.BytesIO();Image.new('RGB',(768,768),'blue').save(output,format='JPEG')
    data=output.getvalue(); item=digest('item'); frozen=digest('frozen')
    for index,key in enumerate([frozen,digest('new1'),digest('new2')]):
        store.db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',(key,item,'ready',data,1,at.isoformat(),(at+timedelta(seconds=index)).isoformat()))
    store.db.commit()
    original=tuple(store.db.execute('SELECT * FROM illustrations WHERE id=?',(frozen,)).fetchone())
    generator=Illustrator(store,at,tmp_path/'images',demo=True)
    monkeypatch.setattr(generator,'_frozen_keys',lambda:{frozen})
    monkeypatch.setattr('seferihisar.illustrations.MAX_CACHED_IMAGES',2 if limit=='count' else 80)
    monkeypatch.setattr('seferihisar.illustrations.MAX_CACHE_BYTES',len(data)*2 if limit=='bytes' else 12*1024*1024)
    generator.prune({item})
    assert store.db.execute("SELECT count(*) FROM illustrations WHERE status='ready'").fetchone()[0]==2
    assert tuple(store.db.execute('SELECT * FROM illustrations WHERE id=?',(frozen,)).fetchone())==original
    assert store.db.execute('SELECT id FROM illustrations WHERE id=?',(digest('new2'),)).fetchone()
    store.close()
