from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, time, timedelta

from .domain import TZ, digest, parse_date
from .editor import caption, caption_with_hashtags, digest_hashtags, event_date_label, event_title, headline, news_body
from .media_caption import generated_image_caption
from .store import Store

SLOTS = (time(8, 30), time(12, 30), time(15), time(18, 30), time(21))
SOURCE_MAX_AGE = timedelta(hours=1)


def blocked_sources(store: Store) -> set[str]:
    import json
    latest = store.rows("SELECT errors FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1")
    return {e["source_id"] for e in json.loads(latest[0]["errors"])} if latest else set()


def source_current(item: dict, at: datetime, failed: set[str]) -> bool:
    seen = parse_date(item.get("last_seen"))
    return item["source_id"] not in failed and seen is not None and at - SOURCE_MAX_AGE <= seen <= at + timedelta(minutes=5)


def next_slot(at: datetime, event: bool = False) -> datetime:
    slots = (time(15),) if event else SLOTS
    for slot in slots:
        candidate = datetime.combine(at.date(), slot, TZ)
        if candidate >= at:
            return candidate
    return datetime.combine(at.date() + timedelta(days=1), slots[0], TZ)


def prepare(store: Store, at: datetime):
    failed = blocked_sources(store)
    current = {i["id"]: i for i in store.items()}
    by_url = {url: i for i in current.values() for url in i.get("sources", []) + [i["url"]]}
    with store.db:
        for post in store.posts():
            if post["status"] not in ("prepared", "blocked_source"):
                continue
            references = [current.get(post["item_id"])] if post.get("item_id") else [by_url.get(url) for url in post["source_urls"]]
            valid = bool(references) and all(item and source_current(item, at, failed) for item in references)
            store.db.execute("UPDATE posts SET status=? WHERE id=?", ("prepared" if valid else "blocked_source", post["id"]))
    for item in store.items():
        if not source_current(item, at, failed):
            continue
        if item["kind"] == "news":
            if at - parse_date(item["published_at"]) > timedelta(days=7):
                continue
            urgent = item["category"] in ("outage", "weather", "transport")
            queue_item(store, item, "news", at if urgent else next_slot(at), at)
            continue
        start = parse_date(item["start"])
        if item["status"] in ("cancelled", "postponed"):
            queue_item(store, item, "cancellation" if item["status"] == "cancelled" else "update", at, at)
            continue
        if start.date() < at.date():
            continue
        if item["revision"] > 1:
            queue_item(store, item, "update", at, at)
        elif start <= at + timedelta(days=30):
            queue_item(store, item, "announcement", min(next_slot(at, event=True), start) if item.get("time_known") else at, at)
        days = (start.date() - at.date()).days
        # A delayed run catches the 3-day reminder on days 2/1; never posts it after the event.
        if 0 < days <= 3:
            queue_item(store, item, "reminder_3d", at, at)
        if days == 0 and (not item.get("time_known") or start >= at):
            queue_item(store, item, "reminder_day", at, at)
    # Expire stale prepared posts, including reminders whose event has passed.
    current = {i["id"]: i for i in store.items()}
    with store.db:
        for post in store.posts():
            item = current.get(post.get("item_id"))
            if post["status"] not in ("prepared", "blocked_source"):
                continue
            if not item:
                if post["kind"] in ("weekly", "monthly") and parse_date(post["due_at"]) < at - timedelta(days=2):
                    store.db.execute("UPDATE posts SET status='expired' WHERE id=?", (post["id"],))
                continue
            expired = item["kind"] == "news" and at - parse_date(item["published_at"]) > timedelta(days=2)
            expired |= item["kind"] == "event" and item["status"] not in ("cancelled", "postponed") and (parse_date(item["end"]).date() < at.date() or (item.get("time_known") and parse_date(item["end"]) < at))
            expired |= post["kind"] in ("reminder_3d", "reminder_day") and parse_date(post["created_at"]).date() != at.date()
            if expired:
                store.db.execute("UPDATE posts SET status='expired' WHERE id=?", (post["id"],))
    prepare_digest(store, at, "weekly", 7)
    prepare_digest(store, at, "monthly", 30)


def queue_item(store: Store, item: dict, kind: str, due: datetime, at: datetime):
    days = (parse_date(item["start"]).date() - at.date()).days if item["kind"] == "event" else None
    title = headline(item, kind)
    if kind == "reminder_3d" and days != 3:
        title = f"{days} gün kaldı: {event_title(item)}"
    key = digest(f"{item['id']}:{item['revision']}:{kind}")
    post = {"id": key, "item_id": item["id"], "revision": item["revision"], "kind": kind,
                 "due_at": due.isoformat(), "title": title, "caption": caption(item, title),
                 "category": item["category"], "source_urls": item["sources"],
                 "slides": [{"title": title, "body": slide_body(item)}],
                 "created_at": at.isoformat(), "formats": ["carousel", "story"] if item["kind"] == "event" else ["feed", "story"]}
    if store.queue(post):
        return
    rows = store.rows("SELECT payload,status,revision FROM posts WHERE id=?", (key,))
    if not rows or rows[0]["status"] not in ("prepared", "blocked_source") or rows[0]["revision"] != item["revision"]:
        return
    # A wording/layout change may refresh an unclaimed card, but keeps its
    # identity and due date. Published, in-flight and uncertain claims are frozen.
    previous = json.loads(rows[0]["payload"])
    post["due_at"] = previous["due_at"]
    post["created_at"] = previous["created_at"]
    if "illustration_keys" in previous:
        post["illustration_keys"] = previous["illustration_keys"]
    post["caption"] = generated_image_caption(post["caption"], bool(post.get("illustration_keys")))
    with store.db:
        store.db.execute("UPDATE posts SET payload=? WHERE id=? AND revision=? AND status IN ('prepared','blocked_source')",
                         (json.dumps(post, ensure_ascii=False), key, item["revision"]))


