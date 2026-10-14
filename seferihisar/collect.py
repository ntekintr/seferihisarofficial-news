"""Permitted RSS/Atom and schema.org collection, bounded per-source crawling.

No search-engine scraping, social login scraping or ticket-platform bypasses.
Unknown sources are candidates, never automatically trusted publishers.
"""
from __future__ import annotations

import ipaddress
import codecs
import json
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from itertools import zip_longest
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, NavigableString, Comment
from urllib3.exceptions import NameResolutionError

from .domain import TZ, canonical, category, digest, local, normalized, now, parse_date

AGENT = "SeferihisarOfficial/0.1 (+https://github.com/ntekintr/seferihisarofficial-news)"
MAX_BYTES = 2_000_000
MONTHS = {name: index for index, name in enumerate(("ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"), 1)}


class PublicDNSLookupError(requests.ConnectionError):
    """A controlled DNS failure, without the resolver's potentially private text."""


def network_error_kind(exc: Exception) -> str | None:
    """Inspect typed Requests/urllib3 causes, never match or export error text."""
    pending, seen = [exc], set()
    while pending and len(seen) < 24:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(error, (PublicDNSLookupError, NameResolutionError, socket.gaierror)):
            return 'dns_failed'
        if isinstance(error, ssl.SSLCertVerificationError) and getattr(error, 'verify_code', None) == 62:
            return 'tls_name_mismatch'
        for nested in (error.__cause__, error.__context__, getattr(error, 'reason', None), *error.args):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return None


def decode_document(body: bytes, content_type: str = '') -> str:
    """Honor explicit HTTP/document charsets; HTTP's implicit Latin-1 is not evidence."""
    header = re.search(r'charset\s*=\s*[\"\']?([\w.-]+)', content_type, re.I)
    prefix = body[:4096].decode('ascii', errors='ignore')
    declared = re.search(r'(?:<meta\b[^>]*charset\s*=\s*[\"\']?|<\?xml\b[^>]*encoding\s*=\s*[\"\'])([\w.-]+)', prefix, re.I)
    encoding = header[1] if header else (declared[1] if declared else 'utf-8')
    try:
        codecs.lookup(encoding)
        return body.decode(encoding, errors='replace').lstrip('\ufeff')
    except (LookupError, ValueError):
        raise ValueError('Unsupported document charset') from None


def page_url(url: str) -> str:
    """Strip tracking/fragment data while preserving the publisher's fetch path."""
    return urlsplit(canonical(url))._replace(path=urlsplit(url).path or "/").geturl()


def labelled_event(title: str, description: str, article, url: str, source: dict) -> dict | None:
    """Only explicitly labelled, full-year event dates; no inference from news dates."""
    if category(title + " " + description) not in ("concert", "festival", "theatre", "cinema", "family", "sport", "market", "culture", "event", "food", "education"):
        return None
    body = text(article)
    labelled = re.findall(r"(?:etkinlik\s+tarihi|tarih)\s*[:：]\s*(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(20\d{2})", body, re.I)
    named = re.findall(r"(?:etkinlik\s+tarihi|tarih)\s*[:：]\s*(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})", body, re.I)
    values = labelled + [(d, str(MONTHS[m.casefold()]), y) for d, m, y in named]
    if len(set(values)) != 1:
        return None
    hour = re.search(r"(?:başlangıç\s+saati|saat)\s*[:：]\s*(\d{1,2})[.:](\d{2})", body, re.I)
    day, month, year = map(int, values[0])
    try:
        start = datetime(year, month, day, int(hour[1]) if hour else 0, int(hour[2]) if hour else 0, tzinfo=TZ)
    except ValueError:
        return None
    def field(names):
        for p in article.select("p, li, div"):
            value = text(p)
            match = re.fullmatch(r"(?:" + names + r")\s*[:：]\s*(.{1,200})", value, re.I)
            if match:
                return match[1]
        return None
    fee = field("ücret|bilet ücreti")
    free = True if fee and fee.casefold() == "ücretsiz" else (False if fee and re.fullmatch(r"\d+(?:[.,]\d+)?\s*(?:TL|₺)", fee, re.I) else None)
    return {"kind": "event", "identity": canonical(url), "title": title[:240], "description": description,
            "url": page_url(url), "source_id": source["id"], "source_name": source["name"],
            "category": category(title + " " + description), "sources": [page_url(url)],
            "start": start.isoformat(), "end": start.isoformat(), "time_known": bool(hour),
            "location": field("yer|konum|mek[âa]n"), "organizer": field("organizatör|düzenleyen"),
            "free": free, "price": None, "currency": None, "ticket_url": None,
            "status": "cancelled" if re.search(r"(?:etkinlik|konser|gösteri)\s+iptal\s+edil(?:di|miştir)", body, re.I) else "scheduled", "previous_start": None}


