"""Conservative, article-bound news photos; never infer incident identity from CLIP."""
import io
import json
import os
import re
from datetime import timedelta
from urllib.parse import urljoin,urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image

from .collect import Fetcher,structured
from .domain import canonical,normalized,parse_date
from .illustrations import clean_image
from .security import public_url,contains_secret
from .source_photo_data import VERSION,EVENT_VERSION,key,validate_record,valid_bindings,MAX_CACHE_BYTES,MAX_CACHED_IMAGES
from .visual_gate import fingerprint
from .visual_match import validate_news_photo,MatchRejected,MatchUnavailable
from .image_safety import IllustrationCheckUnavailable

MAX_READS=2
ARCHIVE=re.compile(r'\b(?:ar[şs]iv\w*|temsili\w*|illustration\w*|ill[uü]strasyon\w*|stok|stock|yapay zek[aâ]\w*|ai generated)\b')


def news_subject(item):
    if item.get('kind')!='news' or item.get('category')=='outage':return None
    title=normalized(item.get('title',''))
    # A warning, cancellation or proposal is not evidence that the pictured
    # incident/meeting happened. Keep those notices on information cards.
    if re.search(r'\b(?:uyari\w*|beklen\w*|risk\w*|iptal\w*|planlan\w*|yarin|yapilacak|gerçekleşecek|önlenecek)\b',title):
        return None
    if re.search(r'\b(?:sel|su baskini|göle döndü|sular altinda)\b',title):return 'flood'
    if (re.search(r'\b(?:mandalina\w*|satsuma)\b', title)
            and re.search(r'\bhasat\w*\b', title)
            and re.search(r'\b(?:başladi|sürüyor|yapiliyor)\b', title)):
        return 'citrus_harvest'
    if re.search(r'\b(?:toplanti\w*|bir araya gel\w*|buluştu|bulustu)\b',title):return 'meeting'
    if re.search(r'\b(?:trafik|çevre yolu|kavşak)\b',title):return 'traffic'
    return None


def photo_subject(item):
    if item.get('kind') == 'event':
        if item.get('status') not in ('scheduled','rescheduled'):
            return None
        from .visual_subject import subject
        return subject(item)
    return news_subject(item)


def identity_dates(item):
    return {k:item.get(k) for k in (('start','end') if item.get('kind')=='event' else ('published_at',))}


