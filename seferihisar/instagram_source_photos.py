"""Optional GET-only single photos, isolated from captions and publication.

Signed CDN URLs and raw Graph responses stay in memory. Only bounded, stripped
JPEGs plus permalink-bound public evidence leave this credentialed job.
"""
import argparse
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import requests

from .collect import safe_url
from .domain import now, parse_date, canonical
from .image_safety import MAX_IMAGE_BYTES, validate_jpeg
from .instagram_sources import consume, read_account, caption_items, SourceReadError
from .security import assert_no_secrets
from .source_photo_data import INSTAGRAM_VERSION, validate_evidence
from .source_photos import ARCHIVE, cleaned_photo, news_subject, normalized
from .timeliness import publication_reason
from .visual_gate import fingerprint

MAX_PHOTOS=2
STATUSES=('available','no_single_photo','api_unavailable','download_rejected')


def cdn_url(value):
    if not isinstance(value,str) or len(value)>4096:raise ValueError('Invalid media destination')
    parts=urlsplit(value)
    host=parts.hostname or ''
    allowed=(re.fullmatch(r'scontent(?:-[a-z0-9-]+)?\.cdninstagram\.com',host)
             or re.fullmatch(r'(?:scontent|instagram)(?:[.-][a-z0-9-]+)*\.fbcdn\.net',host))
    if (not allowed or parts.fragment or parts.username or parts.password or parts.port not in (None,443)
            or parts.scheme!='https' or not re.search(r'\.(?:jpe?g|png|webp)$',parts.path,re.I)
            or any(any(word in name.casefold() for word in ('token','auth','password','secret','credential'))
                   for name,_ in parse_qsl(parts.query))):
        raise ValueError('Unapproved media destination')
    return safe_url(value,{host})


def download(value,client):
    # This session has no Graph headers, cookies or bearer credential. No retry,
    # redirects, videos, arbitrary external hosts or original metadata export.
    url=cdn_url(value)
    with client.get(url,timeout=(8,15),stream=True,allow_redirects=False) as response:
        if (response.status_code!=200 or response.headers.get('Content-Type','').split(';')[0].lower()
                not in ('image/jpeg','image/png','image/webp')):
            raise ValueError('Media unavailable')
        raw=bytearray()
        for chunk in response.iter_content(65536):
            raw.extend(chunk)
            if len(raw)>2_000_000:raise ValueError('Oversized media')
    image=cleaned_photo(bytes(raw));validate_jpeg(image)
    return image


def build(path,sources,at,*,graph=None,images=None):
    items,_=consume(path,sources,at)
    selected={s['id']:s for s in sources}
    # No second call to accounts whose caption read failed. No attempt to
    # download reel thumbnails, video frames or an arbitrary carousel slide.
    candidates=[i for i in items if news_subject(i) and i.get('kind')=='news' and publication_reason(i,at) is None
                and '/p/' in i['url'] and not ARCHIVE.search(normalized(i['description']))]
    candidates.sort(key=lambda i:(i['published_at'],i['url']),reverse=True)
    checks=[];photos=[];accounts={};blobs={}
    own_graph,own_images=graph is None,images is None
    graph=graph or requests.Session();images=images or requests.Session()
    if own_graph:graph.trust_env=False
    if own_images:images.trust_env=False
    try:
        for item in candidates[:MAX_PHOTOS]:
            sid=item['source_id'];status='no_single_photo'
            try:
                if sid not in accounts:
                    try:
                        accounts[sid]=read_account(selected[sid],os.getenv('IG_SOURCE_ACCESS_TOKEN',''),
                            os.getenv('IG_SOURCE_USER_ID',''),os.getenv('META_GRAPH_VERSION','v25.0'),graph,photos=True)
                    except SourceReadError:accounts[sid]=None
                account=accounts[sid]
                if account is None:status='api_unavailable'
                else:
                    # Reparse this response and require the exact caption item
                    # already passed to research, rather than trusting URL alone.
                    fresh=caption_items(account,selected[sid],at)
                    rows=account.get('media',{}).get('data',[])
                    matching=[r for r in rows if isinstance(r,dict) and isinstance(r.get('permalink'),str)
                              and canonical(r['permalink'])==canonical(item['url'])]
                    if item in fresh and len(matching)==1 and matching[0].get('media_type')=='IMAGE':
                        row=matching[0]
                        if not isinstance(row.get('id'),str) or not re.fullmatch(r'\d{8,32}',row['id']):
                            raise ValueError('Invalid media identity')
                        image=download(row.get('media_url'),images)
                        evidence={'version':INSTAGRAM_VERSION,'source_id':sid,'source_url':item['url'],
                                  'media_id':row['id'],'title':item['title'],'published_at':item['published_at'],
                                  'checked_at':at.isoformat(),'subject':news_subject(item),'sha256':fingerprint(image)}
                        validate_evidence(evidence)
                        # Do not label identical pixels as two different events.
                        if evidence['sha256'] in blobs:raise ValueError('Repeated source photograph')
                        blobs[evidence['sha256']]=image;photos.append(evidence);status='available'
            except SourceReadError:status='api_unavailable'
            except (requests.RequestException,ValueError,TypeError,KeyError,OSError,AttributeError):
                status='download_rejected'
            checks.append({'source_id':sid,'status':status})
        # Use the caption manifest generation as an exact artifact-run binding.
        generated=json.loads(path.read_text(encoding='utf8'))['generated_at'] if items else at.isoformat()
        result={'schema_version':1,'generated_at':generated,'photos':photos,'checks':checks}
        assert_no_secrets(result)
        return result,blobs
    finally:
        if own_graph:graph.close()
        if own_images:images.close()