def safe_url(url: str, allowed_hosts: set[str]) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("Only public HTTPS URLs on port 443 are allowed")
    host = parts.hostname or ""
    if host not in allowed_hosts:
        raise ValueError("Host requires explicit source approval")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise PublicDNSLookupError('Public source DNS lookup failed') from None
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError("Private or reserved network destination rejected")
    # Fetch the publisher's actual path. Removing a trailing slash here makes
    # sites which redirect to that slash loop forever; canonicalize identities only.
    return parts._replace(fragment="").geturl()


class Fetcher:
    def __init__(self, sources: list[dict], session=None):
        web_sources = [s for s in sources if s.get('kind')!='instagram_api']
        self.hosts = {urlsplit(s["url"]).hostname for s in web_sources if s.get("enabled")}
        self.missing_robots_hosts = {urlsplit(s["url"]).hostname for s in web_sources
                                    if s.get("enabled") and s.get("allow_missing_robots") is True}
        self.session = session or requests.Session()
        self.robots: dict[str, RobotFileParser] = {}
        self.last_request: dict[str, float] = {}
        # One extra read per reviewed host/run, never a retry loop or a bypass.
        self.retries = {urlsplit(s['url']).hostname: min(1, max(0, s.get('transient_retries', 0)))
                        for s in web_sources if s.get('enabled')}

    def request(self, url: str) -> tuple[str, str]:
        url = safe_url(url, self.hosts)
        # Validate every redirect before following it; keep requests bounded.
        for _ in range(5):
            host = urlsplit(url).hostname
            wait = max(0, 1.0 - (time.monotonic() - self.last_request.get(host, 0)))
            if wait:
                time.sleep(wait)
            self.last_request[host] = time.monotonic()
            response = self.session.get(url, timeout=(8, 20), headers={"User-Agent": AGENT}, allow_redirects=False, stream=True)
            try:
                if response.is_redirect:
                    url = safe_url(urljoin(url, response.headers["Location"]), self.hosts)
                    continue
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError("Response too large")
                return decode_document(bytes(body), response.headers.get('Content-Type', '')), url
            finally:
                response.close()
        raise ValueError("Too many redirects")

    def get(self, url: str) -> tuple[str, str]:
        try:
            return self._get(url)
        except requests.RequestException as exc:
            host = urlsplit(url).hostname
            response = exc.response
            status = response.status_code if response is not None else None
            retryable = isinstance(exc, (requests.Timeout, requests.ConnectionError)) or status in (429, 500, 502, 503, 504)
            if isinstance(exc, requests.exceptions.SSLError):
                retryable = False
            delay = 2
            if status == 429:
                value = response.headers.get('Retry-After', '')
                if not value.isdigit() or int(value) > 5:
                    retryable = False
                else:
                    delay = max(2, int(value))
            if not retryable or self.retries.get(host, 0) <= 0:
                raise
            self.retries[host] -= 1
            time.sleep(delay)
            return self._get(url)

    def _get(self, url: str) -> tuple[str, str]:
        host = urlsplit(url).hostname
        if host not in self.robots:
            robot = RobotFileParser()
            # Only explicitly reviewed hosts may treat an absent file as no rules.
            # Authentication errors, rate limits, server errors and timeouts still stop collection.
            try:
                body, _ = self.request(f"https://{host}/robots.txt")
            except requests.HTTPError as exc:
                if host not in self.missing_robots_hosts or exc.response is None or exc.response.status_code not in (404, 410):
                    raise
                body = "User-agent: *\nDisallow:"
            robot.parse(body.splitlines())
            self.robots[host] = robot
        robot = self.robots[host]
        if not robot.can_fetch(AGENT, url):
            raise ValueError("robots.txt disallows this path")
        delay = robot.crawl_delay(AGENT) or robot.crawl_delay("*") or 1
        if delay > 60:
            raise ValueError("Source requires a crawl delay exceeding the run budget")
        request_rate = robot.request_rate(AGENT) or robot.request_rate("*")
        if request_rate and request_rate.requests:
            delay = max(delay, request_rate.seconds / request_rate.requests)
        wait = max(0, delay - (time.monotonic() - self.last_request.get(host, 0)))
        if wait:
            time.sleep(wait)
        return self.request(url)


