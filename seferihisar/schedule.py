from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, time, timedelta

from .domain import TZ, digest, parse_date
from .editor import caption, caption_with_hashtags, digest_hashtags, event_date_label, event_title, excerpt, headline, news_body, plain_source_text
from .media_caption import generated_image_caption
from .store import Store
from .timeliness import publication_reason
from . import event_metadata

SLOTS = (time(8, 30), time(12, 30), time(15), time(18, 30), time(21))
SOURCE_MAX_AGE = timedelta(hours=1)


def blocked_sources(store: Store) -> set[str]:
    import json
    latest = store.rows("SELECT errors FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1")
    return {e["source_id"] for e in json.loads(latest[0]["errors"])} if latest else set()


def source_current(item: dict, at: datetime, failed: set[str]) -> bool:
    seen = parse_date(item.get("last_seen"))
    if publication_reason(item, at):
        return False
    return item["source_id"] not in failed and seen is not None and at - SOURCE_MAX_AGE <= seen <= at + timedelta(minutes=5)


def next_slot(at: datetime, event: bool = False) -> datetime:
    slots = (time(15),) if event else SLOTS
    for slot in slots:
        candidate = datetime.combine(at.date(), slot, TZ)
        if candidate >= at:
            return candidate
    return datetime.combine(at.date() + timedelta(days=1), slots[0], TZ)


def prepare(store: Store, at: datetime, *, refresh_digests: bool = True):
    failed = blocked_sources(store)
    current = {i["id"]: i for i in store.items()}
    by_url = {url: i for i in current.values() for url in i.get("sources", []) + [i["url"]]}
    with store.db:
        for post in store.posts():
            if post["status"] not in ("prepared", "blocked_source"):
                continue
            references = [current.get(post["item_id"])] if post.get("item_id") else [by_url.get(url) for url in post["source_urls"]]
            from .publication_policy import post_reason
            valid = (bool(references) and all(item and source_current(item, at, failed) for item in references)
                     and post_reason(store, post, at) is None)
            store.db.execute("UPDATE posts SET status=? WHERE id=?", ("prepared" if valid else "blocked_source", post["id"]))
    for item in store.items():
        from .quality import news_editorial_reason
        if reason := news_editorial_reason(item):
            store.withhold(item['id']+':editorial', reason, at.isoformat())
            continue
        if not source_current(item, at, failed):
            continue
        if item["kind"] == "news":
            if at - parse_date(item["published_at"]) > timedelta(days=7):
                continue
            urgent = item["category"] in ("outage", "weather", "transport")
            from .publication_policy import evening_news_item
            due_now = urgent or evening_news_item(item, at, bonus=False)
            queue_item(store, item, "news", at if due_now else next_slot(at), at)
            continue
        start = parse_date(item["start"])
        if item['category']=='outage':
            if parse_date(item['end'])>at:
                queue_item(store,item,'cancellation' if item['status']=='cancelled' else 'update' if item['revision']>1 else 'announcement',at,at)
            continue
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
            expired = publication_reason(item, at) in ('expired_news', 'expired_event', 'expired_service_notice')
            expired |= post["kind"] in ("reminder_3d", "reminder_day") and parse_date(post["created_at"]).date() != at.date()
            if expired:
                store.db.execute("UPDATE posts SET status='expired' WHERE id=?", (post["id"],))
    # Dispatch revalidates the original references. Replacing an expired slide
    # here would approve different content under an already-deployed image URL.
    # Only normal research rebuilds editions together with their Pages media.
    if refresh_digests:
        prepare_digest(store, at, "weekly", 7)
        prepare_digest(store, at, "monthly", 30)
        from .local_series import prepare as prepare_series
        prepare_series(store, at)
    from .local_series import expired as series_expired
    with store.db:
        for post in store.posts():
            if post['status'] in ('prepared', 'blocked_source') and series_expired(post, at):
                store.db.execute("UPDATE posts SET status='expired' WHERE id=?", (post['id'],))
    from .story_identity import repeat
    from .publication_policy import duplicate_reason, post_reason
    for post in store.posts():
        if post['status'] != 'prepared':
            continue
        reason = (post_reason(store, post, at) or duplicate_reason(store, post)
                  or ('duplicate_story' if repeat(store, post) else None))
        if reason:
            with store.db:
                store.db.execute("UPDATE posts SET status='blocked_source' WHERE id=? AND status='prepared'", (post['id'],))
            store.withhold(post['id'], reason, at.isoformat())


