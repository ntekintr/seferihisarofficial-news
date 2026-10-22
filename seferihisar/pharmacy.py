"""One independent daily duty-pharmacy story edition, targeted at 17:00 TR."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time

import requests

from .domain import TZ, now, digest
from .pharmacy_data import asset_id, fresh, profile, validate_bulletin


def refresh(store,at,fetcher=None):
    at=at.astimezone(TZ)
    if not 16 <= at.hour < 18:return
    day=at.date().isoformat()
    rows=store.rows('SELECT * FROM pharmacy_stories WHERE day=?',(day,))
    old=rows[0] if rows else None
    if old and old['status'] in ('publishing','published','uncertain'):return
    if old and old['status']=='prepared' and datetime.fromisoformat(old['checked_at'])>at-timedelta(minutes=15):return
    try:
        from .pharmacy_source import fetch_bulletin
        value=fetch_bulletin(at,fetcher)
        from .pharmacy_render import layouts
        layouts(value)  # Actual glyph/line budget, before marking the list prepared.
        payload=json.dumps(value,ensure_ascii=False,sort_keys=True);status=result='prepared'
    except (requests.RequestException,ValueError,TypeError,KeyError,OSError):
        payload=None;status='blocked';result='source_unavailable'
    with store.db:
        store.db.execute("INSERT INTO pharmacy_stories(day,bulletin,status,checked_at,last_result) VALUES(?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET bulletin=excluded.bulletin,status=excluded.status,checked_at=excluded.checked_at,last_result=excluded.last_result "
            "WHERE pharmacy_stories.status IN ('prepared','blocked')",(day,payload,status,now().isoformat(),result))


def export(store,public_dir,at):
    today=at.astimezone(TZ).date().isoformat();current=None
    # Retain frozen editions' versioned public media as well as today's preview.
    for row in store.rows("SELECT * FROM pharmacy_stories WHERE day=? OR status IN ('publishing','published','uncertain') ORDER BY day",(today,)):
        record={k:row[k] for k in ('day','status','checked_at','last_result','published_at')}
        record.update(target_time='17:00',timezone='Europe/Istanbul')
        if row['bulletin']:
            value=validate_bulletin(json.loads(row['bulletin']))
            from .pharmacy_render import render
            record.update(bulletin=value,asset_id=asset_id(value),**render(value,public_dir))
        if row['day']==today:current=record
    return current


@dataclass(frozen=True)
class Ready:
    day:str
    payload:str
    urls:tuple


def _profile_enabled():
    p=profile()
    if p['city']=='isparta':
        path=Path(__file__).resolve().parents[1]/'config/runtime.json'
        settings=json.loads(path.read_text(encoding='utf-8'))
        if (settings.get('repository')!=p['repository'] or settings.get('publishing_enabled') is not True
                or settings.get('meta_connected') is not True or settings.get('pharmacy_stories_enabled') is not True
                or settings.get('instagram_auth_mode')!=os.getenv('INSTAGRAM_AUTH_MODE')):
            return False
    return True


def account_matches(api):
    if not isinstance(api.account,str) or not re.fullmatch(r'\d{1,32}',api.account):return False
    mode=os.getenv('INSTAGRAM_AUTH_MODE')
    if mode=='instagram_login':
        if not api.base.startswith('https://graph.instagram.com/v'):return False
        value=api.call('me','GET',fields='user_id,username,account_type')
        if isinstance(value,dict) and 'data' in value:
            rows=value['data']
            if (not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict)
                    or any(k in value for k in ('id','user_id','username','account_type'))):return False
            value=rows[0]
        if (not isinstance(value,dict) or 'error' in value or not isinstance(value.get('account_type'),str)
                or value['account_type'].upper() not in ('BUSINESS','MEDIA_CREATOR')):return False
        key='user_id'
    elif mode=='facebook_login':
        if not api.base.startswith('https://graph.facebook.com/v'):return False
        value=api.call(api.account,'GET',fields='id,username');key='id'
    else:return False
    return isinstance(value,dict) and value.get(key)==api.account and value.get('username')==profile()['username']


def observe(store,at,adapter=None):
    """Bounded GET-only membership evidence; independent of publication receipts."""
    if not _profile_enabled():return {'status':'disabled'}
    rows=store.rows("SELECT * FROM pharmacy_stories WHERE status='published' AND day=?",(at.astimezone(TZ).date().isoformat(),))
    if not rows:return {'status':'no_recorded_delivery'}
    row=rows[0];claimed=datetime.fromisoformat(row['published_at'])
    if at-claimed<timedelta(minutes=3):return {'status':'propagation_pending'}
    if at-claimed>=timedelta(hours=23):return {'status':'expired_not_checked'}
    tasks=[]
    for index,media in enumerate(json.loads(row['media_ids'])):
        key=digest('instagram-pharmacy:'+row['day']+':'+str(index))
        old=store.rows('SELECT * FROM delivery_audits WHERE id=?',(key,))
        if old and at-datetime.fromisoformat(old[0]['checked_at'])<timedelta(hours=6):continue
        tasks.append((key,media))
    if not tasks:return {'status':'observation_current'}
    from .instagram import Instagram
    api=adapter or Instagram()
    if not api.enabled():return {'status':'disabled'}
    try:
        if not account_matches(api):return {'status':'account_mismatch'}
        value=api.call(api.account+'/stories','GET',fields='id')
        values=value.get('data')
        if (not isinstance(values,list) or any(not isinstance(v,dict) or not isinstance(v.get('id'),str)
                or not re.fullmatch(r'\d{1,32}',v['id']) for v in values)):
            raise ValueError('Invalid story membership response')
        active={v['id'] for v in values}
        results=[(key,'instagram','story',at.isoformat(),'present' if media in active else 'not_visible') for key,media in tasks]
    except (requests.RequestException,RuntimeError,ValueError,TypeError,KeyError):
        results=[(key,'instagram','story',at.isoformat(),'read_failed') for key,_ in tasks]
    from .delivery_audit import validate_row, MAX_ROWS
    with store.db:
        for result in results:
            validate_row(result)
            store.db.execute('INSERT OR REPLACE INTO delivery_audits VALUES(?,?,?,?,?)',result)
        store.db.execute('DELETE FROM delivery_audits WHERE id NOT IN (SELECT id FROM delivery_audits ORDER BY checked_at DESC,id LIMIT ?)',(MAX_ROWS,))
    return {'status':'observed','parts':{r[0]:r[-1] for r in results},'image_pixels_inspected':False}


def readiness(store,at,site,api):
    p=profile()
    if not _profile_enabled() or not api.enabled():return {'status':'disabled'}
    if site.rstrip('/')!=p['site']:raise ValueError('Unexpected pharmacy public site')
    day=at.astimezone(TZ).date().isoformat()
    rows=store.rows('SELECT * FROM pharmacy_stories WHERE day=?',(day,))
    if not rows:return {'status':'source_unavailable'}
    row=rows[0]
    if row['status']=='published':return {'status':'already_published'}
    if row['status'] in ('publishing','uncertain'):return {'status':'awaiting_resolution'}
    if row['status']!='prepared' or not row['bulletin']:return {'status':'source_unavailable'}
    value=json.loads(row['bulletin'])
    if not fresh(value,at):return {'status':'source_stale'}
    try:
        from .pharmacy_render import layouts
        count=len(layouts(value))
        response=api.session.get(site+'/data.json',timeout=(8,20),allow_redirects=False)
        if response.status_code!=200 or len(response.content)>8_000_000:return {'status':'media_not_deployed'}
        snapshot=response.json();record=snapshot.get('pharmacy_story') or {}
        paths=[f'media/{asset_id(value)}/story-{i}.jpg' for i in range(1,count+1)]
        hashes=record.get('sha256',{})
        if (snapshot.get('demo') is not False or snapshot.get('brand',{}).get('version')!=value['brand_version']
                or record.get('status')!='prepared' or record.get('bulletin')!=value
                or record.get('assets')!=paths or set(hashes)!=set(paths)):
            return {'status':'media_not_deployed'}
        from PIL import Image
        for path in paths:
            image=api.session.get(site+'/'+path,timeout=(8,20),allow_redirects=False)
            if (image.status_code!=200 or not image.headers.get('Content-Type','').startswith('image/jpeg')
                    or len(image.content)>6_000_000 or hashlib.sha256(image.content).hexdigest()!=hashes[path]):
                return {'status':'media_not_deployed'}
            with Image.open(BytesIO(image.content)) as jpeg:
                if jpeg.size!=(1080,1920) or jpeg.format!='JPEG':return {'status':'media_not_deployed'}
                jpeg.verify()
    except (requests.RequestException,ValueError,TypeError,KeyError,OSError):
        return {'status':'media_not_deployed'}
    return Ready(day,row['bulletin'],tuple(site+'/'+path for path in paths))


def publish(store,at,site,adapter=None,checkpoint=None):
    at=at.astimezone(TZ)
    if at.hour!=17:return {'status':'outside_window'}
    if not _profile_enabled():return {'status':'disabled'}
    from .instagram import Instagram
    api=adapter or Instagram()
    ready=readiness(store,at,site,api)
    if not isinstance(ready,Ready):return ready
    if checkpoint is None:return {'status':'disabled'}  # No non-durable live path.
    try:
        if not account_matches(api):return {'status':'account_mismatch'}
    except (requests.RequestException,RuntimeError,ValueError,KeyError,TypeError):
        return {'status':'account_mismatch'}
    with store.db:
        claim=store.db.execute("UPDATE pharmacy_stories SET status='publishing',published_at=?,last_result='uncertain' "
            "WHERE day=? AND status='prepared' AND bulletin=?",(at.isoformat(),ready.day,ready.payload))
    if claim.rowcount!=1:return {'status':'awaiting_resolution'}
    checkpoint()  # Before the first Meta mutation; a failure stops publication.
    containers=[];media=[]
    try:
        for url in ready.urls:
            container=api.container([url],'',True)
            if not isinstance(container,str) or not re.fullmatch(r'\d{1,32}',container):raise ValueError('Invalid container')
            containers.append(container)
            with store.db:store.db.execute('UPDATE pharmacy_stories SET container_ids=? WHERE day=?',(json.dumps(containers),ready.day))
            checkpoint();api.wait(container)
            item=api.call(f'{api.account}/media_publish',creation_id=container)['id']
            if not isinstance(item,str) or not re.fullmatch(r'\d{1,32}',item):raise ValueError('Invalid media')
            media.append(item)
            with store.db:store.db.execute('UPDATE pharmacy_stories SET media_ids=? WHERE day=?',(json.dumps(media),ready.day))
            checkpoint()
        with store.db:store.db.execute("UPDATE pharmacy_stories SET status='published',last_result='published' WHERE day=?",(ready.day,))
        checkpoint();return {'status':'published','stories':len(media)}
    except (requests.RequestException,RuntimeError,ValueError,KeyError,TypeError):
        with store.db:store.db.execute("UPDATE pharmacy_stories SET status='uncertain',last_result='uncertain' WHERE day=?",(ready.day,))
        checkpoint();return {'status':'uncertain','confirmed_parts':len(media)}


def run(store,site,adapter=None,checkpoint=None,*,wait_for_target=False,clock=None,sleeper=None):
    clock=clock or now;sleeper=sleeper or time.sleep;at=clock().astimezone(TZ)
    target=at.replace(hour=17,minute=0,second=0,microsecond=0)
    if wait_for_target and target-timedelta(minutes=25)<=at<target:
        if not _profile_enabled():return {'status':'disabled'}
        from .instagram import Instagram
        api=adapter or Instagram()
        ready=readiness(store,target,site,api)
        if not isinstance(ready,Ready):return ready
        remaining=25*60
        while at<target:
            if remaining<=0 or at.date()!=target.date():return {'status':'outside_window'}
            seconds=min(30,(target-at).total_seconds(),remaining);sleeper(seconds);remaining-=seconds
            at=clock().astimezone(TZ)
        return publish(store,at,site,api,checkpoint)
    return publish(store,at,site,adapter,checkpoint)


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--wait-for-target',action='store_true')
    parser.add_argument('--observe-only',action='store_true');args=parser.parse_args()
    p=profile()
    if os.getenv('GITHUB_REPOSITORY')!=p['repository'] or os.getenv('GITHUB_REF')!='refs/heads/main':
        raise SystemExit('Correct pharmacy repository and main workflow required')
    from .store import Store
    from .state_git import persist
    store=Store('state/platform.sqlite')
    try:
        result=(observe(store,now()) if args.observe_only else
                run(store,p['site'],checkpoint=lambda:persist(store.path),wait_for_target=args.wait_for_target))
        if not args.observe_only and result['status'] in ('source_stale','media_not_deployed','account_mismatch','disabled'):
            with store.db:
                store.db.execute("UPDATE pharmacy_stories SET last_result=? WHERE day=? AND status IN ('prepared','blocked')",
                                 (result['status'],now().date().isoformat()))
        if target:=os.getenv('GITHUB_STEP_SUMMARY'):
            with Path(target).open('a',encoding='utf-8') as out:
                out.write('### Günlük nöbetçi eczane story\n\n'+json.dumps(result)+'\n\n17:00 Türkiye saati hedefi; ayrı günlük story listesi. Hazırlık gerçek teslim değildir.\n')
        print(json.dumps(result))
        if not args.observe_only and result['status'] not in ('published','already_published','outside_window','disabled'):raise SystemExit(1)
    finally:store.close()


if __name__=='__main__':main()
