"""Reviewed public service and event readers; explicit dates and venue locality."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .collect import MONTHS, detail_error_code, objects, page_url, publication_date, structured, text
from .domain import TZ, canonical, category, digest, local, normalized, now, parse_date
from .security import contains_secret, public_url

EVENT_CATEGORIES = {'concert','festival','theatre','cinema','family','sport','market','culture','event','food','education'}
UUID = re.compile(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}')


def official_notice_items(body, base, source):
    """Reviewed governorate body/date fields; image-only warnings stay with MGM."""
    soup = BeautifulSoup(body, 'html.parser')
    heading, article = soup.select_one('h2.page-title'), soup.select_one('.icerik')
    stamp = publication_date(soup, source)
    if heading is None or article is None or stamp is None:
        return []
    for node in article.select('script,style,nav,footer'):
        node.decompose()
    title, description = text(heading), text(article)[:3000]
    topic = category(title + ' ' + description)
    if not description or not local(title + ' ' + description) or topic in ('weather','outage'):
        return []
    return [news(source,base,title,description,stamp,topic)]


def _gdz_name(value):
    return re.sub(r'\s+', ' ', value.replace('İ','i').casefold()).strip() if isinstance(value,str) else ''


def gdz_planned_items(body, base, source, district, at, known_events=()):
    """Verified service intervals, not invented article publication timestamps."""
    data = json.loads(body)
    if (not isinstance(data,dict) or data.get('success') is not True
            or data.get('level')!='district_outages' or _gdz_name(data.get('city'))!='izmir'
            or _gdz_name(data.get('district'))!=_gdz_name(district)
            or not isinstance(data.get('data'),list) or len(data['data'])>500
            or type(data.get('count')) is not int or data['count']!=len(data['data'])):
        raise ValueError('Expected reviewed GDZ district collection')
    display = source['display_url']
    results = []
    for row in data['data']:
        if not isinstance(row,dict) or contains_secret(row):
            continue
        identifier = row.get('Kesinti_ID')
        if (not isinstance(identifier,str) or not re.fullmatch(r'\d{1,12}',identifier)
                or _gdz_name(row.get('Sehir'))!='izmir'
                or _gdz_name(row.get('Ilce'))!=_gdz_name(district)):
            continue
        state = row.get('Durum')
        if state not in ('Planlandı','Başladı','Planlı Kesinti İptal Edildi','Arşivlendi'):
            continue
        # This route also returns archived/cancelled records and may contain
        # incidental outages. Only explicit full planned intervals are usable.
        stamps = [row.get('Planlanan_Baslangic_Zamani'),row.get('Planlanan_Sona_Erme_Zamani')]
        if not all(isinstance(v,str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?',v) for v in stamps):
            continue
        identity = canonical(display)+'#'+identifier
        known = any(e.get('source_id')==source['id'] and e.get('identity')==identity for e in known_events)
        start,end = [parse_date(v) for v in stamps]
        if not start or not end or end<=start or start>at+timedelta(days=7):
            continue
        if state=='Arşivlendi':
            # A previously tracked interval explicitly completed early must
            # become stale immediately, without creating a new archive alert.
            actual = row.get('Kesinti_Sona_Erme_Zamani')
            actual_end = parse_date(actual) if isinstance(actual,str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?',actual) else None
            if not known:
                continue
            if not actual_end or not start<actual_end<=at:
                raise ValueError('Existing GDZ interval has no verified completion time')
            end = actual_end
        elif end<=at:
            continue
        if row.get('type') not in (None,'planned'):
            continue
        cancelled = state=='Planlı Kesinti İptal Edildi'
        if cancelled and not known:
            continue  # Do not import the provider's cancellation archive as new alerts.
        neighborhoods = row.get('Mahalle')
        if not isinstance(neighborhoods,list) or not neighborhoods or not all(isinstance(n,str) and 1<=len(n)<=100 for n in neighborhoods):
            continue
        place = {'SEFERİHİSAR':'Seferihisar','URLA':'Urla','GÜZELBAHÇE':'Güzelbahçe','MENDERES':'Özdere'}.get(district)
        if not place:
            continue
        selected = neighborhoods
        if district=='MENDERES':
            # Municipality confirms Çukuraltı and Orta as Özdere neighborhoods.
            # Bare Cumhuriyet is ambiguous (also Görece/Gümüldür); do not infer it.
            selected=[n for n in neighborhoods if _gdz_name(n) in ('çukuraltı','orta','özdere çukuraltı','özdere orta','özdere cumhuriyet')]
        if not selected:
            continue
        details = []
        pairs = row.get('MahalleSokak')
        if isinstance(pairs,list):
            for pair in pairs:
                if not isinstance(pair,dict) or pair.get('Mahalle') not in selected:
                    continue
                streets=pair.get('Sokak')
                if isinstance(streets,list) and all(isinstance(v,str) and len(v)<=100 for v in streets):
                    details.append(pair['Mahalle']+': '+', '.join(streets))
        scope = '; '.join(details)[:1800] or ', '.join(selected)
        reason = row.get('Kesinti_Nedeni')
        reason = reason[:300] if isinstance(reason,str) else None
        title = place+('’de' if place in ('Güzelbahçe','Özdere') else '’da')+' planlı elektrik kesintisi'+(' iptal edildi' if cancelled else '')
        description = ('GDZ Elektrik kaydına göre '+('planlı kesinti iptal edildi. ' if cancelled else 'planlı çalışma. ')
                       +'Başlangıç: '+start.strftime('%d.%m.%Y %H:%M')+'. Bitiş: '+end.strftime('%d.%m.%Y %H:%M')
                       +'. Etkilenen mahalleler: '+', '.join(selected)+'. Sokak ayrıntıları: '+scope+'.'+(' Neden: '+reason+'.' if reason else ''))
        item = event(source,display,title,description,start,end,place+' · '+', '.join(selected),'outage',valid_until=end.isoformat())
        item.update(identity=identity,status='cancelled' if cancelled else 'scheduled',organizer='GDZ Elektrik')
        results.append(item)
    return results


def collect_gdz_planned(source,fetcher,known_events):
    from urllib.parse import urlencode
    found,errors = [],[]
    at = now()
    for district in ('SEFERİHİSAR','URLA','GÜZELBAHÇE','MENDERES'):
        url = source['url']+'?'+urlencode({'city':'İZMİR','district':district,'action':'outages'})
        try:
            body,base=fetcher.get(url)
            found.extend(gdz_planned_items(body,base,source,district,at,known_events))
        except (ValueError,OSError,requests.RequestException) as exc:
            errors.append({'source_id':source['id'],'code':detail_error_code(exc)})
    return found,[],errors


def news(source, url, title, description, published, topic, **extra):
    return {'kind':'news', 'url':page_url(url), 'identity':canonical(url),
            'title':title[:240], 'description':description[:3000],
            'published_at':published.isoformat(), 'category':topic,
            'source_id':source['id'], 'source_name':source['name'],
            'sources':[page_url(url)], **extra}


def event(source, url, title, description, start, end, location, topic, **extra):
    return {'kind':'event', 'url':page_url(url), 'identity':canonical(url),
            'title':title[:240], 'description':description[:3000],
            'source_id':source['id'], 'source_name':source['name'], 'sources':[page_url(url)],
            'category':topic, 'start':start.isoformat(), 'end':end.isoformat(),
            'time_known':True, 'location':location, 'organizer':None, 'free':None,
            'price':None, 'currency':None, 'ticket_url':None, 'status':'scheduled',
            'previous_start':None, **extra}


def afad_items(body, base, source):
    soup = BeautifulSoup(body, 'html.parser')
    header = ' '.join(text(n) for n in soup.select('thead th'))
    if not all(word in header for word in ('Tarih','Enlem','Boylam','Büyüklük','Yer')):
        raise ValueError('Expected dated AFAD earthquake table')
    results = []
    for row in soup.select('tbody tr')[:100]:
        cells = row.find_all('td', recursive=False)
        if len(cells) != 8:
            continue
        values = [text(c) for c in cells]
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', values[0]):
            continue
        stamp = parse_date(values[0].replace(' ', 'T')) # Table explicitly labels Turkish time (TS).
        try:
            lat, lon, depth, magnitude = (float(values[i]) for i in (1,2,3,5))
        except ValueError:
            continue
        if (not stamp or not all(math.isfinite(v) for v in (lat,lon,depth,magnitude))
                or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= depth <= 800
                or not 4.0 <= magnitude <= 10 or not re.fullmatch(r'M[LWDBS]|Mw', values[4])):
            continue
        place = values[6]
        distance = 6371 * 2 * math.asin(min(1, math.sqrt(
            math.sin(math.radians(lat-38.1969)/2)**2
            + math.cos(math.radians(lat))*math.cos(math.radians(38.1969))
            * math.sin(math.radians(lon-26.8381)/2)**2)))
        if not local(place + ' deprem') and distance > 60:
            continue
        anchor = cells[7].find('a',href=True)
        url = urljoin(base, anchor['href']) if anchor else ''
        if not re.fullmatch(r'https://deprem\.afad\.gov\.tr/event-detail/\d{1,12}', url):
            continue
        subject = place if local(place + ' deprem') else 'Seferihisar yakınları (' + place + ')'
        title = 'AFAD kaydı: ' + subject + ' — ' + values[5] + ' büyüklüğünde deprem'
        description = (f"AFAD'ın {stamp.strftime('%d.%m.%Y %H:%M:%S')} (Türkiye saati) kaydı: "
                       f"{place}; büyüklük {values[5]} {values[4]}, derinlik {values[3]} km. "
                       f"Koordinatlar: {values[1]}, {values[2]}. ")
        if not local(place + ' deprem'):
            description += f"Koordinatlardan hesaplanan Seferihisar ilçe merkezine kuş uçuşu mesafe yaklaşık {round(distance)} km. "
        description += 'Bu kayıt hasar veya hissedilme bilgisi içermez.'
        results.append(news(source,url,title,description,stamp,'public',valid_until=(stamp+timedelta(hours=3)).isoformat()))
    return results


def warning_field(soup, label):
    heading = soup.find('h3', string=lambda s: isinstance(s,str) and s.strip()==label)
    if not heading:
        return ''
    if heading.parent.get('id')=='divUyari':
        node = heading.find_next_sibling()
        return text(node) if node and node.name=='p' else ''
    row = heading.parent.parent
    node = row.select_one('.c2')
    return text(node) if node else ''


def mgm_items(body, url, source):
    soup = BeautifulSoup(body,'html.parser')
    stamp = soup.select_one('.uZaman')
    title = warning_field(soup,'Beklenen Meteorolojik Hadise') or text(soup.select_one('h2'))
    values = stamp.select('i') if stamp else []
    if not stamp:
        fields = {}
        for cell in soup.select('#divUyari table th'):
            label = text(cell).strip(' :\xa0')
            value = cell.find_next_sibling('td')
            if label in ('Tarih','Saat') and value:
                fields[label] = text(value)
        values = [fields.get('Tarih',''),fields.get('Saat','')]
    if not title or len(values)<2 or not all(text(v) for v in values[:2]):
        raise ValueError('Expected dated MGM warning')
    area = warning_field(soup,'Beklendiği Yer') or warning_field(soup,'Genel Durum')
    if not area:
        raise ValueError('Missing warning area')
    if not local(area + ' meteoroloji fırtına'):
        if not re.search(r'(?i)İzmir\s+(?:il\s+)?genel(?:i|inde)',area):
            return []
        title = 'İzmir geneli (Seferihisar dahil): ' + title
    date = re.fullmatch(r'(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\s+\w+',text(values[0]),re.I)
    hour = re.fullmatch(r'(\d{1,2})[.:](\d{2})',text(values[1]))
    validity = warning_field(soup,'Başlama-Bitiş Zamanı')
    period = re.fullmatch(r'(\d{1,2}\.\d{1,2}\.20\d{2})\s+(\d{1,2}[.:]\d{2})\s*[-–]\s*(\d{1,2}\.\d{1,2}\.20\d{2})\s+(\d{1,2}[.:]\d{2})',validity)
    if not date or not hour or not period:
        raise ValueError('Missing full-year warning validity')
    try:
        published = datetime(int(date[3]),MONTHS[date[2].casefold()],int(date[1]),int(hour[1]),int(hour[2]),tzinfo=TZ)
        start,end = [datetime.strptime(d+' '+h.replace('.',':'),'%d.%m.%Y %H:%M').replace(tzinfo=TZ)
                     for d,h in ((period[1],period[2]),(period[3],period[4]))]
    except ValueError:
        raise ValueError('Invalid warning date') from None
    if end < start or end < published:
        raise ValueError('Conflicting warning validity')
    description = (area + ' Geçerlilik: ' + start.strftime('%d.%m.%Y %H:%M')
                   + ' – ' + end.strftime('%d.%m.%Y %H:%M') + ' (Türkiye saati).')
    return [news(source,url,title,description,published,'weather',valid_until=end.isoformat())]


def collect_mgm(source, fetcher):
    body,base = fetcher.get(source['url'])
    soup = BeautifulSoup(body,'html.parser')
    if not soup.select('a[href*="tahmin-uyari-goster.aspx"]') and 'Güncel Meteorolojik' not in text(soup):
        raise ValueError('Expected public MGM warning list')
    links = []
    for anchor in soup.select('a[href*="tahmin-uyari-goster.aspx"]'):
        match = re.fullmatch(r'tahmin-uyari-goster\.aspx\?sN=([a-zA-Z0-9]{1,20})',anchor['href'])
        if match:
            # The published mobile list points to a retired mobile detail
            # endpoint; the official desktop detail accepts the same warning ID.
            links.append('https://www.mgm.gov.tr/tahmin/uyari-goster.aspx?sN='+match[1])
    found,errors = [],[]
    for link in list(dict.fromkeys(links))[:5]:
        try:
            page,final = fetcher.get(link)
            found.extend(mgm_items(page,final,source))
        except (ValueError, OSError) as exc:
            errors.append({'source_id':source['id'],'code':detail_error_code(exc)})
        except Exception as exc:
            from requests import RequestException
            if not isinstance(exc,RequestException):
                raise
            errors.append({'source_id':source['id'],'code':detail_error_code(exc)})
    return found,[],errors


def ticket_items(body, base, source):
    """Use actual session metadata, never a touring biography for geolocation."""
    soup = BeautifulSoup(body,'html.parser')
    records = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            records.extend(o for o in objects(json.loads(script.get_text()))
                           if isinstance(o.get('@type'),str) and o['@type'].endswith('Event'))
        except (ValueError,TypeError):
            continue
    has_sessions = any(isinstance(o.get('offers'),dict) and '/seans/' in str(o['offers'].get('url','')) for o in records)
    found = []
    for obj in records[:100]:
        location = obj.get('location')
        if isinstance(location,list):
            location = location[0] if len(location)==1 else None
        if not isinstance(location,dict):
            continue
        address = location.get('address')
        if not isinstance(address,dict):
            continue
        place = ' · '.join(filter(None,[text(location.get('name')),
                              ' '.join(text(address.get(k)) for k in ('streetAddress','addressLocality','addressRegion'))]))
        if not local(place + ' etkinlik'):
            continue
        offers = obj.get('offers',{})
        offers = offers[0] if isinstance(offers,list) and len(offers)==1 else offers
        offers = offers if isinstance(offers,dict) else {}
        if has_sessions and offers.get('@type')=='AggregateOffer':
            continue
        data = {**obj,'location':location,
                'description':'Etkinlik duyurusu. '+text(obj.get('description'))}
        if not isinstance(data.get('url'),str):
            data['url'] = base
        if data['url'].startswith('http://') and urlsplit(data['url']).hostname==urlsplit(base).hostname:
            data['url'] = 'https://' + data['url'][7:]
        encoded = '<script type="application/ld+json">'+json.dumps(data).replace('</','<\\/')+'</script>'
        items = structured(encoded,base,source)
        for item in items:
            if item['kind']!='event' or not public_url(item['url']) or urlsplit(item['url']).hostname!=urlsplit(source['url']).hostname:
                continue
            # A real per-session ticket URL is a stable identity when available.
            session_url = offers.get('url','')
            if '/seans/' in session_url and public_url(session_url) and urlsplit(session_url).hostname==urlsplit(base).hostname:
                item.update(url=page_url(session_url),identity=canonical(session_url),sources=[page_url(session_url)])
            elif not obj.get('@id'):
                item['identity'] = canonical(item['url'])+'#session-'+digest(item['start']+':'+normalized(place))
            if item['category'] not in EVENT_CATEGORIES:
                item['category'] = 'event'
            item['ticket_url'] = item['url']
            if not contains_secret(item):
                found.append(item)
    return list({i['identity']:i for i in found}.values())


def collect_tickets(source, fetcher, known_events=(), reader=ticket_items):
    links = []
    for listing in (source.get('listing_urls') or [source['url']])[:4]:
        if urlsplit(listing).hostname != urlsplit(source['url']).hostname:
            raise ValueError('Unapproved ticket listing origin')
        body,base = fetcher.get(listing)
        if source.get('listing_format')=='biletinial_json':
            data = json.loads(body)
            if not isinstance(data,dict) or not isinstance(data.get('items'),list):
                raise ValueError('Expected Biletinial listing')
            for row in data['items'][:60]:
                if not isinstance(row,dict) or not local(text(row.get('saloonName'))+' etkinlik'):
                    continue
                slug,section = row.get('seoUrl'),row.get('organizerUrl')
                if isinstance(slug,str) and re.fullmatch(r'[a-zA-Z0-9-]{1,160}',slug) and section in ('tiyatro','muzik','etkinlik','sinema','opera-bale'):
                    links.append('https://biletinial.com/tr-tr/'+section+'/'+slug)
            continue
        soup = BeautifulSoup(body,'html.parser')
        for anchor in soup.select(source['link_selector']):
            link = page_url(urljoin(base,anchor['href']))
            if not public_url(link) or urlsplit(link).hostname!=urlsplit(base).hostname:
                continue
            node = anchor.find_parent(['li','article']) or anchor.parent
            evidence = text(node)[:1200]+' '+text(anchor)+' '+link.replace('-',' ')
            if source.get('local_links_only',True) and not local(evidence+' etkinlik'):
                if not any(link.startswith(prefix) for prefix in source.get('reviewed_local_prefixes',[])):
                    continue
            links.append(link)
    tracked = [i['url'] for i in known_events if i['source_id']==source['id']]
    links.sort(key=lambda link: not any(link.startswith(prefix)
                                       for prefix in source.get('reviewed_local_prefixes',[])))
    found,errors = [],[]
    for link in list(dict.fromkeys(tracked+links))[:source.get('max_pages',4)]:
        try:
            body,base = fetcher.get(link)
            found.extend(reader(body,base,source))
        except Exception as exc:
            from requests import RequestException
            if not isinstance(exc,(RequestException,ValueError,OSError)):
                raise
            errors.append({'source_id':source['id'],'code':detail_error_code(exc)})
    return found,[],errors


def public_collection(body):
    data = json.loads(body)
    if not isinstance(data,dict) or data.get('ok') is not True or not isinstance(data.get('data'),list) or len(data['data'])>500:
        raise ValueError('Expected public municipal collection')
    return data['data']


def culture_items(sessions, events, venues, source):
    event_map = {e.get('id'):e for e in events if isinstance(e,dict)}
    venue_map = {v.get('id'):v for v in venues if isinstance(v,dict)}
    found = []
    for row in sessions:
        if not isinstance(row,dict) or type(row.get('entityStatus')) is not int or row['entityStatus']!=0 or not UUID.fullmatch(str(row.get('id',''))):
            continue
        ref,venue_ref = row.get('event'),row.get('venue')
        if not isinstance(ref,dict) or not isinstance(venue_ref,dict):
            continue
        details,venue = event_map.get(ref.get('id')),venue_map.get(venue_ref.get('id'))
        if not details or not venue or details.get('entityStatus')!=0 or venue.get('entityStatus')!=0:
            continue
        address = text(venue.get('address'))
        if not local(address+' etkinlik'):
            continue
        title = text(details.get('name'))
        start,end = parse_date(row.get('eventDate')),parse_date(row.get('eventEndDate'))
        if (not title or not start or not end or end<start
                or not all(isinstance(row.get(k),str) and 'T' in row[k] for k in ('eventDate','eventEndDate'))):
            continue
        slug = normalized(title).replace(' ','-')
        url = source['content_origin']+'/event/session/'+slug+'/'+row['id']
        topic = category(' '.join(text(c) for c in row.get('categories',[])))
        if topic not in EVENT_CATEGORIES:
            topic = 'event'
        description = text(row.get('longDescription') or details.get('longDescription'))[:2500]
        location = text(venue.get('name'))+' · '+address
        found.append(event(source,url,title,description or location,start,end,location,topic,
                           identity=source['content_origin']+'/#session-'+row['id'],
                           organizer=text(row.get('company')) or None))
    return found


def collect_culture(source,fetcher):
    bodies = [public_collection(fetcher.get(url)[0]) for url in source['listing_urls']]
    return culture_items(*bodies,source),[],[]


def rotary_items(body,base,source):
    soup = BeautifulSoup(body,'html.parser')
    obj = next((o for s in soup.select('script[type="application/ld+json"]')
                for o in objects(json.loads(s.get_text())) if o.get('@type')=='Event'),None)
    if not obj:
        return structured(body,base,source)
    # This site embeds UTC offsets in schema but prints Turkish local start
    # times. Read the explicit Date and Time fields together, not that offset.
    fields = {}
    for li in soup.select('li'):
        children = li.find_all('span',recursive=False)
        if len(children)==2 and text(children[0]) in ('Tarih','Saat','Yer','Mekan','Mekân'):
            key = text(children[0]);value = text(children[1])
            if key in fields and fields[key]!=value:
                raise ValueError('Conflicting rotary event labels')
            fields[key]=value
    date = re.fullmatch(r'(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})',fields.get('Tarih',''),re.I)
    hour = re.fullmatch(r'(\d{1,2}):(\d{2})',fields.get('Saat',''))
    if not date or not hour:
        raise ValueError('Missing full rotary event date')
    start = datetime(int(date[3]),MONTHS[date[2].casefold()],int(date[1]),int(hour[1]),int(hour[2]),tzinfo=TZ)
    title = text(obj.get('name'));location = obj.get('location',{});address = location.get('address',{})
    place = text(location.get('name'))+' · '+text(address.get('streetAddress'))
    if not local(place+' etkinlik'):
        return []
    offer = obj.get('offers',{})
    price = str(offer.get('price',''))
    price = price if re.fullmatch(r'\d+(?:\.\d{1,2})?',price) else None
    return [event(source,base,title,text(obj.get('description')),start,start,place,category(title),
                  organizer=text(obj.get('organizer')) or None,price=price,
                  currency='TRY' if price and offer.get('priceCurrency')=='TRY' else None,
                  free=price in ('0','0.00') if price is not None else None)]


def hospital_items(body,base,source):
    soup = BeautifulSoup(body,'html.parser')
    article = soup.select_one('#div_print')
    date = publication_date(soup,source)
    if not article or not date:
        return []
    date_node = soup.select_one(source['published_date_selector'])
    heading = date_node.parent.find('h5',recursive=False) if date_node else None
    description = ' '.join(text(p) for p in article.select('p') if len(text(p))>30)
    if not heading or not description:
        return []
    return [news(source,base,source['name']+': '+text(heading),description,date,'public')]


def program_items(body,base,source):
    soup = BeautifulSoup(body,'html.parser')
    for node in soup.select('script,style,nav,header,footer'):
        node.decompose()
    prose = text(soup)
    month_names = '|'.join(MONTHS)
    ranges = re.findall(r'(\d{1,2})\s*[-–]\s*(\d{1,2})\s+('+month_names+r')\s+(20\d{2})',prose,re.I)
    dates = re.findall(r'(\d{1,2})\s+('+month_names+r')\s+(20\d{2})',prose,re.I)
    values = {(int(y),MONTHS[m.casefold()],int(d)) for d,m,y in dates}
    for first,last,m,y in ranges:
        values.update(((int(y),MONTHS[m.casefold()],int(first)),(int(y),MONTHS[m.casefold()],int(last))))
    listed = re.findall(r'(\d{1,2})\s*,\s*(\d{1,2})\s+ve\s+(\d{1,2})\s+('+month_names+r')\s+(20\d{2})',prose,re.I)
    for first,middle,last,m,y in listed:
        values.update((int(y),MONTHS[m.casefold()],int(d)) for d in (first,middle,last))
    if not values or len({v[0] for v in values})!=1:
        raise ValueError('Missing unambiguous full-year festival dates')
    start,end = [datetime(*v,tzinfo=TZ) for v in (min(values),max(values))]
    if end-start>timedelta(days=6):
        raise ValueError('Ambiguous festival range')
    title,place = source['program_title'],source['program_location']
    if title not in prose or not local(place+' festival'):
        raise ValueError('Unverified festival program')
    url = page_url(base)
    return [event(source,url,title,'Festival programı: '+title+' · '+place,start,end,place,'festival',
                  identity=canonical(url)+'#edition-'+str(start.year),time_known=False)]