def queue_item(store: Store, item: dict, kind: str, due: datetime, at: datetime):
    from .editor import editorial_category
    days = (parse_date(item["start"]).date() - at.date()).days if item["kind"] == "event" else None
    title = headline(item, kind)
    if kind == "reminder_3d" and days != 3:
        title = f"{days} gün kaldı: {event_title(item)}"
    key = digest(f"{item['id']}:{item['revision']}:{kind}")
    post = {"id": key, "item_id": item["id"], "revision": item["revision"], "kind": kind,
                 "due_at": due.isoformat(), "title": title, "caption": caption(item, title),
                 "category": editorial_category(item), "source_urls": item["sources"],
                 "slides": [{"title": title, "body": slide_body(item)}],
                 "created_at": at.isoformat(), "formats": ["carousel", "story"] if item["kind"] == "event" and item['category']!='outage' else ["feed", "story"]}
    if store.queue(post):
        return
    rows = store.rows("SELECT payload,status,revision FROM posts WHERE id=?", (key,))
    if not rows or rows[0]["status"] not in ("prepared", "blocked_source") or rows[0]["revision"] != item["revision"]:
        return
    # A wording/layout change may refresh an unclaimed card, but keeps its
    # identity and due date. Published, in-flight and uncertain claims are frozen.
    previous = json.loads(rows[0]["payload"])
    from .publication_policy import evening_news_item
    post["due_at"] = (min(parse_date(previous['due_at']), at).isoformat()
                      if evening_news_item(item, at, bonus=False) else previous["due_at"])
    post["created_at"] = previous["created_at"]
    if "illustration_keys" in previous:
        post["illustration_keys"] = previous["illustration_keys"]
    if 'source_photo_keys' in previous:
        post['source_photo_keys']=deepcopy(previous['source_photo_keys'])
    if 'card_layout' in previous:
        post['card_layout']=previous['card_layout']
    if 'brand_version' in previous:
        post['brand_version']=previous['brand_version']
    if "visual_review" in previous:
        post['visual_review'] = deepcopy(previous['visual_review'])
    post["caption"] = generated_image_caption(post["caption"], bool(post.get("illustration_keys")))
    with store.db:
        store.db.execute("UPDATE posts SET payload=? WHERE id=? AND revision=? AND status IN ('prepared','blocked_source')",
                         (json.dumps(post, ensure_ascii=False), key, item["revision"]))


def card_location(item: dict) -> str | None:
    """Use the named venue; leave its explicit street address in the caption."""
    location = event_metadata.location(item)
    if (item.get('source_id') in ('bubilet-bademler', 'biletinial-bademler') and location
            and location.startswith('Bademler Sanat Köyü ')):
        return 'Bademler Sanat Köyü'
    if location and " · " in location:
        venue, address = location.split(" · ", 1)
        if venue.strip() and re.search(r"\b(?:mahalle\w*|mah\.?|cadde\w*|cad\.?|sokak\w*|sok\.?|adres)\b|\bno\s*[:.]", address, re.I):
            return venue.strip()
    return location


def slide_body(item: dict) -> str:
    if item["kind"] == "news":
        body = news_body(item)
        endings = [match.end() for match in re.finditer(r'[.!?](?=\s|$)', body[:300]) if match.end() >= 80]
        return body[:endings[min(1,len(endings)-1)]] if endings else excerpt(body, 300)
    if item['category']=='outage':
        return event_date_label(item)+'\n\nEtkilenen bölge: '+(item.get('location') or 'Açıklanmadı')+'\n\nMahalle ve sokak ayrıntıları için resmî duyuruyu kontrol edin.'
    details = [event_date_label(item)]
    if location := card_location(item):
        details.append(location)
    if organizer := event_metadata.organizer(item):
        details.append("Düzenleyen: " + organizer)
    if item.get("free") is True:
        details.append("Ücretsiz")
    elif item.get("price"):
        currency = 'TL' if (item.get('currency') or '').upper() == 'TRY' else item.get('currency')
        details.append("Ücret: " + item["price"] + (" " + currency if currency else ""))
    elif item.get("free") is False:
        details.append("Ücretli")
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
                and e['category']!='outage'
                and parse_date(e["start"]).date() <= at.date() + timedelta(days=days)
                and parse_date(e["end"]).date() >= at.date()
                and (not e.get("time_known") or parse_date(e["end"]) > at)
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
    cover = (at.strftime('%d.%m.%Y') + ' – ' + (at + timedelta(days=days)).strftime('%d.%m.%Y')
             + f'\n\n{len(selected)} etkinlikten seçki\n\n'
             + '\n\n'.join(excerpt(event_title(e), 85) + '\n' + event_date_label(e, include_time=False) for e in selected[:3]))
    if len(selected) > 3:
        cover += '\n\nDevamı sonraki kartlarda →'
    slides = [{"title": title, "body": cover}] + [{"title": event_title(e), "body": slide_body(e), "category": e["category"]} for e in selected]
    content = "\n\n".join([title, description] + [event_title(e) + " · " + event_date_label(e, include_time=False) + "\nKaynak: " + plain_source_text(e["source_name"]) + "\n" + e["url"] for e in selected])
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
            if 'visual_review' in existing:
                post['visual_review'] = deepcopy(existing['visual_review'])
        post["caption"] = generated_image_caption(post["caption"], bool(post.get("illustration_keys")))
        with store.db:
            store.db.execute("UPDATE posts SET payload=?,status='prepared' WHERE id=?", (json.dumps(post, ensure_ascii=False), key))
    else:
        store.queue(post)