def candidate(html,final_url,item,source):
    """Same article URL, headline and publication date, plus an in-article image."""
    if canonical(final_url)!=canonical(item['url']):raise ValueError('Article redirected')
    matches=[row for row in structured(html,final_url,source) if row['kind']==item.get('kind')
             and canonical(row['url'])==canonical(item['url'])
             and normalized(row['title'])==normalized(item['title'])
             and all(parse_date(row.get(k))==parse_date(v) and parse_date(v) is not None
                     for k,v in identity_dates(item).items())
             and (item.get('kind')!='event' or all(row.get(k)==item.get(k)
                  for k in ('location','status','time_known')))]
    if len(matches)!=1:raise ValueError('Article identity mismatch')
    soup=BeautifulSoup(html,'html.parser')
    canonical_node=soup.select_one('link[rel="canonical"][href]')
    if canonical_node and canonical(urljoin(final_url,canonical_node['href']))!=canonical(item['url']):
        raise ValueError('Article canonical mismatch')
    article=soup.select_one(source.get('article_selector','article .entry-content, article .article-content, article, .news-detail, .haber-detay'))
    if not article:raise ValueError('No article image scope')
    # WordPress featured photos often sit beside entry-content inside article.
    article=article.find_parent('article') or article
    heading=soup.select_one(source['title_selector']) if source.get('title_selector') else article.find('h1')
    if heading and normalized(heading.get_text(' ',strip=True))!=normalized(item['title']):
        raise ValueError('Visible article headline mismatch')
    image_alt=soup.select_one('meta[property="og:image:alt"][content]')
    if image_alt and ARCHIVE.search(normalized(image_alt['content'])):
        raise ValueError('Archival article photograph')
    images={}
    for node in article.select('img'):
        if node.find_parent(['aside','nav','footer','header']):continue
        raw=node.get('data-src') or node.get('src')
        if not isinstance(raw,str):continue
        url=urljoin(final_url,raw)
        label=normalized(' '.join(str(node.get(k,'')) for k in ('alt','title')))
        figure=node.find_parent('figure')
        if figure and (caption:=figure.find('figcaption')):label+=' '+normalized(caption.get_text(' ',strip=True))
        if (not public_url(url) or len(url)>2048 or urlsplit(url).hostname!=urlsplit(item['url']).hostname
                or ARCHIVE.search(label) or re.search(r'logo|avatar|banner|reklam|placeholder|no-image',urlsplit(url).path,re.I)):
            continue
        link=node.find_parent('a',href=True)
        if link:
            href=urljoin(final_url,link['href'])
            if canonical(href) not in (canonical(url),canonical(item['url'])):continue
        images[url]=label
    primary=soup.select_one('meta[property="og:image"][content]')
    if primary:
        url=urljoin(final_url,primary['content'])
        if url in images:return url
        # A WordPress featured img can be a resized derivative of the exact
        # OpenGraph file. Match the same host/path, never filename alone.
        base=lambda value:re.sub(r'-\d{2,5}x\d{2,5}(?=\.(?:jpe?g|png|webp)$)','',canonical(value),flags=re.I)
        variants=[image for image in images if base(image)==base(url)]
        if (public_url(url) and len(url)<=2048 and urlsplit(url).hostname==urlsplit(item['url']).hostname
                and len(variants)==1):return variants[0]
    if len(images)!=1:raise ValueError('Ambiguous article photograph')
    return next(iter(images))


def cleaned_photo(raw, *, poster=False):
    if len(raw)>2_000_000:raise ValueError('Oversized source photo')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if (image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>4_000_000
                    or not ((image.width>=640 and image.height>=300 and 1.4<=image.width/image.height<=2.6)
                            or (poster and image.width>=480 and image.height>=640 and .5<=image.width/image.height<1.4))
                    or getattr(image,'n_frames',1)!=1 or image.getexif().get(274,1)!=1):
                # Cleaning strips EXIF. Do not silently turn an orientation-
                # dependent photograph sideways or change its displayed frame.
                raise ValueError('Unsupported source photo dimensions')
    except Image.DecompressionBombError:
        raise ValueError('Oversized source photo') from None
    return clean_image(raw)


def binding_reason(store,post,items,at):
    bindings=post.get('source_photo_keys',{})
    if not bindings:return None
    if not valid_bindings(bindings):return 'visual_review_stale'
    item=items.get(post.get('item_id'),{})
    for index,photo in bindings.items():
        rows=store.rows('SELECT * FROM source_photos WHERE id=?',(photo,))
        if not rows:return 'visual_review_stale'
        row=rows[0]
        try:value=validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
        except (ValueError,TypeError):return 'visual_review_stale'
        event=value['version']==EVENT_VERSION
        if ((item.get('kind')=='event')!=event or (not event and post.get('kind')!='news')
                or row['item_id']!=item.get('id') or row['revision']!=item.get('revision')
                or value['source_id']!=item.get('source_id') or value['source_url']!=item.get('url') or value['title']!=item.get('title')
                or any(value.get(k)!=v for k,v in identity_dates(item).items()) or value['subject']!=photo_subject(item)
                or post.get('visual_review',{}).get('images',{}).get(index)!=value['sha256']):
            return 'visual_review_stale'
        if not at-timedelta(hours=1)<=parse_date(value['checked_at'])<=at+timedelta(minutes=5):
            return 'visual_review_stale'
    return None


