import hashlib
import json
import sqlite3
import pytest
from seferihisar.historical_visuals import fingerprint,repair,recover

def fixture():
    db=sqlite3.connect(':memory:')
    db.executescript("CREATE TABLE posts(id TEXT PRIMARY KEY,status TEXT,payload TEXT); CREATE TABLE illustrations(id TEXT PRIMARY KEY,item_id TEXT,status TEXT,image BLOB,attempts INTEGER,retry_at TEXT,updated_at TEXT);")
    claim=('post','published',json.dumps({'illustration_keys':{'0':'image'}}))
    original=('image','item','ready',b'old pixels',1,'retry','updated')
    db.execute('INSERT INTO posts VALUES(?,?,?)',claim)
    db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',original);db.commit()
    archive=db.serialize()
    manifest={'state_commit':'a'*40,'snapshot_sha256':hashlib.sha256(archive).hexdigest(),'rows':[{'key':'image','original':fingerprint(original),'observed':None,'owners':{'post':fingerprint(claim)}}]}
    db.execute('DELETE FROM illustrations');db.commit()
    return db,archive,manifest,claim,original

def test_missing_archive_repaired_without_touching_claim_and_idempotent():
    db,archive,m,claim,original=fixture()
    with db:assert repair(db,archive,m)==1
    assert db.execute('SELECT * FROM posts').fetchall()==[claim]
    assert db.execute('SELECT * FROM illustrations').fetchall()==[original]
    with db:assert repair(db,archive,m)==0

@pytest.mark.parametrize('change',['new_owner','changed_owner','changed_current','no_owner'])
def test_new_or_changed_claim_or_pixels_are_never_overwritten(change):
    db,archive,m,claim,original=fixture()
    if change=='new_owner':db.execute('INSERT INTO posts VALUES(?,?,?)',('new','publishing',claim[2]))
    if change=='changed_owner':db.execute("UPDATE posts SET status='uncertain'")
    if change=='changed_current':db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',(*original[:3],b'new pixels',*original[4:]))
    if change=='no_owner':db.execute('DELETE FROM posts')
    db.commit();before=db.serialize()
    with db:assert repair(db,archive,m)==0
    assert db.serialize()==before

def test_exact_observed_replacement_can_recover_original():
    db,archive,m,claim,original=fixture();current=(*original[:3],b'observed replacement',*original[4:])
    db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',current);db.commit()
    m['rows'][0]['observed']=fingerprint(current)
    with db:assert repair(db,archive,m)==1
    assert db.execute('SELECT * FROM illustrations').fetchone()==original

@pytest.mark.parametrize('bad',['snapshot','row'])
def test_mismatched_archive_fails_without_partial_changes(bad):
    db,archive,m,claim,original=fixture();before=db.serialize()
    if bad=='snapshot':m['snapshot_sha256']='0'*64
    else:m['rows'][0]['original']='0'*64
    with pytest.raises(ValueError),db:repair(db,archive,m)
    assert db.serialize()==before

def test_no_eligible_claim_means_no_git_or_remote_access(tmp_path):
    db,archive,m,claim,original=fixture();db.execute('DELETE FROM posts');db.commit()
    path=tmp_path/'state.sqlite';path.write_bytes(db.serialize())
    def deny(*args):raise AssertionError('Unexpected git call')
    assert recover(path,deny,m)==0

def test_recover_only_fetches_pinned_commit_when_needed(tmp_path):
    import subprocess
    db,archive,m,claim,original=fixture();path=tmp_path/'state.sqlite';path.write_bytes(db.serialize());calls=[]
    def git(*args):
        calls.append(args)
        if len(calls)==1:raise subprocess.CalledProcessError(1,'git')
        return archive if args[0]=='show' else b''
    assert recover(path,git,m)==1
    assert calls[1]==('fetch','--no-tags','--depth=1','origin',m['state_commit'])
    assert recover(path,lambda *a:pytest.fail('Repeated fetch'),m)==0

def test_recovery_evicts_only_expired_draft_cache_within_existing_limit(monkeypatch):
    db,archive,m,claim,original=fixture()
    db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',('stale','old','ready',b'old draft',1,'retry','updated'))
    db.execute('INSERT INTO posts VALUES(?,?,?)',('stale-post','expired',json.dumps({'illustration_keys':{'0':'stale'}})))
    db.commit();monkeypatch.setattr('seferihisar.image_safety.MAX_CACHED_IMAGES',1)
    with db:assert repair(db,archive,m)==1
    assert db.execute('SELECT id FROM illustrations').fetchall()==[('image',)]
    assert db.execute('SELECT count(*) FROM posts').fetchone()[0]==2

@pytest.mark.parametrize('status',['prepared','published','publishing','uncertain','blocked_source'])
def test_full_active_cache_skips_recovery_without_breaking_restore(monkeypatch,status):
    db,archive,m,claim,original=fixture()
    db.execute('INSERT INTO illustrations VALUES(?,?,?,?,?,?,?)',('active','other','ready',b'active pixels',1,'retry','updated'))
    db.execute('INSERT INTO posts VALUES(?,?,?)',('active-post',status,json.dumps({'illustration_keys':{'0':'active'}})))
    db.commit();before=db.serialize();monkeypatch.setattr('seferihisar.image_safety.MAX_CACHED_IMAGES',1)
    with db:assert repair(db,archive,m)==0
    assert db.serialize()==before
