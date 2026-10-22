"""Public, date-bound duty lists; never medical advice or inferred opening hours."""
from datetime import date, datetime, timedelta
import hashlib
import json
import re

from .brand import VERSION as BRAND, logo_path
from .domain import TZ, digest

VERSION = 'duty-pharmacy-v1'
IZMIR_WEB = 'https://www.izmir.bel.tr/tr/NobetciEczane/27?bolge=SEFER%C4%B0H%C4%B0SAR'
PROFILES = {
    'snail-s-v1': ('seferihisar', 'Seferihisar', 'seferihisarofficial',
        'ntekintr/seferihisarofficial-news', 'https://ntekintr.github.io/seferihisarofficial-news',
        'https://openapi.izmir.bel.tr/api/ibb/nobetcieczaneler', 'İzmir Büyükşehir Belediyesi'),
    'isparta-rose-v1': ('isparta', 'Isparta Merkez', 'ispartaofficial',
        'ispartaofficial/ispartaofficial-news', 'https://ispartaofficial.github.io/ispartaofficial-news',
        'https://www.ispartaeo.org.tr/nobetci-eczaneler', 'Isparta Eczacı Odası'),
}
FIELDS = {'version','brand_version','city','date','source_url','source_name','checked_at','entries','background_sha256'}
ENTRY_FIELDS = {'name','address','phone','region','note'}
STATES = {'prepared','blocked','publishing','published','uncertain'}
RESULTS = {'prepared','published','uncertain','source_unavailable','source_invalid',
           'source_stale','media_not_deployed','account_mismatch','disabled','outside_window'}
MAX_ENTRIES = 12


def profile():
    keys = ('city','label','username','repository','site','source_url','source_name')
    return dict(zip(keys, PROFILES[BRAND]))


def background_path():
    return logo_path().parent / 'pharmacy-background-v1.png'


def background_hash():
    return hashlib.sha256(background_path().read_bytes()).hexdigest()


def validate_bulletin(value):
    p = profile()
    sources = {p['source_url']}
    if p['city'] == 'seferihisar':
        sources.add(IZMIR_WEB)
    if (not isinstance(value,dict) or set(value) != FIELDS or value['version'] != VERSION
            or value['brand_version'] != BRAND or value['city'] != p['city']
            or value['source_url'] not in sources or value['source_name'] != p['source_name']
            or not isinstance(value['background_sha256'],str)
            or not re.fullmatch(r'[a-f0-9]{64}',value['background_sha256'])):
        raise ValueError('Invalid pharmacy bulletin identity')
    day = date.fromisoformat(value['date'])
    checked = datetime.fromisoformat(value['checked_at'])
    if checked.tzinfo is None or checked.astimezone(TZ).date() != day:
        raise ValueError('Duty date and check date differ')
    entries = value['entries']
    if not isinstance(entries,list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise ValueError('Invalid pharmacy list size')
    names = set()
    for e in entries:
        if not isinstance(e,dict) or set(e) != ENTRY_FIELDS:
            raise ValueError('Invalid pharmacy fields')
        for key, minimum, maximum in [('name',3,100),('address',8,240),('region',2,80),('note',0,240)]:
            text = e[key]
            if (not isinstance(text,str) or not minimum <= len(text) <= maximum
                    or any(ord(c) < 32 or c == '\ufffd' for c in text)):
                raise ValueError('Invalid pharmacy text')
        if not isinstance(e['phone'],str) or (e['phone'] and not re.fullmatch(r'0[2-5]\d{9}',e['phone'])):
            raise ValueError('Invalid public business phone')
        if p['city'] == 'isparta' and e['region'] != 'MERKEZ':
            raise ValueError('Outside Isparta centre')
        if p['city'] == 'seferihisar' and e['region'] not in ('SEFERİHİSAR','SIĞACIK','ÜRKMEZ'):
            raise ValueError('Outside Seferihisar')
        key = e['name'].casefold()
        if key in names:
            raise ValueError('Duplicate pharmacy')
        names.add(key)
    from .security import assert_no_secrets
    assert_no_secrets(value)
    return value


def make_bulletin(entries, day, checked_at, *, source_url=None):
    p = profile()
    value = dict(version=VERSION,brand_version=BRAND,city=p['city'],date=day.isoformat(),
                 source_url=source_url or p['source_url'],source_name=p['source_name'],checked_at=checked_at.isoformat(),
                 entries=sorted(entries,key=lambda e:(e['region'],e['name'])),background_sha256=background_hash())
    return validate_bulletin(value)


def fresh(value, at):
    try:
        validate_bulletin(value)
        checked = datetime.fromisoformat(value['checked_at'])
        return (at.tzinfo is not None and value['date'] == at.astimezone(TZ).date().isoformat()
                and at-timedelta(minutes=90) <= checked <= at)
    except (ValueError,TypeError,KeyError):
        return False


def asset_id(value):
    validate_bulletin(value)
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True))


def validate_record(row):
    day,payload,status,checked,result,containers,media,claimed = row
    if (date.fromisoformat(day).isoformat() != day or status not in STATES or result not in RESULTS
            or datetime.fromisoformat(checked).tzinfo is None):
        raise ValueError('Invalid pharmacy story state')
    value = validate_bulletin(json.loads(payload)) if payload else None
    if (value and value['date'] != day) or (not value and status != 'blocked'):
        raise ValueError('Missing or wrong pharmacy day')
    ids = [json.loads(v) for v in (containers,media)]
    if any(not isinstance(v,list) or len(v)>MAX_ENTRIES for v in ids):
        raise ValueError('Invalid pharmacy publication parts')
    if any(not isinstance(x,str) or not re.fullmatch(r'\d{1,32}',x) for v in ids for x in v):
        raise ValueError('Invalid pharmacy media id')
    if len(ids[1]) > len(ids[0]):
        raise ValueError('Pharmacy media without container')
    if status in ('publishing','published','uncertain'):
        stamp = datetime.fromisoformat(claimed) if claimed else None
        if stamp is None or stamp.tzinfo is None or stamp.astimezone(TZ).date().isoformat()!=day:
            raise ValueError('Invalid pharmacy claim timestamp')
    if status == 'published' and (not ids[1] or len(ids[0]) != len(ids[1])):
        raise ValueError('Incomplete pharmacy delivery')
    from .security import assert_no_secrets
    assert_no_secrets(row)