class SourcePhotos:
    def __init__(self,store,at,directory,sources,*,demo=False,fetcher=None,instagram_photos=None,instagram_checks=None):
        self.store,self.at,self.directory=store,at,directory
        self.enabled=not demo and os.getenv('ILLUSTRATIONS_ENABLED')=='true'
        self.sources={s['id']:s for s in sources if s.get('enabled') and s.get('trusted')
                      and ((s.get('kind') in ('html','rss') and s.get('access')=='robots')
                           or (s.get('kind')=='instagram_api' and s.get('access')=='api'))}
        self.instagram_photos=instagram_photos or {}
        self.fetcher=fetcher
        self.stats={'enabled':self.enabled,'downloaded':0,'reused':0,'rejected':0,'unavailable':0,'deferred':0}
        if instagram_checks is not None:self.stats['instagram']=instagram_checks
        self.reads=0
        self.results={}

    def materialize(self,row):
        validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
        self.directory.mkdir(parents=True,exist_ok=True)
        path=self.directory/(row['id']+'.jpg');path.write_bytes(row['image'])
        return path

    def frozen(self):
        return {key for p in self.store.posts() if p['status'] in ('publishing','published','uncertain')
                for key in p.get('source_photo_keys',{}).values()}

    def prune(self,allowed_ids):
        frozen=self.frozen()
        with self.store.db:
            for row in self.store.rows('SELECT id,item_id FROM source_photos'):
                if row['item_id'] not in allowed_ids and row['id'] not in frozen:
                    self.store.db.execute('DELETE FROM source_photos WHERE id=?',(row['id'],))

    def image(self,item):
        if item['id'] in self.results:return self.results[item['id']]
        self.results[item['id']]=None
        source=self.sources.get(item['source_id']);expected=photo_subject(item)
        if (not source or not expected or contains_secret(item) or not public_url(item['url'])
                or urlsplit(item['url']).hostname!=urlsplit(source['url']).hostname):return None
        if source['kind']=='instagram_api':
            if item.get('kind')!='news':return None
            result=self.instagram_photos.get(item['url'])
            if not result:return None
            if self.reads>=MAX_READS:self.stats['deferred']+=1;return None
            self.reads+=1
            try:
                evidence,image=result
                # Artifact provenance is revalidated by the consumer; check it
                # again against the actual durable item revision before binding.
                if (evidence['source_id']!=item['source_id'] or evidence['title']!=item['title']
                        or evidence['published_at']!=item['published_at'] or evidence['subject']!=expected):
                    raise ValueError('Instagram photo changed')
                validate_news_photo(image,expected)
                return self.save(item,evidence,image)
            except MatchUnavailable:self.stats['unavailable']+=1
            except (ValueError,TypeError,KeyError,OSError):self.stats['rejected']+=1
            return None
        rows=self.store.rows('SELECT * FROM source_photos WHERE item_id=? AND revision=?',(item['id'],item['revision']))
        for row in rows:
            value=validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
            if (row['id'] not in self.frozen() and value['title']==item['title'] and value['source_url']==item['url']
                    and value['source_id']==item['source_id'] and all(value.get(k)==v for k,v in identity_dates(item).items())
                    and value['subject']==expected
                    and self.at-timedelta(minutes=15)<=parse_date(value['checked_at'])<=self.at+timedelta(minutes=5)):
                self.stats['reused']+=1
                self.results[item['id']]=(row['id'],self.materialize(row))
                return self.results[item['id']]
        if self.reads>=MAX_READS:
            self.stats['deferred']+=1;return None
        self.reads+=1
        try:
            if self.fetcher is None:self.fetcher=Fetcher(list(self.sources.values()))
            html,final=self.fetcher.get(item['url'])
            url=candidate(html,final,item,source)
            raw,final_image=self.fetcher.image(url)
            if final_image!=url:raise ValueError('Image redirected')
            image=cleaned_photo(raw,poster=item.get('kind')=='event')
            if item.get('kind')=='event':
                from .event_image_text import validate as validate_event_text
                with Image.open(io.BytesIO(image)) as pixels:portrait=pixels.width<pixels.height
                validate_event_text(image,item,poster=portrait)
                from .visual_match import validate_event_photo
                validate_event_photo(image,expected)
            else:
                validate_news_photo(image,expected)
            sha=fingerprint(image)
            for previous in self.store.rows('SELECT item_id,payload FROM source_photos WHERE item_id!=?',(item['id'],)):
                old=json.loads(previous['payload'])
                if old.get('image_url')==url or old['sha256']==sha:
                    raise ValueError('Photograph reused by another article')
            evidence={'version':EVENT_VERSION if item.get('kind')=='event' else VERSION,'source_id':item['source_id'],'source_url':item['url'],
                      'image_url':url,'title':item['title'],**identity_dates(item),
                      'checked_at':self.at.isoformat(),'subject':expected,'sha256':sha}
            return self.save(item,evidence,image)
        except (MatchUnavailable,IllustrationCheckUnavailable):self.stats['unavailable']+=1
        except (requests.RequestException,ValueError,TypeError,KeyError,OSError):self.stats['rejected']+=1
        return None

    def save(self,item,evidence,image):
        photo=key(item['id'],item['revision'],evidence)
        payload=json.dumps(evidence,ensure_ascii=False)
        validate_record(photo,item['id'],item['revision'],payload,image)
        for previous in self.store.rows('SELECT item_id,payload FROM source_photos WHERE item_id!=?',(item['id'],)):
            old=json.loads(previous['payload'])
            if old['sha256']==evidence['sha256'] or (evidence.get('media_id') and old.get('media_id')==evidence['media_id']):
                raise ValueError('Photograph reused by another item')
        frozen=self.frozen()
        with self.store.db:
            # Only unreferenced draft cache rows may be evicted. Frozen
            # pixels and evidence survive every later research/export.
            used={key for p in self.store.posts() for key in p.get('source_photo_keys',{}).values()}
            for row in self.store.rows('SELECT id FROM source_photos'):
                if row['id'] not in used and row['id']!=photo:self.store.db.execute('DELETE FROM source_photos WHERE id=?',(row['id'],))
            size,count=self.store.db.execute('SELECT COALESCE(SUM(length(image)),0),COUNT(*) FROM source_photos WHERE id!=?',(photo,)).fetchone()
            if size+len(image)>MAX_CACHE_BYTES or count>=MAX_CACHED_IMAGES:
                self.stats['deferred']+=1;return None
            if photo not in frozen:
                self.store.db.execute('INSERT OR REPLACE INTO source_photos VALUES(?,?,?,?,?)',
                                      (photo,item['id'],item['revision'],payload,image))
        row=self.store.rows('SELECT * FROM source_photos WHERE id=?',(photo,))[0]
        self.stats['downloaded']+=1
        self.results[item['id']]=(photo,self.materialize(row))
        return self.results[item['id']]

    def for_post(self,post,items):
        assignments={}
        if post.get('source_photo_keys') and (post['status']!='prepared' or not self.enabled):
            for index,photo in post['source_photo_keys'].items():
                rows=self.store.rows('SELECT * FROM source_photos WHERE id=?',(photo,))
                if rows:assignments[int(index)]=self.materialize(rows[0])
            return assignments
        if not self.enabled or post['status']!='prepared' or not post.get('item_id'):return assignments
        bindings={}
        item=items.get(post.get('item_id'))
        if item and item['revision']==post.get('revision') and (result:=self.image(item)):
            photo,path=result
            bindings['0']=photo;assignments[0]=path
        # Add the field only to photo-bearing drafts, preserving legacy hashes.
        if bindings or 'source_photo_keys' in post:post['source_photo_keys']=bindings
        return assignments
