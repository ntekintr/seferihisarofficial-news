"""Public-safe source-photo evidence. Standard library only for state writes."""
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

from .domain import digest
from .image_safety import validate_jpeg,MAX_CACHE_BYTES,MAX_CACHED_IMAGES

VERSION='source-photo-v1'
FIELDS={'version','source_id','source_url','image_url','title','published_at','checked_at','subject','sha256'}
SUBJECTS=('meeting','flood','traffic')


def key(item_id,revision,evidence):
    # Each new source check is a separate binding. Never refresh the timestamp
    # of evidence already frozen by another publication of the same article.
    return digest(VERSION+item_id+str(revision)+json.dumps(evidence,sort_keys=True,ensure_ascii=False))


def validate_record(photo_id,item_id,revision,payload,image):
    from .security import assert_no_secrets,public_url
    value=json.loads(payload)
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['version']!=VERSION
            or value['subject'] not in SUBJECTS or type(revision) is not int or not 1<=revision<=1000000
            or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{24}',v) for v in (photo_id,item_id))):
        raise ValueError('Invalid source photo record')
    assert_no_secrets(value)
    if (not all(public_url(value[k]) and len(value[k])<=2048 for k in ('source_url','image_url'))
            or urlsplit(value['source_url']).hostname!=urlsplit(value['image_url']).hostname
            or not isinstance(value['source_id'],str) or not re.fullmatch(r'[a-z0-9-]{1,80}',value['source_id'])
            or not isinstance(value['title'],str) or not 8<=len(value['title'])<=240
            or not all(isinstance(value[k],str) and datetime.fromisoformat(value[k]).tzinfo is not None for k in ('checked_at','published_at'))
            or not isinstance(value['sha256'],str) or not re.fullmatch(r'(?:[a-f0-9]{2}:){31}[a-f0-9]{2}',value['sha256'])):
        raise ValueError('Invalid source photo evidence')
    validate_jpeg(image)
    import hashlib
    if hashlib.sha256(image).digest().hex(':')!=value['sha256'] or key(item_id,revision,value)!=photo_id:
        raise ValueError('Source photo fingerprint mismatch')
    return value


def valid_bindings(value):
    return (isinstance(value,dict) and len(value)<=1 and all(
        index=='0' and isinstance(photo,str) and re.fullmatch(r'[a-f0-9]{24}',photo)
        for index,photo in value.items()))
