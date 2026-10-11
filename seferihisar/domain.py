from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
PLACES = ("seferihisar", "sığacık", "sigacik", "ürkmez", "urkmez", "doğanbey", "doganbey", "akarca", "ulamış", "ulamis", "orhanlı", "orhanli")
NEARBY_PLACES = ("güzelbahçe", "guzelbahce", "urla", "yelki", "özdere", "ozdere")
NEARBY_TOPICS = ("konser", "festival", "şenlik", "senlik", "tiyatro", "sinema", "sergi", "etkinlik", "ulaşım", "ulasim", "eshot", "yol çalış", "yol calis", "yol kap", "kesinti", "fırtına", "firtina", "sağanak", "saganak", "sel uyar", "deprem", "yangın", "yangin", "tahliye", "kamu duyuru", "sağlık uyar", "saglik uyar", "hastane aç", "hastane kap")
CATEGORIES = {
    "news": "Yerel Haberler", "municipality": "Belediye", "concert": "Konserler",
    "festival": "Festivaller", "theatre": "Tiyatro", "cinema": "Sinema",
    "culture": "Kültür & Sanat", "event": "Etkinlikler", "family": "Aile & Çocuk",
    "sport": "Spor", "market": "Pazar & Fuar", "food": "Gastronomi",
    "tourism": "Turizm", "transport": "Ulaşım", "outage": "Kesintiler",
    "weather": "Hava Durumu", "education": "Eğitim", "health": "Sağlık",
    "public": "Kamu Duyuruları",
}
TERMS = {
    "concert": ("konser", "canlı müzik"), "festival": ("festival",),
    "theatre": ("tiyatro",), "cinema": ("sinema", "film göster"),
    "family": ("çocuk", "aile"), "sport": ("turnuva", "spor", "koşu"),
    "market": ("pazar", "fuar", "kermes"), "food": ("gastronomi", "mandalina", "zeytin"),
    "culture": ("sergi", "sanat", "atölye"), "transport": ("eshot", "trafik", "yol çalış"),
    "outage": ("kesinti", "elektrik", "su kes"), "weather": ("meteoroloji", "fırtına", "yağış"),
    "education": ("kurs", "seminer", "eğitim"), "health": ("sağlık",),
    "tourism": ("turizm", "gezi"), "municipality": ("belediye",),
    "public": ("kaymakam", "afad"), "event": ("etkinlik", "şenlik"),
}
SENSITIVE = re.compile(r"cinayet|ölüm|öldü|vefat|intihar|yaral[ıa]|suç|tutuk|gözaltı|tecavüz|istismar|yolsuz|rüşvet|dolandır|iddia|siyasi|seçim|partisi|mahkeme|şüpheli|itham|skandal|istifa|kaçak|hırsız|ifşa|saldırı|göçmen|yakalan|uyuşturucu", re.I)


def now() -> datetime:
    return datetime.now(TZ)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    except (ValueError, TypeError, AttributeError):
        return None


def canonical(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k not in ("fbclid", "gclid")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def normalized(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold().replace("\u0307", "").replace("ı", "i")).strip()


def local(text: str) -> bool:
    value = normalized(text)
    def mentions(places):
        return any(re.search(r"\b" + re.escape(normalized(place)) + r"\b", value) for place in places)
    return mentions(PLACES) or (mentions(NEARBY_PLACES) and any(normalized(word) in value for word in NEARBY_TOPICS))


def category(text: str) -> str:
    text = text.casefold()
    return next((key for key, words in TERMS.items() if any(w in text for w in words)), "news")
