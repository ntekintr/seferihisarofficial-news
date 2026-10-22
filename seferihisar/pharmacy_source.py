"""Read only the reviewed municipal/Chamber source; no cached search snippets."""
from datetime import datetime
import json
import re
from bs4 import BeautifulSoup
import requests

from .domain import TZ
from .pharmacy_data import IZMIR_WEB, make_bulletin, profile

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


def parse_izmir_web(body, at):
    """Official filtered page: every pharmacy has an explicit start/end date."""
    soup = BeautifulSoup(body, 'html.parser')
    selected = soup.select('select[name="Bolgeler"] option[selected]')
    if len(selected) != 1 or clean(selected[0].get_text()) != 'SEFERİHİSAR':
        raise ValueError('Official region filter was not applied')
    if any('page=' in a.get('href', '') for a in soup.select('a[href]')):
        raise ValueError('Incomplete paginated official pharmacy list')
    blocks = soup.select('.nobetci-eczane')
    if not blocks or len(blocks) > 12:
        raise ValueError('Missing official pharmacy cards')
    entries = []
    for block in blocks:
        name = block.select_one('.nobetci-eczane-adress > h2')
        address = block.select_one('.nobetci-eczane-place')
        if not name or not address:
            raise ValueError('Incomplete official pharmacy card')
        address = clean(address.get_text(' ',strip=True))
        if not address.endswith(' SEFERİHİSAR'):
            raise ValueError('Outside the verified Seferihisar district')
        dates = {}
        for paragraph in block.select('.nobetci-eczane-adress > p'):
            label = paragraph.find('strong',recursive=False)
            if label:
                key = clean(label.get_text()).rstrip(' :')
                if key in ('Başlangıç','Bitiş'):
                    if key in dates: raise ValueError('Ambiguous official duty dates')
                    text = clean(' '.join(paragraph.find_all(string=True,recursive=False)))
                    dates[key] = datetime.strptime(text,'%d-%m-%Y %H:%M:%S').replace(tzinfo=TZ)
        if set(dates) != {'Başlangıç','Bitiş'}:
            raise ValueError('Missing explicit official duty interval')
        start,end = dates['Başlangıç'],dates['Bitiş']
        if (start.date() != at.astimezone(TZ).date() or end <= start or end <= at
                or (end-start).total_seconds() > 36*3600):
            raise ValueError('Official duty interval is stale or invalid')
        number = block.select_one('.eczane-tel')
        number = phone(number.get('href','').removeprefix('tel:')) if number else ''
        note = clean(' '.join(p.get_text(' ',strip=True) for p in block.select('.eczane-ozel-durum')))
        hours = f"Nöbet: {start:%d.%m %H:%M} – {end:%d.%m %H:%M}"
        area = ('SIĞACIK' if re.search(r'SIĞACIK|SIGACIK',address) else
                'ÜRKMEZ' if re.search(r'BENGİLER|DOĞANBEY|ÜRKMEZ',address) else 'SEFERİHİSAR')
        entries.append(dict(name=clean(name.get_text(' ',strip=True)),address=address,
                            phone=number,region=area,note=hours+(' · '+note if note else '')))
    return make_bulletin(entries,at.astimezone(TZ).date(),at,source_url=IZMIR_WEB)


def fetch_bulletin(at, fetcher=None):
    p=profile()
    if fetcher is None:
        from .collect import Fetcher
        # Official anonymous API documentation was reviewed; its robots.txt is
        # explicitly absent (404). 403, TLS, server errors remain hard failures.
        sources=[{'url':p['source_url'],'enabled':True,
                  'allow_missing_robots':p['city']=='seferihisar'}]
        if p['city']=='seferihisar':
            # This official public page also returned robots.txt 404 on review.
            # Only explicit absence is allowed, never TLS/403/robots denials.
            sources.append({'url':IZMIR_WEB,'enabled':True,'allow_missing_robots':True})
        fetcher=Fetcher(sources)
    parser = parse_izmir if p['city']=='seferihisar' else parse_isparta
    try:
        body,_=fetcher.get(p['source_url'])
    except requests.exceptions.SSLError:
        raise
    except (requests.exceptions.Timeout,requests.exceptions.ConnectionError):
        if p['city']!='seferihisar': raise
        body,_=fetcher.get(IZMIR_WEB)
        parser=parse_izmir_web
    from .domain import now
    checked=now()
    if checked.astimezone(TZ).date()!=at.astimezone(TZ).date():
        raise ValueError('Source read crossed duty date')
    return parser(body,checked)


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
