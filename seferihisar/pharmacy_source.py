"""Read only the reviewed municipal/Chamber source; no cached search snippets."""
from datetime import datetime
import json
import re
from bs4 import BeautifulSoup

from .domain import TZ
from .pharmacy_data import make_bulletin, profile

MONTHS = ('ocak','şubat','mart','nisan','mayıs','haziran','temmuz','ağustos','eylül','ekim','kasım','aralık')


def clean(value):
    if not isinstance(value,str):
        raise ValueError('Missing pharmacy source field')
    return ' '.join(value.split())


def phone(value):
    value = clean(value or '')
    digits = re.sub(r'[\s()+-]','',value)
    if digits.startswith('90') and len(digits)==12:
        digits='0'+digits[2:]
    if digits and not re.fullmatch(r'0[2-5]\d{9}',digits):
        raise ValueError('Unclear pharmacy phone')
    return digits


def parse_izmir(body, at):
    data = json.loads(body)
    if not isinstance(data,list) or len(data)>500:
        raise ValueError('Invalid official pharmacy response')
    entries = []
    for row in data:
        if not isinstance(row,dict):
            raise ValueError('Invalid official pharmacy row')
        region = clean(row.get('Bolge',''))
        if region == 'SEFERİHİSAR':
            area = 'SEFERİHİSAR'
        elif region == 'SEFERİHİSAR-SIĞACIK BÖLGESİ':
            area = 'SIĞACIK'
        elif region in ('ÜRKMEZ','GÜMÜLDÜR-ÜRKMEZ') and re.search(r'BENGİLER|DOĞANBEY|ÜRKMEZ|SEFERİHİSAR',row.get('Adres','')):
            area = 'ÜRKMEZ'
        else:
            continue  # Gümüldür/Menderes and all other districts stay outside.
        if datetime.fromisoformat(row['Tarih']).date() != at.astimezone(TZ).date():
            raise ValueError('Official duty date is stale')
        entries.append(dict(name=clean(row['Adi']),address=clean(row['Adres']),
                            phone=phone(row.get('Telefon','')),region=area,note=clean(row.get('BolgeAciklama',''))))
    return make_bulletin(entries,at.astimezone(TZ).date(),at)


def parse_isparta(body, at):
    soup = BeautifulSoup(body,'html.parser')
    labels = [h.get_text(' ',strip=True) for h in soup.select('h3') if 'Bugün Nöbetçi Eczaneler' in h.get_text()]
    if len(labels)!=1:
        raise ValueError('Missing official duty heading')
    match = re.fullmatch(r'(\d{1,2}) (\w+) (20\d{2}) Bugün Nöbetçi Eczaneler',labels[0])
    if not match or match[2].casefold() not in MONTHS:
        raise ValueError('Missing explicit duty date')
    duty = datetime(int(match[3]),MONTHS.index(match[2].casefold())+1,int(match[1]),tzinfo=TZ).date()
    if duty != at.astimezone(TZ).date():
        raise ValueError('Official duty date is stale')
    # Input defaults/header site dates elsewhere cannot override this duty heading.
    entries = []
    for block in soup.select('.trend-content'):
        area = block.find('h5')
        if not area or area.get_text(' ',strip=True) != 'MERKEZ':
            continue
        name = block.find('h3'); ps=block.find_all('p',recursive=False)
        if not name or len(ps)!=2:
            raise ValueError('Incomplete centre pharmacy')
        address = ps[0].get_text(' ',strip=True)
        # Exclude map-link text from the actual pharmacy's phone paragraph.
        number = ' '.join(ps[1].find_all(string=True,recursive=False)).strip()
        entries.append(dict(name=clean(name.get_text(' ',strip=True)),address=clean(address),
                            phone=phone(number),region='MERKEZ',note=''))
    return make_bulletin(entries,duty,at)


def fetch_bulletin(at, fetcher=None):
    p=profile()
    if fetcher is None:
        from .collect import Fetcher
        # Official anonymous API documentation was reviewed; its robots.txt is
        # explicitly absent (404). 403, TLS, server errors remain hard failures.
        fetcher=Fetcher([{'url':p['source_url'],'enabled':True,
                          'allow_missing_robots':p['city']=='seferihisar'}])
    body,_=fetcher.get(p['source_url'])
    from .domain import now
    checked=now()
    if checked.astimezone(TZ).date()!=at.astimezone(TZ).date():
        raise ValueError('Source read crossed duty date')
    return (parse_izmir if p['city']=='seferihisar' else parse_isparta)(body,checked)


def main():
    """One explicit cloud preflight; no state restoration, credentials or posts."""
    import argparse
    from pathlib import Path
    from .domain import now
    from .pharmacy_render import render
    from .security import validate_public
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true',required=True)
    parser.parse_args()
    value=fetch_bulletin(now());target=Path('work/pharmacy-preview')
    cards=render(value,target,preview=True)
    proof={'preview_only':True,'publication_attempted':False,'bulletin':value,**cards}
    (target/'data.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    validate_public(target)
    print(json.dumps({'date':value['date'],'pharmacies':len(value['entries']),'source':value['source_url'],
                      'preview_only':True,'publication_attempted':False}))


if __name__=='__main__':main()
