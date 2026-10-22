from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from seferihisar.domain import digest, parse_date
from seferihisar.illustrations import Illustrator, image_key
from seferihisar.owner_curated import matches, image_bytes, SUBJECT, TITLE, URL, validate
from seferihisar.owner_requests import pending
from seferihisar.schedule import prepare
from seferihisar.visual_subject import subject

AT = parse_date('2026-10-22T11:30:00+03:00')


def article():
    return {'kind':'news','title':TITLE,'url':URL,'identity':URL.rstrip('/'),
            'source_id':'toplumsal-mandalina-review','source_name':'Toplumsal Haber',
            'category':'food','sources':[URL],'published_at':'2026-10-22T10:14:00+03:00',
            'description':'Seferihisar Belediyesi, satsuma mandalinasının kabuklarından kedi-köpek maması, özgün bileşenlerinden ise aromaterapi yağları üretmek için proje hazırlıyor. Amaç, mandalinanın ekonomik değerini artırarak üreticilere ek fayda sağlamak.'}


def test_exact_source_and_exact_pixels_only():
    item=article()
    assert matches(item) and subject(item)==SUBJECT
    for key,value in [('url',URL+'other'),('description','Başka bir haber.'),('source_id','other'),('title','Üretim başladı')]:
        assert not matches({**item,key:value})
        assert subject({**item,key:value}) is None
    data=image_bytes();validate(data)
    with pytest.raises(ValueError):validate(data[:-1])
    from seferihisar.editor import verify
    assert verify({**item,'description':'Güncellenmiş farklı bir metin.'},
                  {'id':'toplumsal-mandalina-review'},AT)=='reviewed_article_changed'


def test_curated_picture_uses_normal_ocr_and_no_provider_or_daily_quota(store,tmp_path,monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    item=article();key,_=store.upsert(item,AT.isoformat());item=next(i for i in store.items() if i['id']==key)
    generator=Illustrator(store,AT,tmp_path)
    lettering=Mock();monkeypatch.setattr(generator,'check_image',lettering)
    provider=Mock(side_effect=AssertionError('No provider request allowed'))
    monkeypatch.setattr(generator,'generate',provider)
    assert generator.image(item,True).is_file()
    lettering.assert_called();provider.assert_not_called()
    assert store.rows('SELECT * FROM illustration_days')==[]
    assert store.rows('SELECT status FROM illustrations WHERE id=?',(image_key(item),))==[{'status':'ready'}]


def test_owner_request_identity_expiry_and_completed_pair_are_finite(store):
    store.upsert(article(),AT.isoformat());prepare(store,AT)
    request=pending(store,AT)
    assert request['post_id']=='ec40504d1cdce992de9d3d65'
    assert request['requires_image'] is True
    assert pending(store,AT+timedelta(days=3)) is None
    parent=next(p for p in store.posts() if p['id']==request['post_id'])
    with store.db:store.db.execute("UPDATE posts SET status='published' WHERE id=?",(parent['id'],))
    store.queue({**parent,'id':digest(parent['id']+':story:0'),'publish_format':'story','parent_post_id':parent['id']})
    with store.db:store.db.execute("UPDATE posts SET status='published' WHERE id=?",(digest(parent['id']+':story:0'),))
    assert pending(store,AT) is None


def test_expired_one_article_reader_does_not_make_another_network_request(monkeypatch):
    from seferihisar.collect import collect_source
    fetcher=Mock()
    monkeypatch.setattr('seferihisar.collect.now',lambda:AT)
    assert collect_source({'requested_until':(AT-timedelta(seconds=1)).isoformat()},fetcher,[])==([],[],[])
    fetcher.get.assert_not_called()