def consume_photos(path,sources,at):
    """Revalidate the run artifact independently; failure keeps captions usable."""
    if path is None:return {},{'status':'not_supplied','available':0,'checks':[]}
    try:
        items,_=consume(path,sources,at)
        caption=json.loads(path.read_text(encoding='utf8'))
        index=path.parent/'photos.json'
        if path.parent.is_symlink() or index.is_symlink() or index.stat().st_size>16_000:
            raise ValueError('Invalid photo artifact')
        data=json.loads(index.read_text(encoding='utf8'));assert_no_secrets(data)
        if (not isinstance(data,dict) or set(data)!={'schema_version','generated_at','photos','checks'}
                or data['schema_version']!=1 or data['generated_at']!=caption['generated_at']
                or not isinstance(data['photos'],list) or len(data['photos'])>MAX_PHOTOS
                or not isinstance(data['checks'],list) or len(data['checks'])>MAX_PHOTOS):
            raise ValueError('Invalid photo artifact')
        allowed={s['id'] for s in sources if s.get('kind')=='instagram_api' and s.get('enabled') and s.get('trusted') and s.get('access')=='api'}
        for row in data['checks']:
            if (not isinstance(row,dict) or set(row)!={'source_id','status'} or row['source_id'] not in allowed
                    or row['status'] not in STATUSES):raise ValueError('Invalid photo diagnostics')
        if sum(row['status']=='available' for row in data['checks'])!=len(data['photos']):
            raise ValueError('Conflicting photo diagnostics')
        found={};hashes=set()
        for value in data['photos']:
            validate_evidence(value)
            if value['version']!=INSTAGRAM_VERSION:raise ValueError('Invalid photo origin')
            matching=[i for i in items if i['url']==value['source_url'] and i['source_id']==value['source_id']]
            if len(matching)!=1:raise ValueError('Unknown photo item')
            item=matching[0];checked=parse_date(value['checked_at'])
            if (item['kind']!='news' or publication_reason(item,at) is not None
                    or news_subject(item)!=value['subject'] or ARCHIVE.search(normalized(item['description']))
                    or item['title']!=value['title'] or item['published_at']!=value['published_at']
                    or not at-timedelta(hours=1)<=checked<=at+timedelta(minutes=5)
                    or value['source_url'] in found or value['sha256'] in hashes):
                raise ValueError('Stale or mismatched photo')
            directory=path.parent/'photos';image_path=directory/(value['sha256'].replace(':','')+'.jpg')
            if directory.is_symlink() or image_path.is_symlink() or image_path.stat().st_size>MAX_IMAGE_BYTES:
                raise ValueError('Invalid photo file')
            image=image_path.read_bytes();validate_jpeg(image)
            if fingerprint(image)!=value['sha256']:raise ValueError('Photo changed')
            found[value['source_url']]=(value,image);hashes.add(value['sha256'])
        return found,{'status':'checked','available':len(found),'checks':data['checks']}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        return {},{'status':'unavailable','available':0,'checks':[]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,default=Path('config/sources.json'))
    parser.add_argument('--manifest',type=Path,default=Path('work/instagram-sources/public.json'))
    args=parser.parse_args()
    try:
        data,blobs=build(args.manifest,json.loads(args.sources.read_text(encoding='utf8')),now())
        folder=args.manifest.parent/'photos';folder.mkdir(parents=True,exist_ok=True)
        for sha,image in blobs.items():(folder/(sha.replace(':','')+'.jpg')).write_bytes(image)
        (args.manifest.parent/'photos.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        print(json.dumps({'available':len(data['photos']),'checks':data['checks']}))
    except (OSError,ValueError,TypeError,KeyError):
        raise SystemExit('Optional Instagram photos unavailable; captions remain usable.') from None


if __name__=='__main__':main()
