"""Public-safe source-photo evidence. Standard library only for state writes."""
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from .domain import digest
from .image_safety import validate_jpeg,MAX_CACHE_BYTES,MAX_CACHED_IMAGES

VERSION='source-photo-v1'
INSTAGRAM_VERSION='source-photo-instagram-v1'
EVENT_VERSION='source-photo-event-v1'
FIELDS={'version','source_id','source_url','image_url','title','published_at','checked_at','subject','sha256'}
INSTAGRAM_FIELDS=(FIELDS-{'image_url'})|{'media_id'}
EVENT_FIELDS=(FIELDS-{'published_at'})|{'start','end'}
# Another source's photograph of this same story. The record stays bound to the
# story that shows it and names the page and publisher the picture came from.
STORY_VERSION='source-photo-story-v1'
STORY_FIELDS=FIELDS|{'photo_source_id','photo_source_name','photo_url'}
# Current news outside the reviewed topics: the publisher's own photo of this
# exact article, checked as a photograph rather than against a topic label.
ARTICLE_PHOTO='article_photo'
SUBJECTS=(ARTICLE_PHOTO,'meeting','flood','traffic','citrus_harvest','roadworks','hiking','glass_litter','football','landscape','parking','bus','electrical','water_utility','weather_sky','land_planning','education','health_workspace','public_service','food','market','concert','theatre','cinema','festival','culture','animal_care','citrus_processing','public_park')
EVENT_SUBJECTS=('theatre','concert','cinema','festival','culture','family','sport','market','food','education','yoga','tile_art','workshop','event_poster','electrical','water_utility')

IMAGE_ORIGINS = {
    'bubilet': ('www.bubilet.com.tr', 'cdn.bubilet.com.tr', r'/cdn-cgi/image/width=\d{2,4},quality=\d{2,3}/files/Etkinlik/[A-Za-z0-9_.-]+\.(?:jpe?g|png|webp)'),
    'bubilet-bademler': ('www.bubilet.com.tr', 'cdn.bubilet.com.tr', r'/cdn-cgi/image/width=\d{2,4},quality=\d{2,3}/files/Etkinlik/[A-Za-z0-9_.-]+\.(?:jpe?g|png|webp)'),
}


def approved_image_url(source_id, source_url, image_url):
    from .security import public_url
    if not public_url(image_url) or len(image_url) > 2048:
        return False
    page, image = urlsplit(source_url), urlsplit(image_url)
    if image.hostname == page.hostname:
        return True
    origin = IMAGE_ORIGINS.get(source_id)
    return bool(origin and page.hostname == origin[0] and image.hostname == origin[1]
                and not image.query and not image.fragment
                and not any(part in ('.', '..') for part in image.path.split('/'))
                and re.fullmatch(origin[2], image.path, re.I))


def key(item_id,revision,evidence):
    # Each new source check is a separate binding. Never refresh the timestamp
    # of evidence already frozen by another publication of the same article.
    return digest(evidence.get('version',VERSION)+item_id+str(revision)+json.dumps(evidence,sort_keys=True,ensure_ascii=False))


