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
SUBJECTS=('meeting','flood','traffic','citrus_harvest')
EVENT_SUBJECTS=('theatre','concert','cinema','festival','culture','family','sport','market','food','education','yoga','tile_art','workshop')


def key(item_id,revision,evidence):
    # Each new source check is a separate binding. Never refresh the timestamp
    # of evidence already frozen by another publication of the same article.
    return digest(evidence.get('version',VERSION)+item_id+str(revision)+json.dumps(evidence,sort_keys=True,ensure_ascii=False))


def validate_evidence(value):
    from .security import assert_no_secrets,public_url
    if not isinstance(value,dict):raise ValueError('Invalid source photo evidence')
    instagram=value.get('version')==INSTAGRAM_VERSION
    event=value.get('version')==EVENT_VERSION
    if (set(value)!=(EVENT_FIELDS if event else INSTAGRAM_FIELDS if instagram else FIELDS)
            or value['version'] not in (VERSION,INSTAGRAM_VERSION,EVENT_VERSION)
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
    if event and datetime.fromisoformat(value['end']) < datetime.fromisoformat(value['start']):
        raise ValueError('Invalid event photograph interval')
    if instagram:
        parts=urlsplit(value['source_url'])
        if (parts.hostname!='www.instagram.com' or parts.query or parts.fragment
                or not re.fullmatch(r'/p/[a-zA-Z0-9_-]{5,40}/',parts.path)
                or not isinstance(value['media_id'],str) or not re.fullmatch(r'\d{8,32}',value['media_id'])):
            raise ValueError('Invalid Instagram photograph identity')
    elif (not public_url(value['image_url']) or len(value['image_url'])>2048
          or urlsplit(value['source_url']).hostname!=urlsplit(value['image_url']).hostname):
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