def text(value) -> str:
    if isinstance(value, dict):
        value = value.get("name", "")
    return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)


def objects(value):
    if isinstance(value, list):
        for child in value:
            yield from objects(child)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from objects(child)


def publication_date(soup, source: dict):
    """Source-specific publication field, never a date borrowed from body/sidebar."""
    selector = source.get('published_date_selector')
    if not selector:
        node = soup.select_one('meta[property="article:published_time"], meta[name="datePublished"], meta[name="date"], time[datetime]')
        return parse_date((node.get('content') or node.get('datetime')) if node else None)
    nodes = soup.select(selector)
    values = []
    for node in nodes:
        if source.get('published_date_parent'):
            node = node.parent
        value = (' '.join(str(n) for n in node.contents if isinstance(n, NavigableString) and not isinstance(n, Comment))
                 if source.get('published_date_direct_text') else text(node))
        if source.get('published_date_format') == 'turkish':
            match = re.fullmatch(r'\s*(\d{1,2})\s+(' + '|'.join(MONTHS) + r')\s+(20\d{2})\s*', value, re.I)
            if not match:
                return None
            d, month_name, y = match.groups()
            m, h, minute, second = MONTHS[month_name.casefold()], None, None, None
        else:
            match = re.fullmatch(r'\s*(\d{1,2})\.(\d{1,2})\.(20\d{2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\s*', value)
            if not match:
                return None
            d, m, y, h, minute, second = match.groups()
        try:
            values.append(datetime(int(y), int(m), int(d), int(h or 0), int(minute or 0), int(second or 0), tzinfo=TZ))
        except ValueError:
            return None
    return values[0] if values and len(set(values)) == 1 else None


