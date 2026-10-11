"""Permitted RSS/Atom and schema.org collection, bounded per-source crawling.

No search-engine scraping, social login scraping or ticket-platform bypasses.
Unknown sources are candidates, never automatically trusted publishers.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .domain import TZ, canonical, category, digest, local, parse_date

AGENT = "SeferihisarOfficial/0.1 (+https://github.com/ntekintr/seferihisarofficial-news)"
MAX_BYTES = 2_000_000
MONTHS = {name: index for index, name in enumerate(("ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"), 1)}


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
            "url": canonical(url), "source_id": source["id"], "source_name": source["name"],
            "category": category(title + " " + description), "sources": [canonical(url)],
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
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError("Private or reserved network destination rejected")
    return canonical(url)


class Fetcher:
    def __init__(self, sources: list[dict], session=None):
        self.hosts = {urlsplit(s["url"]).hostname for s in sources if s.get("enabled")}
        self.session = session or requests.Session()
        self.robots: dict[str, RobotFileParser] = {}
        self.last_request: dict[str, float] = {}

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
                return body.decode(response.encoding or "utf-8", errors="replace"), url
            finally:
                response.close()
        raise ValueError("Too many redirects")

    def get(self, url: str) -> tuple[str, str]:
        host = urlsplit(url).hostname
        if host not in self.robots:
            robot = RobotFileParser()
            # Fail closed on inaccessible robots.txt. 404 can be reviewed by source owner.
            body, _ = self.request(f"https://{host}/robots.txt")
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


def structured(html: str, url: str, source: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
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
            description = text(obj.get("description") or obj.get("articleBody"))[:3000]
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
            item_url = canonical(urljoin(url, obj.get("url") if isinstance(obj.get("url"), str) else url))
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
                identity = obj.get("@id") or item_url
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
            results.append(item)
    if not results:
        # Common WordPress and municipal article metadata, without guessing dates.
        headline = soup.select_one('meta[property="og:title"]')
        published = soup.select_one('meta[property="article:published_time"], meta[name="date"], time[datetime]')
        article = soup.select_one('article .entry-content, article .article-content, article, .news-detail, .haber-detay')
        date = parse_date((published.get("content") or published.get("datetime")) if published else None)
        title = text(headline.get("content")) if headline else text(soup.find("h1"))
        if article and date and title:
            for removable in article.select('script, style, nav, footer, .comments, .sharedaddy'):
                removable.decompose()
            paragraphs = [text(p) for p in article.select("p")]
            description = " ".join(p for p in paragraphs if len(p) > 30)[:3000]
            if description and local(title + " " + description):
                event = labelled_event(title, description, article, url, source)
                results.append(event or {"kind": "news", "title": title[:240], "description": description,
                                "url": canonical(url), "source_id": source["id"], "source_name": source["name"],
                                "category": category(title + " " + description), "published_at": date.isoformat(), "sources": [canonical(url)]})
        elif article and title:
            description = text(article)[:3000]
            if local(title + " " + description):
                event = labelled_event(title, description, article, url, source)
                if event:
                    results.append(event)
    return results


def feed_items(xml: str, base: str, source: dict) -> list[dict]:
    root = ET.fromstring(xml)
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
        raw_date = values.get("pubDate") or values.get("published") or values.get("updated")
        date = parse_date(raw_date)
        if not date and raw_date:
            try:
                date = parsedate_to_datetime(raw_date).astimezone(TZ)
            except (ValueError, TypeError):
                pass
        if not date:
            continue
        results.append({"kind": "news", "title": title[:240], "description": description, "url": canonical(urljoin(base, link)),
                        "source_id": source["id"], "source_name": source["name"], "category": category(title + " " + description),
                        "published_at": date.isoformat(), "sources": [canonical(urljoin(base, link))]})
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


def collect_source(source: dict, fetcher: Fetcher, known_events: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    body, base = fetcher.get(source["url"])
    if source["kind"] == "rss":
        items = feed_items(body, base, source)
        candidates = []
        links = [item["url"] for item in items[:8]]
    else:
        items = structured(body, base, source)
        candidates = discover(body, base)
        soup = BeautifulSoup(body, "html.parser")
        links = []
        for anchor in soup.select(source.get("link_selector", "article a[href], a[href*='haber'], a[href*='etkinlik']")):
            if anchor.get("href"):
                link = canonical(urljoin(base, anchor["href"]))
                if urlsplit(link).hostname == urlsplit(base).hostname and link != base and link not in links:
                    links.append(link)
    # Revisit already announced future events, even when they leave the listing page.
    tracked = [e["url"] for e in known_events if e["source_id"] == source["id"]]
    links = list(dict.fromkeys(tracked + links))[:source.get("max_pages", 12)]
    errors = []
    for link in links:
        try:
            page, final = fetcher.get(link)
            extracted = structured(page, final, source)
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
        except (requests.RequestException, ValueError, OSError):
            # Surface the source failure, rather than treating disappearance as cancellation.
            errors.append({"source_id": source["id"], "code": "detail_check_failed"})
    # The feed representation of an event isn't an extra news announcement.
    event_urls = {i["url"] for i in items if i["kind"] == "event"}
    return [i for i in items if i["kind"] == "event" or i["url"] not in event_urls], candidates, errors
