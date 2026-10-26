"""Recovery must work with a full quota, without weakening image or claim gates."""
from contextlib import closing
from datetime import timedelta
import hashlib
import json
from unittest.mock import Mock

import pytest

from seferihisar import editorial_stock
from seferihisar.domain import digest,parse_date
from seferihisar.illustrations import Illustrator,image_key,scene_brief
from seferihisar.image_safety import validate_jpeg,IllustrationTextRejected
from seferihisar.security import validate_state
from seferihisar.store import Store
from seferihisar.visual_match import MatchRejected,MatchUnavailable
from seferihisar.visual_subject import subject

AT=parse_date('2026-10-26T11:30:00+03:00')


def item(number=1,category='theatre',title='Örnek tiyatro gösterisi'):
    return {'id':digest('stock-'+str(number)),'revision':1,'kind':'event',
            'category':category,'title':title}


def manager(store,tmp_path,monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED','true')
    monkeypatch.delenv('CLOUDFLARE_API_TOKEN',raising=False)
    monkeypatch.delenv('CLOUDFLARE_ACCOUNT_ID',raising=False)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available',lambda:True)
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',validate_jpeg)
    monkeypatch.setattr('seferihisar.illustrations.validate_match',lambda *args:None)
    session=Mock();session.post.side_effect=AssertionError('Stock tried to call image provider')
    return Illustrator(store,AT,tmp_path/'images',session=session)


def test_failed_two_attempts_recovers_even_with_full_daily_quota(tmp_path,monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        row=item();key=image_key(row)
        store.db.execute('INSERT INTO illustrations VALUES(?,?,?,NULL,?,?,?)',
            (key,row['id'],'failed',2,(AT+timedelta(days=1)).isoformat(),AT.isoformat()))
        store.db.execute('INSERT INTO illustration_days VALUES(?,20)',('2026-10-26',));store.db.commit()
        generator=manager(store,tmp_path,monkeypatch)
        assert generator.image(row,True)
        assert generator.stats['stock_reused']==1 and generator.stats['attempted']==generator.stats['generated']==0
        assert store.rows('SELECT attempts FROM illustration_days')==[{'attempts':20}]
        assert store.rows('SELECT status,attempts FROM illustrations')==[{'status':'ready','attempts':2}]
        validate_state(store.path);generator.session.post.assert_not_called()


def test_stock_works_after_runner_restart_without_credentials_or_daily_claim(tmp_path,monkeypatch):
    path=tmp_path/'state.sqlite';row=item()
    with closing(Store(path)) as store:
        generator=manager(store,tmp_path,monkeypatch)
        before=generator.image(row,True).read_bytes()
        assert store.rows('SELECT attempts FROM illustrations')==[{'attempts':0}]
        assert not store.rows('SELECT * FROM illustration_days')
        validate_state(path)
    with closing(Store(path)) as store:
        fresh=manager(store,tmp_path,monkeypatch)
        assert fresh.image(row,False).read_bytes()==before
        assert fresh.stats['reused']==1 and fresh.stats['generated']==0


@pytest.mark.parametrize('failure',[IllustrationTextRejected,MatchRejected,MatchUnavailable])
def test_failed_review_never_becomes_a_bound_image(tmp_path,monkeypatch,failure):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        generator=manager(store,tmp_path,monkeypatch)
        field='validate_text_free_illustration' if failure is IllustrationTextRejected else 'validate_match'
        monkeypatch.setattr('seferihisar.illustrations.'+field,Mock(side_effect=failure('Rejected')))
        assert generator.image(item(),True) is None
        assert not store.rows('SELECT * FROM illustrations')
        generator.session.post.assert_not_called()


def test_unknown_subject_or_different_brief_never_receives_related_stock(tmp_path,monkeypatch):
    assert editorial_stock.stock_image('weather_sky','A heavy rain scene') is None
    assert editorial_stock.stock_image('meeting',scene_brief(item())) is None
    with closing(Store(tmp_path/'state.sqlite')) as store:
        generator=manager(store,tmp_path,monkeypatch)
        assert generator.image(item(category='event',title='Belirsiz etkinlik'),True) is None
        assert not store.rows('SELECT * FROM illustrations')


def test_changed_pixels_or_brief_manifest_is_not_accepted(tmp_path,monkeypatch):
    directory=editorial_stock.DIRECTORY
    manifest=json.loads((directory/'manifest.json').read_text())
    row=next(r for r in manifest['scenes'] if r['subject']=='theatre')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    (tmp_path/row['file']).write_bytes((directory/row['file']).read_bytes()+b'changed')
    monkeypatch.setattr(editorial_stock,'DIRECTORY',tmp_path)
    assert editorial_stock.stock_image('theatre',scene_brief(item())) is None


@pytest.mark.parametrize('status',['published','publishing','uncertain'])
def test_stock_never_replaces_any_frozen_binding(tmp_path,monkeypatch,status):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        row=item();key=image_key(row)
        store.queue({'id':digest('post'),'item_id':row['id'],'revision':1,'kind':'announcement',
                     'due_at':AT.isoformat(),'illustration_keys':{'0':key}})
        store.db.execute('UPDATE posts SET status=?',(status,));store.db.commit()
        before=store.rows('SELECT * FROM posts')
        generator=manager(store,tmp_path,monkeypatch)
        assert generator.image(row,True) is None
        assert store.rows('SELECT * FROM posts')==before
        assert not store.rows('SELECT * FROM illustrations')
        generator.session.post.assert_not_called()


def test_source_photo_assignment_still_takes_precedence_over_stock(tmp_path,monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        generator=manager(store,tmp_path,monkeypatch);row=item()
        post={'status':'prepared','kind':'announcement','item_id':row['id'],'revision':1,'slides':[{}]}
        assert generator.for_post(post,{row['id']:row},skip_indices={0})=={}
        assert not store.rows('SELECT * FROM illustrations')


def test_zero_attempts_allowed_only_for_ready_local_scene(tmp_path,monkeypatch):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        generator=manager(store,tmp_path,monkeypatch);assert generator.image(item(),True)
        validate_state(store.path)
        store.db.execute("UPDATE illustrations SET status='failed',image=NULL");store.db.commit()
        with pytest.raises(ValueError,match='illustration record'):validate_state(store.path)


def test_road_renewal_cannot_fall_back_to_a_food_scene():
    row={'kind':'news','category':'food','title':'Selçuk’ta 15,5 kilometrelik yol yenileniyor'}
    assert subject(row)=='maintenance_tools'


def test_reviewed_calendar_exception_is_exact_pixels_and_exact_subject():
    data=(editorial_stock.DIRECTORY/'event_calendar.jpg').read_bytes()
    assert editorial_stock.reviewed_calendar(data,'event_calendar')
    assert not editorial_stock.reviewed_calendar(data,'theatre')
    assert not editorial_stock.reviewed_calendar(data+b'changed','event_calendar')


@pytest.mark.parametrize('changed',[False,True])
def test_only_current_same_brief_donor_can_be_reused(tmp_path,monkeypatch,changed):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        generator=manager(store,tmp_path,monkeypatch)
        donor=item(10); target=item(11)
        pixels=(editorial_stock.DIRECTORY/'theatre.jpg').read_bytes()
        old_key=image_key(donor)
        stored={**donor,'title':'Başka konser','category':'concert'} if changed else donor
        store.db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?)',
            (donor['id'],'event',digest('donor'),json.dumps(stored),1,AT.isoformat(),AT.isoformat()))
        store.db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',
            (old_key,donor['id'],'ready',pixels,1,AT.isoformat(),AT.isoformat()))
        store.db.commit()
        before=store.rows('SELECT * FROM illustrations')
        monkeypatch.setattr(editorial_stock,'stock_image',lambda *args:None)
        result=generator.image(target,True)
        assert bool(result) is (not changed)
        assert generator.stats['scene_reused']==int(not changed)
        assert store.rows('SELECT * FROM illustrations WHERE id=?',(old_key,))==before
        assert not store.rows('SELECT * FROM illustration_days')
        generator.session.post.assert_not_called()



def test_rebetiko_uses_music_scene_without_guessing_unknown_events():
    row=item(category='event',title="Rebetiko Kordelio Yunan Yemekleri ve Gecesi")
    assert subject(row)=='concert'
    assert editorial_stock.stock_image('concert',scene_brief(row))
    assert subject(item(category='event',title='Yunan Yemekleri ve Gecesi')) is None