def structured(html: str, url: str, source: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one(source.get("article_selector", 'article .entry-content, article .article-content, article, .news-detail, .haber-detay'))
    if article is None and source.get("article_selector"):
        article = soup.select_one('article, .news-detail, .haber-detay')
    article_text = " ".join(text(p) for p in article.select("p") if len(text(p)) > 30)[:3000] if article else ""
    if not article_text and article and source.get('body_text_fallback'):
        article_text = text(article)[:3000]
    results = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            raw = script.string or script.get_text()
            if source.get("repair_json_trailing_commas"):
                # Repair commas outside JSON strings only (municipal template defect).
                raw = re.sub(r'("(?:\\.|[^"\\])*"\s*)|,(\s*[}\]])', lambda m: m[1] if m[1] else m[2], raw)
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in objects(data):
            types = obj.get("@type", [])
            types = [types] if isinstance(types, str) else types
            is_event = any(isinstance(t, str) and (t == "Event" or t.endswith("Event")) for t in types)
            is_news = any(t in ("NewsArticle", "Article", "ReportageNewsArticle") for t in types)
            if not is_event and not is_news:
                continue
            title = text(obj.get("name") if is_event else obj.get("headline"))
            description = text(obj.get("description") or obj.get("articleBody"))[:3000] or article_text
            location = obj.get("location", {})
            if isinstance(location, list):
                location = location[0] if location else {}
            address = location.get("address", {}) if isinstance(location, dict) else {}
            location_text = text(location)
            if isinstance(address, dict):
                location_text += " " + " ".join(text(address.get(k)) for k in ("streetAddress", "addressLocality", "addressRegion"))
            elif address:
                location_text += " " + text(address)
            if not title or not local(title + " " + description + " " + location_text):
                continue
            # Some publishers put their homepage in Article.url. The fetched detail
            # page identifies the article; event-specific URLs can remain distinct.
            item_url = page_url(urljoin(url, obj.get("url") if is_event and isinstance(obj.get("url"), str) else url))
            item = {"kind": "event" if is_event else "news", "title": title[:240], "description": description,
                    "url": item_url, "source_id": source["id"], "source_name": source["name"],
                    "category": category(title + " " + description), "sources": [item_url]}
            if is_event:
                start = parse_date(obj.get("startDate"))
                if not start:
                    continue  # Never guess a year or time from prose.
                status = str(obj.get("eventStatus", "EventScheduled")).split("/")[-1]
                if status == "EventCancelled":
                    status = "cancelled"
                elif status in ("EventPostponed", "EventRescheduled"):
                    status = "postponed" if status == "EventPostponed" else "rescheduled"
                else:
                    status = "scheduled"
                offers = obj.get("offers", {})
                offers = offers[0] if isinstance(offers, list) and offers else offers
                offers = offers if isinstance(offers, dict) else {}
                free = obj.get("isAccessibleForFree")
                free = free if isinstance(free, bool) else (True if str(offers.get("price")) in ("0", "0.0", "0.00") else None)
                identity = obj.get("@id") or canonical(item_url)
                item.update(identity=urljoin(url, str(identity)), start=start.isoformat(),
                            time_known="T" in str(obj.get("startDate", "")),
                            end=(parse_date(obj.get("endDate")) or start).isoformat(),
                            location=location_text.strip() or None, organizer=text(obj.get("organizer")) or None,
                            free=free, price=text(offers.get("price")) or None,
                            currency=text(offers.get("priceCurrency")) or None,
                            ticket_url=urljoin(url, offers["url"]) if isinstance(offers.get("url"), str) else None,
                            status=status, previous_start=(parse_date(obj.get("previousStartDate")).isoformat() if parse_date(obj.get("previousStartDate")) else None))
            else:
                published = parse_date(obj.get("datePublished"))
                if not published:
                    continue
                item["published_at"] = published.isoformat()
                item["identity"] = canonical(item_url)
                if article:
                    event = labelled_event(title, description, article, url, source)
                    if event:
                        item = event
            results.append(item)
    if not results:
        # Common WordPress and municipal article metadata, without guessing dates.
        headline = soup.select_one('meta[property="og:title"]')
        date = publication_date(soup, source)
        title_node = soup.select_one(source['title_selector']) if source.get('title_selector') else None
        title = text(title_node) if source.get('title_selector') else (text(headline.get("content")) if headline else text(soup.find("h1")))
        if article and date and title:
            for removable in article.select('script, style, nav, footer, .comments, .sharedaddy'):
                removable.decompose()
            paragraphs = [text(p) for p in article.select("p")]
            description = " ".join(p for p in paragraphs if len(p) > 30)[:3000]
            if not description and source.get('body_text_fallback'):
                description = text(article)[:3000]
            if description and local(title + " " + description):
                event = labelled_event(title, description, article, url, source)
                results.append(event or {"kind": "news", "title": title[:240], "description": description,
                                "url": page_url(url), "identity": canonical(url), "source_id": source["id"], "source_name": source["name"],
                                "category": category(title + " " + description), "published_at": date.isoformat(), "sources": [page_url(url)]})
        elif article and title:
            description = text(article)[:3000]
            if local(title + " " + description):
                event = labelled_event(title, description, article, url, source)
                if event:
                    results.append(event)
    return results


def wordpress_items(body: str, base: str, source: dict) -> list[dict]:
    """Public published WordPress news/announcements, using explicit GMT dates."""
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError('Expected a public WordPress collection')
    results = []
    for obj in data[:20]:
        if not isinstance(obj, dict) or obj.get('status') != 'publish':
            continue
        title_obj, content_obj = obj.get('title'), obj.get('content')
        if not isinstance(title_obj, dict) or not isinstance(content_obj, dict) or not isinstance(obj.get('link'), str):
            continue
        title, description = text(title_obj.get('rendered')), text(content_obj.get('rendered'))[:3000]
        raw_date = obj.get('date_gmt', '')
        if not isinstance(raw_date, str) or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', raw_date):
            continue
        date = parse_date(raw_date + 'Z')
        if not date or not title or not description or not local(title + ' ' + description):
            continue
        url = page_url(urljoin(base, obj['link']))
        article = BeautifulSoup(content_obj.get('rendered') or '', 'html.parser')
        event = labelled_event(title, description, article, url, source)
        results.append(event or {'kind':'news', 'title':title[:240], 'description':description,
                       'url':url, 'identity':canonical(url), 'published_at':date.isoformat(),
                       'source_id':source['id'], 'source_name':source['name'],
                       'category':category(title+' '+description), 'sources':[url]})
    return results


def izmir_art_items(body: str, base: str, source: dict) -> list[dict]:
    """Public event-list JSON, with actual venue addresses and per-session dates."""
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError('Expected public event collection')
    results = []
    for row in data[:80]:
        if not isinstance(row, dict):
            continue
        address = text(row.get('locationAddress'))
        event_type = text(row.get('eventType'))
        title = text(row.get('title'))
        # District IDs on the site can be stale after a touring show's venue changes.
        # Do not use them, the event title or another session to geolocate this one.
        if not address or not local(address + ' ' + event_type):
            continue
        start, end = parse_date(row.get('startDate')), parse_date(row.get('endDate'))
        session, href = row.get('seans'), row.get('eventlink')
        if not title or not start or not end or end < start or not isinstance(session, str) or not re.fullmatch(r'[a-f0-9]{24}', session) or not isinstance(href, str):
            continue
        url = page_url(urljoin(base, href))
        if urlsplit(url).hostname != urlsplit(base).hostname:
            continue
        known_time = bool(re.fullmatch(r'\d{2}:\d{2}', str(row.get('eventTime', ''))))
        if known_time and start.strftime('%H:%M') != row['eventTime']:
            continue  # Conflicting timestamps are not silently reconciled.
        price = text(row.get('eventPrice'))
        fee = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*(?:TL|₺)', price, re.I)
        if type(row.get('cancel')) is not int or row['cancel'] not in (0, 1):
            continue
        location = (text(row.get('location')) + ' · ' + address).strip(' ·')
        description = event_type + ' · ' + location
        results.append({'kind':'event', 'title':title[:240], 'description':description[:3000],
                        'url':url, 'identity':canonical(url), 'source_id':source['id'], 'source_name':source['name'],
                        'sources':[url], 'category':category(title+' '+event_type),
                        'start':start.isoformat(), 'end':end.isoformat(), 'time_known':known_time,
                        'location':location, 'organizer':None, 'free':True if price.casefold()=='ücretsiz' else (False if fee else None),
                        'price':fee[1] if fee else None, 'currency':'TRY' if fee else None, 'ticket_url':None,
                        'status':'cancelled' if row['cancel'] else 'scheduled', 'previous_start':None})
    return results


def municipal_calendar_items(body: str, base: str, source: dict) -> list[dict]:
    """Reviewed FullCalendar date-only feed; its end date is exclusive."""
    rows = json.loads(body)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Expected municipal calendar collection')
    results = []
    for row in rows:
        title, href = text(row.get('title')), row.get('url')
        event_category = category(title)
        if not title or not local(title) or event_category not in (
            'concert', 'festival', 'theatre', 'cinema', 'family', 'sport',
            'market', 'culture', 'event', 'food', 'education'):
            continue
        if not isinstance(href, str) or not href.startswith('/') or href.startswith('//'):
            continue
        dates = [row.get('start'), row.get('end')]
        if not all(isinstance(d, str) and re.fullmatch(r'20\d{2}-\d{2}-\d{2}', d) for d in dates):
            continue
        start, exclusive_end = map(parse_date, dates)
        if not start or not exclusive_end or exclusive_end <= start:
            continue
        url = page_url(urljoin(base, href))
        if urlsplit(url).hostname != urlsplit(base).hostname or urlsplit(url).scheme != 'https':
            continue
        # Date-only end remains date-only; no event time, fee or venue is inferred.
        results.append({'kind': 'event', 'identity': canonical(url), 'url': url,
                        'title': title[:240], 'description': title[:240],
                        'source_id': source['id'], 'source_name': source['name'],
                        'category': event_category, 'sources': [url, base],
                        'start': start.isoformat(), 'end': (exclusive_end - timedelta(days=1)).isoformat(),
                        'time_known': False, 'location': None, 'organizer': None,
                        'free': None, 'price': None, 'currency': None, 'ticket_url': None,
                        'status': 'scheduled', 'previous_start': None})
    return results


def municipal_detail_fields(article) -> dict:
    """Read explicit labels from the event body, independently of date syntax."""
    content = BeautifulSoup(str(article), 'html.parser')
    for removable in content.select('script, style, nav, footer'):
        removable.decompose()
    for br in content.select('br'):
        br.replace_with('\n')
    lines = [re.sub(r'\s+', ' ', line).strip()
             for node in content.select('p, li')
             for line in node.get_text(' ', strip=False).splitlines()]

    def field(pattern):
        values = {match[1].strip() for line in lines
                  if (match := re.fullmatch(pattern + r'(.{1,200})', line, re.I))}
        if len(values) > 1:
            raise ValueError('Conflicting event detail labels')
        return next(iter(values), None)

    fee = field(r'(?:ücret|bilet ücreti)\s*[:：]\s*')
    return {
        'location': field(r'(?:📍\s*|(?:yer|konum|mek[âa]n)\s*[:：]\s*)'),
        'organizer': field(r'(?:organizatör|düzenleyen)\s*[:：]\s*'),
        'free': True if fee and fee.casefold() == 'ücretsiz' else
                False if fee and re.fullmatch(r'\d+(?:[.,]\d+)?\s*(?:TL|₺)', fee, re.I) else None,
    }


def detail_error_code(exc: Exception, *, calendar: bool = False) -> str:
    """Classify failed detail reads without retaining request or exception text."""
    code = 'detail_check_failed'
    if isinstance(exc, requests.exceptions.SSLError):
        code = 'detail_tls_name_mismatch' if network_error_kind(exc) == 'tls_name_mismatch' else 'detail_tls_failed'
    elif isinstance(exc, requests.Timeout):
        code = 'detail_timeout'
    elif isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if type(status) is int and 100 <= status <= 599:
            code = 'detail_http_' + str(status)
    elif isinstance(exc, requests.ConnectionError):
        code = 'detail_dns_failed' if network_error_kind(exc) == 'dns_failed' else 'detail_connection_failed'
    elif isinstance(exc, (ET.ParseError, json.JSONDecodeError)):
        code = 'detail_parse_failed'
    elif isinstance(exc, ValueError):
        # Only Fetcher's own exact, fixed messages have a diagnostic meaning.
        code = {
            'robots.txt disallows this path': 'detail_robots_denied',
            'Response too large': 'detail_response_too_large',
            'Too many redirects': 'detail_redirect_limit',
        }.get(str(exc), code)
    return 'calendar_' + code if calendar else code


def collect_municipal_calendar(source: dict, fetcher: Fetcher):
    body, base = fetcher.get(source['url'])
    today = now().date()
    upcoming = [i for i in municipal_calendar_items(body, base, source)
                if parse_date(i['end']).date() >= today
                and parse_date(i['start']).date() <= today + timedelta(days=90)]
    upcoming.sort(key=lambda i: (i['start'], i['url']))
    found, errors = [], []
    seen = set()
    for item in upcoming:
        if item['identity'] in seen:
            continue
        seen.add(item['identity'])
        if len(seen) > source.get('max_pages', 8):
            break
        try:
            detail, final = fetcher.get(item['url'])
            soup = BeautifulSoup(detail, 'html.parser')
            title = soup.select_one('.col-md-9 > .inner .right-title')
            heading = title.find_parent(class_='inner') if title else None
            # The reviewed template separates its heading and event body into
            # sibling blocks. Do not fall back to the page/sidebar/footer.
            article = heading.find_next_sibling('div', class_='inner') if heading else None
            article = article if article is not None else heading
            if canonical(final) != item['identity'] or article is None or normalized(text(title)) != normalized(item['title']):
                raise ValueError('Calendar detail does not match')
            body_text = text(article)
            richer = labelled_event(item['title'], body_text, article, final, source)
            if richer:
                if parse_date(richer['start']).date() != parse_date(item['start']).date():
                    raise ValueError('Calendar detail date conflicts')
                for field in ('location', 'organizer', 'free', 'status'):
                    item[field] = richer[field]
            item.update({field: value for field, value in municipal_detail_fields(article).items()
                         if value is not None})
            if re.search(r'(?:etkinlik|konser|gösteri|festival)\s+iptal\s+edil(?:di|miştir)', body_text, re.I):
                item['status'] = 'cancelled'
            elif re.search(r'(?:etkinlik|konser|gösteri|festival)\s+ertelen(?:di|miştir)', body_text, re.I):
                item['status'] = 'postponed'
            found.append(item)
        except (requests.RequestException, ValueError, OSError) as exc:
            errors.append({'source_id': source['id'], 'code': detail_error_code(exc, calendar=True)})
    return found, [], errors


def feed_items(xml: str, base: str, source: dict) -> list[dict]:
    root = ET.fromstring(xml)
    if root.tag == 'rss':
        valid = root.find('channel') is not None
    elif root.tag in ('feed', '{http://www.w3.org/2005/Atom}feed'):
        valid = True
    else:
        valid = (root.tag == '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF'
                 and root.find('{http://purl.org/rss/1.0/}channel') is not None)
    if not valid:
        # A well-formed HTML protection page is not an empty news feed.
        raise ET.ParseError('Expected RSS or Atom document')
    results = []
    for entry in root.iter():
        if entry.tag.split("}")[-1] not in ("item", "entry"):
            continue
        values = {}
        for child in entry:
            tag = child.tag.split("}")[-1]
            if tag == "link":
                if child.get("rel", "alternate") == "alternate":
                    values["link"] = child.get("href") or child.text
            elif child.text:
                values[tag] = child.text
        title = text(values.get("title"))
        description = text(values.get("description") or values.get("summary") or values.get("content"))[:3000]
        link = values.get("link")
        if not link or not title or not local(title + " " + description):
            continue
        raw_date = values.get("pubDate") or values.get("published") or values.get("updated") or values.get("date")
        date = parse_date(raw_date)
        if not date and raw_date:
            try:
                date = parsedate_to_datetime(raw_date).astimezone(TZ)
            except (ValueError, TypeError):
                pass
        if not date:
            continue
        item_url = page_url(urljoin(base, link))
        item = {"kind": "news", "title": title[:240], "description": description, "url": item_url, "identity": canonical(item_url),
                        "source_id": source["id"], "source_name": source["name"], "category": category(title + " " + description),
                        "published_at": date.isoformat(), "sources": [item_url]}
        article = BeautifulSoup(values.get("description") or values.get("summary") or values.get("content") or "", "html.parser")
        event = labelled_event(title, description, article, item_url, source)
        results.append(event or item)
    return results


def discover(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for link in soup.select('link[rel="alternate"][type]'):
        if link.get("type") in ("application/rss+xml", "application/atom+xml") and link.get("href"):
            url = canonical(urljoin(base, link["href"]))
            if urlsplit(url).scheme == "https":
                found.append({"id": digest(url), "name": text(link.get("title")) or urlsplit(url).hostname,
                              "url": url, "kind": "rss", "enabled": False, "trusted": False,
                              "access": "review_required", "discovered_from": base})
    # External organizer and media links are candidates only, with no inherited trust.
    for anchor in soup.select('a[href]')[:300]:
        label = text(anchor)
        url = canonical(urljoin(base, anchor["href"]))
        if urlsplit(url).scheme == "https" and urlsplit(url).hostname != urlsplit(base).hostname and any(w in label.casefold() for w in ("bilet", "organizatör", "gazete", "kültür", "dernek")):
            found.append({"id": digest(url), "name": label[:100], "url": url, "kind": "html",
                          "enabled": False, "trusted": False, "access": "review_required", "discovered_from": base})
    return found[:30]


def source_listing(source: dict, fetcher: Fetcher, listing: str):
    """Read one reviewed list atomically; another list can survive its failure."""
    items, candidates, links, seen = [], [], [], set()
    body, base = fetcher.get(listing)
    if source["kind"] in ("rss", "wp_rest", "izmir_art"):
        reader = {'rss':feed_items, 'wp_rest':wordpress_items, 'izmir_art':izmir_art_items}[source['kind']]
        found = reader(body, base, source)
        items.extend(found)
        if source.get("follow_feed_details", True):
            links.extend(item["url"] for item in found[:8])
    else:
        if source['kind'] not in ('hospital', 'rotary', 'official_notice'):
            items.extend(structured(body, base, source))
        candidates.extend(discover(body, base))
        soup = BeautifulSoup(body, "html.parser")
        for anchor in soup.select(source.get("link_selector", "article a[href], a[href*='haber'], a[href*='etkinlik']")):
            if not anchor.get("href"):
                continue
            link = page_url(urljoin(base, anchor["href"]))
            pattern = source.get("detail_url_pattern")
            if pattern and not re.search(pattern, urlsplit(link).path):
                continue
            if source.get("local_links_only") and not local(text(anchor) + " " + link.replace("-", " ")):
                continue
            identity = canonical(link)
            if urlsplit(link).hostname == urlsplit(base).hostname and identity != canonical(base) and identity not in seen:
                links.append(link)
                seen.add(identity)
    return items, candidates, links


def collect_source(source: dict, fetcher: Fetcher, known_events: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    from . import source_readers
    if source['kind']=='gdz_planned':
        return source_readers.collect_gdz_planned(source,fetcher,known_events)
    if source['kind']=='ticketing':
        return source_readers.collect_tickets(source,fetcher,known_events)
    if source['kind']=='rotary':
        return source_readers.collect_tickets(source,fetcher,known_events,reader=source_readers.rotary_items)
    if source['kind']=='mgm_warnings':
        return source_readers.collect_mgm(source,fetcher)
    if source['kind']=='izmir_culture':
        return source_readers.collect_culture(source,fetcher)
    if source['kind'] in ('afad_earthquakes','dated_program'):
        body,base=fetcher.get(source['url'])
        reader=source_readers.afad_items if source['kind']=='afad_earthquakes' else source_readers.program_items
        return reader(body,base,source),[],[]
    detail_reader = {'rotary':source_readers.rotary_items,
                     'hospital':source_readers.hospital_items,
                     'official_notice':source_readers.official_notice_items}.get(source['kind'],structured)
    if source['kind'] == 'municipal_calendar':
        return collect_municipal_calendar(source, fetcher)
    items, candidates, links, errors = [], [], [], []
    # A bounded set of district listings shares one source identity and page budget.
    listings = (source.get("listing_urls") or [source["url"]])[:6]
    if any(urlsplit(listing).hostname != urlsplit(source['url']).hostname for listing in listings):
        raise ValueError("Listing must belong to the configured source")
    listing_links = []
    first_failure = None
    for listing in listings:
        try:
            found, discovered, links = source_listing(source, fetcher, listing)
            items.extend(found)
            candidates.extend(discovered)
            listing_links.append(links)
        except (requests.RequestException, ValueError, OSError, ET.ParseError) as exc:
            first_failure = first_failure or exc
            errors.append({'source_id': source['id'], 'code': detail_error_code(exc).replace('detail_', 'listing_', 1)})
    if not listing_links and first_failure is not None:
        # Preserve whole-source failure semantics when no list was readable.
        raise first_failure
    # Round robin prevents a busy first district from starving nearby districts.
    links = [link for group in zip_longest(*listing_links) for link in group if link]
    # Revisit already announced future events, even when they leave the listing page.
    tracked = [e["url"] for e in known_events if e["source_id"] == source["id"]]
    unique_links = {}
    for link in tracked + links:
        unique_links.setdefault(canonical(link), link)
    links = list(unique_links.values())[:source.get("max_pages", 12)]
    for link in links:
        try:
            page, final = fetcher.get(link)
            extracted = detail_reader(page, final, source)
            items.extend(extracted)
            # Dedicated event pages can remove schema.org markup when cancelled.
            # Only an explicit statement at the original URL changes stored status.
            known = next((e for e in known_events if canonical(e["url"]) == canonical(link) and e["source_id"] == source["id"]), None)
            article = BeautifulSoup(page, "html.parser").select_one('article, .news-detail, .haber-detay')
            if known and article and not any(e["kind"] == "event" for e in extracted):
                body_text = text(article)
                cancelled = re.search(r"(?:bu\s+)?(?:etkinlik|konser|gösteri)\s+iptal\s+edil(?:di|miştir)", body_text, re.I)
                postponed = re.search(r"(?:bu\s+)?(?:etkinlik|konser|gösteri)\s+ertelen(?:di|miştir)", body_text, re.I)
                if cancelled or postponed:
                    update = {k: v for k, v in known.items() if k not in ("id", "revision", "first_seen", "last_seen")}
                    update.update(status="cancelled" if cancelled else "postponed", description=body_text[:3000])
                    items.append(update)
            candidates.extend(discover(page, final))
        except (requests.RequestException, ValueError, OSError) as exc:
            # Surface the source failure, rather than treating disappearance as cancellation.
            errors.append({"source_id": source["id"], "code": detail_error_code(exc)})
    # The feed representation of an event isn't an extra news announcement.
    event_urls = {i["url"] for i in items if i["kind"] == "event"}
    return [i for i in items if i["kind"] == "event" or i["url"] not in event_urls], candidates, errors

