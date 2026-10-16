"""Keep institutional source copy from speaking on behalf of the news account.

Only reviewed possessive forms are converted. Unknown first-person statements
remain explicit source quotations; facts, names, numbers and commitments are
never inferred. Existing direct quotations are kept verbatim.
"""
from __future__ import annotations

import re


_FORMS = {
    'başkanımız': 'başkanı', 'başkanımızın': 'başkanının', 'başkanımıza': 'başkanına',
    'başkanımızla': 'başkanıyla', 'başkanımızı': 'başkanını',
    'cumhurbaşkanımız': 'cumhurbaşkanı', 'cumhurbaşkanımızın': 'cumhurbaşkanının',
    'belediyemiz': 'belediye', 'belediyemizin': 'belediyenin', 'belediyemizde': 'belediyede',
    'belediyemize': 'belediyeye', 'belediyemizden': 'belediyeden',
    'ilçemiz': 'ilçe', 'ilçemizin': 'ilçenin', 'ilçemizde': 'ilçede', 'ilçemize': 'ilçeye',
    'mahallelerimiz': 'mahalleler', 'mahallelerimizin': 'mahallelerin',
    'mahallelerimizde': 'mahallelerde', 'mahallelerimize': 'mahallelere',
    'vatandaşlarımız': 'vatandaşlar', 'vatandaşlarımızın': 'vatandaşların',
    'vatandaşlarımızdan': 'vatandaşlardan', 'vatandaşlarımıza': 'vatandaşlara',
    'muhtarımızla': 'muhtarıyla', 'muhtarlarımız': 'muhtarlar', 'muhtarlarımızla': 'muhtarlarla',
    'muhtarlarımızın': 'muhtarların',
    'çalışanlarımız': 'çalışanlar', 'çalışanlarımızın': 'çalışanların',
    'gençlerimiz': 'gençler', 'gençlerimizin': 'gençlerin',
    'çocuklarımız': 'çocuklar', 'çocuklarımızın': 'çocukların',
    'kurumumuz': 'kurum', 'kurumumuzun': 'kurumun', 'kurumumuzda': 'kurumda',
    'hastanemiz': 'hastane', 'hastanemizin': 'hastanenin', 'hastanemizde': 'hastanede',
    'ekibimiz': 'ekip', 'ekibimizin': 'ekibin',
}
_TERM = re.compile(r'\b(?:' + '|'.join(sorted(_FORMS, key=len, reverse=True)) + r')\b', re.I)
_QUOTE = re.compile(r'“[^”\n]*”|"[^"\n]*"|«[^»\n]*»')
_FIRST_PERSON = re.compile(
    r'\b(?:biz|bizim|bize|bizden|bizler|ben|benim|bana|benden)\b|'
    r'\b\w*(?:yoruz|acağız|eceğiz|dığımız|diğimiz|duğumuz|düğümüz)\b|'
    r'\b\w*(?:ımız|imiz|umuz|ümüz)(?:ın|in|un|ün|a|e|ı|i|u|ü|da|de|dan|den|la|le)?\b|'
    r'\b(?:düzenledik|gerçekleştirdik|buluştuk|katıldık|açtık|yaptık|sunduk|karşıladık|başlattık)\b', re.I)


def _outside_quotes(text, transform):
    parts, start = [], 0
    for match in _QUOTE.finditer(text):
        parts.extend((transform(text[start:match.start()]), match.group()))
        start = match.end()
    parts.append(transform(text[start:]))
    return ''.join(parts)


def source_voice(text):
    return bool(_FIRST_PERSON.search(_QUOTE.sub('', text)))


def neutral_terms(text):
    def replace(match):
        original = match.group()
        key = original.replace('İ','i').replace('I','ı').lower()
        value = _FORMS.get(key)
        if value is None:  # Python's Unicode IGNORECASE also matches dotless variants.
            value = next(v for k,v in _FORMS.items() if re.fullmatch(k,original,re.I))
        if key.startswith('başkanımız') and not re.search(r'\b(?:ilçe|belediye|il|dernek|oda|vakıf|parti|sendika|federasyon)\s+$',match.string[:match.start()],re.I):
            value={'başkanımız':'başkan','başkanımızın':'başkanın','başkanımıza':'başkana',
                   'başkanımızla':'başkanla','başkanımızı':'başkanı'}.get(key,value)
        if key=='muhtarımızla' and not re.search(r'\bmahalle\s+$',match.string[:match.start()],re.I):
            value='muhtarla'
        if original.isupper():
            return value.replace('i','İ').replace('ı','I').upper()
        return value[0].upper()+value[1:] if original[0].isupper() else value
    def transform(value):
        value = _TERM.sub(replace,value)
        # An honorific is not part of the person's identity or role.
        return re.sub(r'(\b(?:başkanı|başkan|cumhurbaşkanı)\s+)Sayın\s+',r'\1',value,flags=re.I)
    return _outside_quotes(text,transform)


def neutral_title(title):
    value = neutral_terms(title)
    # Do not turn an unrecognized first-person claim into a new factual claim.
    return 'Kaynak duyurusu: “'+title+'”' if source_voice(value) else value


def neutral_body(text):
    quotes = [(m.start(),m.end()) for m in _QUOTE.finditer(text)]
    sentences, start = [], 0
    for boundary in re.finditer(r'(?<=[.!?])\s+',text):
        if any(begin <= boundary.start() < end for begin,end in quotes):
            continue
        sentences.append(text[start:boundary.start()])
        start = boundary.end()
    sentences.append(text[start:])
    result = []
    for original in sentences:
        if not re.search(r'\w',original):
            continue
        # Remove only the reviewed, non-factual campaign closing. Other unknown
        # claims stay attributed quotations rather than being silently lost.
        outside = _QUOTE.sub('',original).casefold()
        closing = re.sub(r'^[^\w]+|[^\w]+$','',outside).replace('’',"'")
        if closing == "seferihisar'ımızın tüm mahalleleri için omuz omuza çalışmaya, sorunların takipçisi olmaya devam edeceğiz":
            continue
        value = neutral_terms(original)
        if source_voice(value):
            value = 'Kaynak açıklamasında “'+original+'” denildi.'
        result.append(value)
    return ' '.join(result)
