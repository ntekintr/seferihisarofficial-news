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
from .source_photo_data import VERSION,EVENT_VERSION,key,validate_record,valid_bindings,MAX_CACHE_BYTES,MAX_CACHED_IMAGES,approved_image_url,IMAGE_ORIGINS,delivery_sources,reviewed_ticket_source,same_event_artwork
from .visual_gate import fingerprint
from .visual_match import validate_news_photo,MatchRejected,MatchUnavailable
from .image_safety import IllustrationCheckUnavailable

MAX_READS=2
MAX_SOURCE_CHECKS=6
ARCHIVE=re.compile(r'\b(?:ar[şs]iv\w*|temsili\w*|illustration\w*|ill[uü]strasyon\w*|stok|stock|yapay zek[aâ]\w*|ai generated)\b')


def news_subject(item):
    if item.get('kind') != 'news':
        return None
    from .visual_topics import news_subjects
    return news_subjects(item)[0]



def photo_subject(item):
    if item.get('kind') == 'event':
        if item.get('status') not in ('scheduled','rescheduled'):
            return None
        from .visual_subject import subject
        return subject(item) or ('event_poster' if item.get('category')=='event' else None)
    return news_subject(item)


def identity_dates(item):
    return {k:item.get(k) for k in (('start','end') if item.get('kind')=='event' else ('published_at',))}


def candidate_urls(html,final_url,item,source,*,feed_html=None):
    """Bounded candidates from one exact article/session, never related stories."""
    session_parent = (reviewed_ticket_source(source)
                      and re.fullmatch(re.escape(final_url.rstrip('/')) + r'/seans/\d+', item['url']))
    if canonical(final_url)!=canonical(item['url']) and not session_parent:raise ValueError('Article redirected')
    if reviewed_ticket_source(source):
        from .source_readers import ticket_items
        rows = ticket_items(html,final_url,source)
    else:
        rows = structured(html,final_url,source)
    if source.get('photo_identity_reader') == 'rss-html-v1' and source.get('kind') == 'rss':
        from .collect import feed_items
        if feed_html is None:
            raise ValueError('Current source feed required for article image')
        from xml.etree.ElementTree import ParseError
        try:
            rows = feed_items(feed_html,source['url'],source)
        except ParseError:
            raise ValueError('Source feed invalid') from None
    matches=[row for row in rows if row['kind']==item.get('kind')
             and not row.get('parser_holds') and not row.get('date_conflict')
             and canonical(row['url'])==canonical(item['url'])
             and normalized(row['title'])==normalized(item['title'])
             and all(parse_date(row.get(k))==parse_date(v) and parse_date(v) is not None
                     for k,v in identity_dates(item).items())
             and (item.get('kind')!='event' or all(row.get(k)==item.get(k)
                  for k in ('location','status','time_known')))]
    if len(matches)!=1:raise ValueError('Article identity mismatch')
    soup=BeautifulSoup(html,'html.parser')
    canonical_node=soup.select_one('link[rel="canonical"][href]')
    if canonical_node and canonical(urljoin(final_url,canonical_node['href']))!=canonical(final_url if session_parent else item['url']):
        raise ValueError('Article canonical mismatch')
    if reviewed_ticket_source(source):
        from .collect import objects
        candidates=[]
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                for obj in objects(json.loads(script.get_text())):
                    offers=obj.get('offers')
                    if (not isinstance(obj.get('@type'),str) or not obj['@type'].endswith('Event')
                            or not isinstance(offers,dict) or canonical(offers.get('url',''))!=canonical(item['url'])
                            or normalized(str(obj.get('name','')))!=normalized(item['title'])):
                        continue
                    image=obj.get('image')
                    image=image[0] if isinstance(image,list) and len(image)==1 else image
                    image=image.get('url') if isinstance(image,dict) else image
                    if isinstance(image,str) and approved_image_url(item['source_id'],item['url'],image):
                        candidates.append(image)
            except (ValueError,TypeError,KeyError):
                continue
        if len(set(candidates))!=1:raise ValueError('No exact session artwork')
        return [candidates[0]]
    article=soup.select_one(source.get('photo_article_selector') or source.get('article_selector','article .entry-content, article .article-content, article, .news-detail, .haber-detay'))
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
    # The reviewed body can be a sibling of the hero wrapper. Bind its direct
    # paragraphs to the exact body already parsed for this article; do not
    # expand to sidebars, comments or a second infinite-scroll article.
    body = soup.select_one(source['body_selector']) if source.get('body_selector') else None
    inline = ([node for node in soup.select(source['photo_inline_selector'])
               if any(parent is body for parent in node.parents)]
              if body is not None and source.get('photo_inline_selector') else [])
    inline_nodes = {id(node) for node in inline}
    inline_images = []
    nodes = list({id(node):node for node in article.select('img') + inline}.values())
    for node in nodes:
        if node.find_parent(['aside','nav','footer','header']):continue
        label=normalized(' '.join(str(node.get(k,'')) for k in ('alt','title')))
        figure=node.find_parent('figure')
        if figure and (caption:=figure.find('figcaption')):label+=' '+normalized(caption.get_text(' ',strip=True))
        raw_urls = [node.get('data-src'), node.get('src')]
        # Reviewed lazy-loading publishers omit src entirely. A valid bounded
        # srcset supplies candidates; OpenGraph must still choose an exact one.
        for field in ('srcset', 'data-srcset'):
            value = node.get(field, '')
            if isinstance(value, str) and len(value) <= 8192:
                raw_urls += [m[1] for part in value.split(',')[:12]
                             if (m:=re.fullmatch(r'\s*(\S+)\s+(\d{2,4})w\s*', part)) and int(m[2])<=4096]
        for raw in raw_urls:
            if not isinstance(raw,str):continue
            url=urljoin(final_url,raw)
            if (not approved_image_url(item['source_id'], item['url'], url)
                    or ARCHIVE.search(label) or re.search(r'logo|avatar|banner|reklam|placeholder|no-image',urlsplit(url).path,re.I)):
                continue
            link=node.find_parent('a',href=True)
            if link:
                href=urljoin(final_url,link['href'])
                if canonical(href) not in (canonical(url),canonical(item['url'])):continue
            images[url]=label
            if id(node) in inline_nodes and url not in inline_images:
                inline_images.append(url)
    # Natural, directly embedded source photographs are evaluated before an
    # editorial collage. The same strict subject check still accepts/rejects
    # each actual file; choosing a URL never grants visual approval.
    if inline_images:
        return inline_images[:MAX_READS]
    primary=soup.select_one('meta[property="og:image"][content]')
    if primary:
        url=urljoin(final_url,primary['content'])
        if url in images:return [url]
        # A WordPress featured img can be a resized derivative of the exact
        # OpenGraph file. Match the same host/path, never filename alone.
        base=lambda value:re.sub(r'-\d{2,5}x\d{2,5}(?=\.(?:jpe?g|png|webp)$)','',canonical(value),flags=re.I)
        variants=[image for image in images if base(image)==base(url)]
        if (approved_image_url(item['source_id'], item['url'], url)
                and len(variants)==1):return [variants[0]]
    if len(images)!=1:raise ValueError('Ambiguous article photograph')
    return [next(iter(images))]


