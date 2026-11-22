"""Owner rule, 22 Nov 2026: power cuts and theatre only when in Seferihisar.

"Seferihisar için planlı elektrik kesintileri sadece Seferihisar için olanlar
paylaşılsın urla Güzelbahçe vs olmasın. Tiyatro Seferihisar da varsa
paylaşılsın başka ilçe tiyatroları vs paylaşılmasın."

Other nearby content (concerts, festivals, roads, weather) keeps the existing
`domain.local` rule. An unclear place is not published (safe side).
Standard library only: the state writer may import this module.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .domain import normalized

# Seferihisar district: TÜİK neighbourhood list (citypopulation.de, 2022) plus
# the Ürkmez/Doğanbey settlements, Akarca (GDZ, Wikipedia) and the Teos site.
# Only names that are distinctive are evidence; Atatürk, Cumhuriyet, Tepecik,
# Turgut, Düzce, Payamlı (also a Güzelbahçe neighbourhood in GDZ) or Beyler
# are common elsewhere and prove nothing on their own.
EVIDENCE = ('seferihisar', 'sığacık', 'sigacik', 'ürkmez', 'urkmez', 'doğanbey', 'doganbey',
            'teos', 'gödence', 'godence', 'ulamış', 'ulamis', 'bengiler', 'kavakdere',
            'orhanlı', 'orhanli', 'mersin alanı', 'mersinalanı', 'çolak ibrahim bey', 'çolakibrahimbey')
# Seferihisar names that contain another place's name.
OWN_COMPOUNDS = ('mersin alanı', 'mersinalanı')
IZMIR_DISTRICTS = ('aliağa', 'balçova', 'bayındır', 'bayraklı', 'bergama', 'beydağ', 'bornova',
                   'buca', 'çeşme', 'çiğli', 'dikili', 'foça', 'gaziemir', 'güzelbahçe', 'karabağlar',
                   'karaburun', 'karşıyaka', 'kemalpaşa', 'kınık', 'kiraz', 'konak', 'menderes',
                   'menemen', 'narlıdere', 'ödemiş', 'selçuk', 'tire', 'torbalı', 'urla')
NEARBY_LOCALITIES = ('guzelbahce', 'özdere', 'ozdere', 'gümüldür', 'gumuldur', 'yelki', 'bademler',
                     'çamlıçay', 'kuşçular', 'zeytineli', 'balıklıova', 'gülbahçe', 'kuşadası')
# Other provinces (touring shows); İzmir itself and Düzce (also a Seferihisar
# neighbourhood) are left out.
PROVINCES = ('adana', 'adıyaman', 'afyon', 'afyonkarahisar', 'ağrı', 'aksaray', 'amasya', 'ankara',
             'antalya', 'ardahan', 'artvin', 'aydın', 'balıkesir', 'bartın', 'batman', 'bayburt',
             'bilecik', 'bingöl', 'bitlis', 'bolu', 'burdur', 'bursa', 'çanakkale', 'çankırı', 'çorum',
             'denizli', 'diyarbakır', 'edirne', 'elazığ', 'erzincan', 'erzurum', 'eskişehir',
             'gaziantep', 'giresun', 'gümüşhane', 'hakkari', 'hatay', 'ığdır', 'isparta', 'istanbul',
             'kahramanmaraş', 'karabük', 'karaman', 'kars', 'kastamonu', 'kayseri', 'kırıkkale',
             'kırklareli', 'kırşehir', 'kilis', 'kocaeli', 'konya', 'kütahya', 'malatya', 'manisa',
             'mardin', 'mersin', 'muğla', 'muş', 'nevşehir', 'niğde', 'ordu', 'osmaniye', 'rize',
             'sakarya', 'samsun', 'siirt', 'sinop', 'sivas', 'şanlıurfa', 'şırnak', 'tekirdağ', 'tokat',
             'trabzon', 'tunceli', 'uşak', 'van', 'yalova', 'yozgat', 'zonguldak', 'kıbrıs', 'lefkoşa')
FOREIGN = IZMIR_DISTRICTS + NEARBY_LOCALITIES + PROVINCES
# A street or a person named after a place is not that place.
STREET = r'(?:cad\w*|cd|bulvar\w*|blv\w*|bul|sok\w*|sk|yolu)\b'

OUTAGE_NOTICE = re.compile(r'kesinti|kesilece|kesilme|enerji verilemeyece|elektriksiz')
THEATRE_TEXT = re.compile(r'\btiyatro\w*|\bmüzikal\w*|\bçocuk oyunu\b|\bsahne oyunu\b|\bstand ?up\b')

REASONS = ('outage_outside_district', 'outage_mixed_districts',
           'theatre_outside_district', 'theatre_location_unconfirmed')


def _words(values):
    return tuple(normalized(v) for v in values)


_EVIDENCE, _OWN, _FOREIGN = _words(EVIDENCE), _words(OWN_COMPOUNDS), _words(FOREIGN)


def _has(value, names):
    return any(re.search(r'\b' + re.escape(name) + r'\b', value) for name in names)


def seferihisar(text: str) -> bool:
    return _has(normalized(text or ''), _EVIDENCE)


def foreign(text: str) -> bool:
    value = normalized(text or '')
    for own in _OWN:
        value = re.sub(r'\b' + re.escape(own) + r'\b', ' ', value)
    for name in _FOREIGN:
        for match in re.finditer(r'\b' + re.escape(name) + r'\b', value):
            before, after = value[:match.start()].split()[-1:], value[match.end():]
            if before == ['adnan'] or re.match(r'\s+' + STREET, after):
                continue
            return True
    return False


def theatre_like(item: dict) -> bool:
    if item.get('category') == 'theatre':
        return True
    if item.get('kind') != 'event':
        return False
    # Biletinial files every stage show (plays, children's plays, stand-up)
    # under its /tiyatro/ section, whatever the factory's category says.
    for key in ('url', 'ticket_url'):
        value = item.get(key)
        if isinstance(value, str) and '/tiyatro/' in urlsplit(value).path.casefold():
            return True
    return bool(THEATRE_TEXT.search(normalized(item.get('title', '') + ' ' + item.get('description', ''))))


def outage_notice(item: dict) -> bool:
    return item.get('category') == 'outage' and (
        item.get('kind') == 'event'
        or bool(OUTAGE_NOTICE.search(normalized(item.get('title', '') + ' ' + item.get('description', '')))))


def _outage_reason(item):
    if item.get('kind') == 'event':
        location = item.get('location') or ''
        place = location.split(' · ', 1)[0]
        # GDZ records name their district first: "Urla · Altıntaş, Yaka".
        if ' · ' in location and normalized(place) == 'seferihisar':
            return None
        text = item.get('title', '') + '\n' + location
        if foreign(text) or not seferihisar(text):
            return 'outage_outside_district'
        return None
    title, lines = item.get('title', ''), (item.get('description') or '').splitlines()
    if not seferihisar(title) and not any(seferihisar(line) for line in lines):
        return 'outage_outside_district'
    if foreign(title) or any(foreign(line) for line in lines):
        return 'outage_mixed_districts'
    return None


def _theatre_reason(item):
    if item.get('kind') == 'event':
        # The venue decides; a district named in the play's blurb does not.
        text = item.get('location') or ''
    else:
        # News: a Seferihisar headline decides; otherwise the whole text.
        title = item.get('title', '')
        if seferihisar(title) and not foreign(title):
            return None
        text = title + '\n' + (item.get('description') or '')
    if foreign(text):
        return 'theatre_outside_district'
    if not seferihisar(text):
        return 'theatre_location_unconfirmed'
    return None


def reason(item: dict | None) -> str | None:
    """Why an item is outside the owner's district rule, or None."""
    if not item:
        return None
    if outage_notice(item):
        return _outage_reason(item)
    if theatre_like(item):
        return _theatre_reason(item)
    return None


def scope(item: dict) -> dict:
    """Keep only the Seferihisar lines of a multi-district power-cut notice.

    Lines naming another district are dropped. A notice whose title or a
    single line names both Seferihisar and another district cannot be split
    without rewriting the source, so it is left as is and `reason` withholds it.
    """
    if not outage_notice(item) or item.get('kind') != 'news' or foreign(item.get('title', '')):
        return item
    lines = (item.get('description') or '').splitlines()
    if not any(seferihisar(line) and not foreign(line) for line in lines):
        return item
    if any(seferihisar(line) and foreign(line) for line in lines):
        return item
    kept = [line for line in lines if not foreign(line)]
    if len(kept) == len(lines):
        return item
    return {**item, 'description': '\n'.join(kept).strip()}


def post_reason(post: dict, items: dict[str, dict]) -> str | None:
    """A queued card for, or a digest naming, an out-of-district item."""
    from .schedule import post_references
    for item in post_references(post, items):
        if found := reason(item):
            return found
    return None