def validate_evidence(value):
    from .security import assert_no_secrets,public_url
    if not isinstance(value,dict):raise ValueError('Invalid source photo evidence')
    instagram=value.get('version')==INSTAGRAM_VERSION
    event=value.get('version')==EVENT_VERSION
    story=value.get('version')==STORY_VERSION
    if (set(value)!=(EVENT_FIELDS if event else INSTAGRAM_FIELDS if instagram else STORY_FIELDS if story else FIELDS)
            or value['version'] not in (VERSION,INSTAGRAM_VERSION,EVENT_VERSION,STORY_VERSION)
            or value['subject'] not in (EVENT_SUBJECTS if event else SUBJECTS)):
        raise ValueError('Invalid source photo evidence')
    assert_no_secrets(value)
    if (not public_url(value['source_url']) or len(value['source_url'])>2048
            or not isinstance(value['source_id'],str) or not re.fullmatch(r'[a-z0-9-]{1,80}',value['source_id'])
            or not isinstance(value['title'],str) or not 8<=len(value['title'])<=240
            or not all(isinstance(value[k],str) and datetime.fromisoformat(value[k]).tzinfo is not None
                       for k in (('checked_at','start','end') if event else ('checked_at','published_at')))
            or not isinstance(value['sha256'],str) or not re.fullmatch(r'(?:[a-f0-9]{2}:){31}[a-f0-9]{2}',value['sha256'])):
        raise ValueError('Invalid source photo evidence')
    if story and (not public_url(value['photo_url']) or len(value['photo_url'])>2048
                  or not isinstance(value['photo_source_id'],str) or not re.fullmatch(r'[a-z0-9-]{1,80}',value['photo_source_id'])
                  or not isinstance(value['photo_source_name'],str) or not 2<=len(value['photo_source_name'])<=120):
        raise ValueError('Invalid same-story photograph identity')
    if event and datetime.fromisoformat(value['end']) < datetime.fromisoformat(value['start']):
        raise ValueError('Invalid event photograph interval')
    if instagram:
        parts=urlsplit(value['source_url'])
        if (parts.hostname!='www.instagram.com' or parts.query or parts.fragment
                or not re.fullmatch(r'/p/[a-zA-Z0-9_-]{5,40}/',parts.path)
                or not isinstance(value['media_id'],str) or not re.fullmatch(r'\d{8,32}',value['media_id'])):
            raise ValueError('Invalid Instagram photograph identity')
    elif (not public_url(value['image_url']) or len(value['image_url'])>2048
          or not approved_image_url(*((value['photo_source_id'],value['photo_url']) if story
                                      else (value['source_id'],value['source_url'])),value['image_url'])):
        raise ValueError('Invalid article photograph identity')
    return value


def validate_record(photo_id,item_id,revision,payload,image):
    value=validate_evidence(json.loads(payload))
    if (type(revision) is not int or not 1<=revision<=1000000
            or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{24}',v) for v in (photo_id,item_id))):
        raise ValueError('Invalid source photo record')
    validate_jpeg(image)
    import hashlib
    if hashlib.sha256(image).digest().hex(':')!=value['sha256'] or key(item_id,revision,value)!=photo_id:
        raise ValueError('Source photo fingerprint mismatch')
    return value


def valid_bindings(value):
    return (isinstance(value,dict) and len(value)<=1 and all(
        index=='0' and isinstance(photo,str) and re.fullmatch(r'[a-f0-9]{24}',photo)
        for index,photo in value.items()))


def reviewed_ticket_source(source):
    return (source.get('id') in ('bubilet','bubilet-bademler','bubilet-isparta')
            and urlsplit(source.get('url','')).hostname == 'www.bubilet.com.tr'
            and (source.get('kind') == 'ticketing' or source.get('reader') == 'ticketing'))


def delivery_sources(sources):
    # A reviewed CDN with HTTP 404/410 robots has no published robot rules.
    # Existing disallow rules, 403/429/5xx, redirects, TLS and MIME checks stay
    # closed. This opt-in does not apply to any other publisher/CDN.
    return [{'enabled':True,'url':'https://'+origin[1]+'/',
             'allow_missing_robots': origin[1]=='cdn.bubilet.com.tr' and reviewed_ticket_source(sources[sid])}
            for sid,origin in IMAGE_ORIGINS.items() if sid in sources
            and urlsplit(sources[sid]['url']).hostname==origin[0]]


def same_event_artwork(evidence,item):
    # A provider's date-free poster can belong to several exact sessions of
    # the same show. Each new session still needs source binding AND OCR.
    from .domain import normalized
    if (evidence.get('version')!=EVENT_VERSION or item.get('kind')!='event'
            or evidence.get('source_id')!=item.get('source_id')
            or item.get('source_id') not in ('bubilet','bubilet-bademler','bubilet-isparta')
            or evidence.get('subject')!=photo_subject_for_reuse(item)
            or normalized(evidence.get('title',''))!=normalized(item.get('title',''))):
        return False
    a,b=urlsplit(evidence.get('source_url','')),urlsplit(item.get('url',''))
    pattern=r'/[^/]+/etkinlik/[a-z0-9-]+/seans/\d+'
    return (a.hostname==b.hostname=='www.bubilet.com.tr' and not a.query and not b.query
            and re.fullmatch(pattern,a.path) and re.fullmatch(pattern,b.path)
            and a.path.rsplit('/seans/',1)[0]==b.path.rsplit('/seans/',1)[0])


def own_photo(evidence,item):
    # Another story's card borrowed this file; it stays the publisher's own.
    return evidence.get('version')==STORY_VERSION and evidence.get('photo_url')==item.get('url')


def photo_subject_for_reuse(item):
    from .source_photos import photo_subject
    return photo_subject(item)