def candidate(html,final_url,item,source):
    """Compatibility accessor; all identity checks precede image selection."""
    return candidate_urls(html,final_url,item,source)[0]


def cleaned_photo(raw, *, poster=False):
    if len(raw)>2_000_000:raise ValueError('Oversized source photo')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if (image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>4_000_000
                    or not ((image.width>=480 and image.height>=300 and max(image.size)>=640 and 0.5<=image.width/image.height<=2.6)
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
        # Source-owned photos don't require a generation service credential.
        # An explicit false also keeps this path closed if generation is enabled.
        self.enabled=not demo and os.getenv('SOURCE_PHOTOS_ENABLED', os.getenv('ILLUSTRATIONS_ENABLED', 'false'))=='true'
        self.sources={s['id']:s for s in sources if s.get('enabled') and s.get('trusted')
                      and (((s.get('kind') in ('html','rss') or reviewed_ticket_source(s)) and s.get('access')=='robots')
                           or (s.get('kind')=='instagram_api' and s.get('access')=='api'))}
        self.instagram_photos=instagram_photos or {}
        self.fetcher=fetcher
        self.stats={'enabled':self.enabled,'downloaded':0,'reused':0,'rejected':0,'unavailable':0,'deferred':0,
                    'rejection_stages':{},'source_checks':0,'cooldown':0}
        if instagram_checks is not None:self.stats['instagram']=instagram_checks
        self.reads=0
        self.results={}

    def failure(self,stage,*,unavailable=False):
        # Enumerated pipeline stages, never exception/provider text or URLs.
        if stage not in ('source_read','source_binding','image_read','image_format',
                         'event_text','visual_subject','cache_binding'):
            raise ValueError('Unknown source photograph check stage')
        self.stats['unavailable' if unavailable else 'rejected']+=1
        reasons=self.stats['rejection_stages']
        reasons[stage]=reasons.get(stage,0)+1

    def materialize(self,row):
        validate_record(row['id'],row['item_id'],row['revision'],row['payload'],row['image'])
        self.directory.mkdir(parents=True,exist_ok=True)
        path=self.directory/(row['id']+'.jpg');path.write_bytes(row['image'])
        return path

    def frozen(self):
        return {key for p in self.store.posts() if p['status'] in ('publishing','published','uncertain')
                for key in p.get('source_photo_keys',{}).values()}

    def prune(self,allowed_ids):
        from .source_photo_retry import prune
        prune(self.store,allowed_ids)
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
                    and self.at-timedelta(minutes=45)<=parse_date(value['checked_at'])<=self.at+timedelta(minutes=5)):
                self.stats['reused']+=1
                self.results[item['id']]=(row['id'],self.materialize(row))
                return self.results[item['id']]
        from .source_photo_retry import active,remember
        obsolete = ('image_read',) if reviewed_ticket_source(source) else ()
        if active(self.store,item,self.at,obsolete=obsolete):
            self.stats['cooldown']+=1;return None
        if self.reads>=MAX_READS or self.stats['source_checks']>=MAX_SOURCE_CHECKS:
            self.stats['deferred']+=1;return None
        # Missing images consume bounded page checks, not binary-image slots.
        self.stats['source_checks']+=1
        stage='source_read'
        try:
            if self.fetcher is None:
                cdns = delivery_sources(self.sources)
                self.fetcher=Fetcher(list(self.sources.values()) + cdns)
            page_url = re.sub(r'/seans/\d+$','',item['url']) if reviewed_ticket_source(source) else item['url']
            html,final=self.fetcher.get(page_url)
            stage='source_binding'
            feed_html = None
            if source.get('photo_identity_reader') == 'rss-html-v1' and source.get('kind') == 'rss':
                feed_html,feed_url = self.fetcher.get(source['url'])
                if canonical(feed_url) != canonical(source['url']):
                    raise ValueError('Source feed redirected')
            urls=candidate_urls(html,final,item,source,feed_html=feed_html)
        except (requests.RequestException,ValueError,TypeError,KeyError,OSError):
            self.failure(stage);remember(self.store,item,self.at,stage);return None
        last_failure=None
        for url in urls:
            # Every attempted image, including network/quality failures,
            # consumes one of the existing two image slots for this run.
            if self.reads>=MAX_READS:
                self.stats['deferred']+=1;last_failure=None;break
            self.reads+=1
            stage='image_read'
            try:
                raw,final_image=self.fetcher.image(url)
                if final_image!=url:raise ValueError('Image redirected')
                stage='image_format'
                image=cleaned_photo(raw,poster=item.get('kind')=='event')
                if item.get('kind')=='event':
                    stage='event_text'
                    from .event_image_text import validate as validate_event_text
                    with Image.open(io.BytesIO(image)) as pixels:portrait=pixels.width<pixels.height
                    promotional = validate_event_text(image,item,poster=portrait)
                    stage='visual_subject'
                    from .visual_match import validate_event_photo
                    if not promotional:
                        validate_event_photo(image,expected)
                else:
                    stage='visual_subject'
                    try:
                        validate_news_photo(image,expected)
                    except MatchRejected as rejection:
                        from .visual_match import validate_headline_photo
                        try:
                            validate_headline_photo(image,expected,item['title'])
                        except (ValueError,IllustrationCheckUnavailable):
                            raise rejection
                stage='cache_binding'
                sha=fingerprint(image)
                for previous in self.store.rows('SELECT item_id,payload FROM source_photos WHERE item_id!=?',(item['id'],)):
                    old=json.loads(previous['payload'])
                    if (old.get('image_url')==url or old['sha256']==sha) and not same_event_artwork(old,item):
                        raise ValueError('Photograph reused by another article')
                evidence={'version':EVENT_VERSION if item.get('kind')=='event' else VERSION,'source_id':item['source_id'],'source_url':item['url'],
                          'image_url':url,'title':item['title'],**identity_dates(item),
                          'checked_at':self.at.isoformat(),'subject':expected,'sha256':sha}
                return self.save(item,evidence,image)
            except (MatchUnavailable,IllustrationCheckUnavailable):
                # A missing checker cannot improve on another photograph.
                self.failure(stage,unavailable=True);last_failure='checker_unavailable';break
            except (requests.RequestException,ValueError,TypeError,KeyError,OSError):
                self.failure(stage)
                last_failure='poster_delivery_v2' if stage=='image_read' and reviewed_ticket_source(source) else stage
        if last_failure:remember(self.store,item,self.at,last_failure)
        return None

    def save(self,item,evidence,image):
        photo=key(item['id'],item['revision'],evidence)
        payload=json.dumps(evidence,ensure_ascii=False)
        validate_record(photo,item['id'],item['revision'],payload,image)
        for previous in self.store.rows('SELECT item_id,payload FROM source_photos WHERE item_id!=?',(item['id'],)):
            old=json.loads(previous['payload'])
            if (old['sha256']==evidence['sha256'] or (evidence.get('media_id') and old.get('media_id')==evidence['media_id'])) and not same_event_artwork(old,item):
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
        from .source_photo_retry import clear
        clear(self.store,item)
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