def card_location(item: dict) -> str | None:
    """Use the named venue; leave its explicit street address in the caption."""
    location = item.get("location")
    if location and " · " in location:
        venue, address = location.split(" · ", 1)
        if venue.strip() and re.search(r"\b(?:mahalle\w*|mah\.?|cadde\w*|cad\.?|sokak\w*|sok\.?|adres)\b|\bno\s*[:.]", address, re.I):
            return venue.strip()
    return location


def slide_body(item: dict) -> str:
    if item["kind"] == "news":
        return news_body(item)[:650] + "\n\nKaynak: " + item["source_name"]
    details = [event_date_label(item)]
    if location := card_location(item):
        details.append(location)
    if item.get("organizer"):
        details.append("Düzenleyen: " + item["organizer"])
    if item.get("free") is True:
        details.append("Ücretsiz")
    elif item.get("price"):
        currency = 'TL' if (item.get('currency') or '').upper() == 'TRY' else item.get('currency')
        details.append("Ücret: " + item["price"] + (" " + currency if currency else ""))
    elif item.get("free") is False:
        details.append("Ücretli")
    details.append("Kaynak: " + item["source_name"])
    return "\n\n".join(details)


def prepare_digest(store: Store, at: datetime, kind: str, days: int):
    if kind == "weekly":
        period = (at.date() - timedelta(days=at.weekday())).isoformat()
        title = "Seferihisar ve Çevresinde Bu Hafta"
    else:
        period = at.strftime("%Y-%m")
        title = "Seferihisar ve Çevresi Etkinlik Takvimi"
    failed = blocked_sources(store)
    # Short festivals can remain in an edition after their first day. A long
    # program/annual series is not evidence of a continuous current occurrence.
    upcoming = [e for e in store.items("event")
                if e["status"] in ("scheduled", "rescheduled")
                and parse_date(e["start"]).date() <= at.date() + timedelta(days=days)
                and parse_date(e["end"]).date() >= at.date()
                and (not e.get("time_known") or parse_date(e["end"]) >= at)
                and (parse_date(e["start"]).date() >= at.date()
                     or parse_date(e["end"]).date() - parse_date(e["start"]).date() <= timedelta(days=6))]
    events = sorted((e for e in upcoming if source_current(e, at, failed)), key=lambda e: e["start"])
    if not events:
        with store.db:
            store.db.execute("UPDATE posts SET status=? WHERE id=? AND status IN ('prepared','blocked_source')", ("blocked_source" if upcoming else "superseded", digest(kind + ":" + period)))
        return
    # Refresh an unpublished digest when events change; never repeat a published edition.
    key = digest(kind + ":" + period)
    existing = next((p for p in store.posts() if p["id"] == key), None)
    if existing and existing["status"] not in ("prepared", "blocked_source"):
        return
    selected = events[:9]  # Meta carousel cover + 9 slides; do not imply a complete calendar.
    description = f"{at.strftime('%d.%m.%Y')} itibarıyla önümüzdeki {days} gün için doğrulanmış etkinliklerden seçki."
    slides = [{"title": title, "body": description}] + [{"title": event_title(e), "body": slide_body(e), "category": e["category"]} for e in selected]
    content = "\n\n".join([title, description] + [event_title(e) + " · " + event_date_label(e, include_time=False) + "\nKaynak: " + e["url"] for e in selected])
    post = {"id": key, "kind": kind, "revision": 1, "due_at": next_slot(at, event=True).isoformat(),
            "title": title, "caption": caption_with_hashtags(content, digest_hashtags(selected)), "category": "event", "slides": slides,
            "source_urls": [e["url"] for e in selected], "created_at": at.isoformat(), "formats": ["carousel", "story"]}
    if existing:
        # Keep original due date so frequent runs cannot postpone it indefinitely.
        post["due_at"] = existing["due_at"]
        # The publisher refreshes text with illustration generation disabled.
        # Retain bindings only while each event still occupies the same slide.
        if (existing["source_urls"] == post["source_urls"]
                and len(existing["slides"]) == len(post["slides"])
                and "illustration_keys" in existing):
            post["illustration_keys"] = deepcopy(existing["illustration_keys"])
        post["caption"] = generated_image_caption(post["caption"], bool(post.get("illustration_keys")))
        with store.db:
            store.db.execute("UPDATE posts SET payload=?,status='prepared' WHERE id=?", (json.dumps(post, ensure_ascii=False), key))
    else:
        store.queue(post)


