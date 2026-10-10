from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .collect import Fetcher, collect_source
from .domain import now, parse_date
from .editor import ai_priority, verify
from .render import render_post
from .schedule import prepare
from .store import Store


def run(db_path: Path, public_dir: Path, sources_path: Path, at: datetime | None = None, fixture: Path | None = None) -> dict:
    at = at or now()
    sources = json.loads(sources_path.read_text())
    source_map = {s["id"]: s for s in sources}
    store = Store(db_path)
    errors = []
    collected = 0
    try:
        with store.db:
            run_id = store.db.execute("INSERT INTO runs(started_at) VALUES (?)", (at.isoformat(),)).lastrowid
        incoming = []
        candidates = []
        if fixture:
            incoming = json.loads(fixture.read_text())
        else:
            fetcher = Fetcher(sources)
            tracked = [e for e in store.items("event") if parse_date(e["start"]).date() >= at.date() - timedelta(days=1)]
            for source in sources:
                if not source.get("enabled") or source.get("access") not in ("robots", "api", "licensed"):
                    continue
                try:
                    found, discovered, detail_errors = collect_source(source, fetcher, tracked)
                    incoming.extend(found)
                    candidates.extend(discovered)
                    errors.extend(detail_errors)
                except Exception:
                    # Only controlled codes are retained; URLs/exceptions can contain tokens.
                    errors.append({"source_id": source["id"], "code": "collection_failed"})
        for candidate in candidates:
            # Candidate labels/URLs are untrusted and might contain private query data.
            from urllib.parse import urlsplit
            split = urlsplit(candidate["url"])
            candidate["url"] = f"https://{split.hostname}{split.path}"
            candidate["name"] = split.hostname
            candidate.pop("discovered_from", None)
            with store.db:
                store.db.execute("INSERT OR IGNORE INTO candidates VALUES (?,?)", (candidate["id"], json.dumps(candidate)))
        for item in incoming:
            source = source_map.get(item.get("source_id"), {})
            reason = verify(item, source, at)
            if reason:
                store.withhold(item.get("url", "") + ":" + item.get("title", ""), reason, at.isoformat())
                continue
            # URL fields may contain access tokens. Retain only canonical public links.
            if unsafe_item_links(item):
                store.withhold(item["url"], "non_public_url", at.isoformat())
                continue
            key, changed = store.upsert(item, at.isoformat())
            if changed:
                collected += 1
                # Priority metadata cannot change verified text or activate publishing.
                priority = ai_priority(item)
                if priority is not None:
                    with store.db:
                        store.db.execute("INSERT OR REPLACE INTO annotations VALUES (?,?,?)", (key, priority, at.isoformat()))
        # If a formerly safe article becomes sensitive, remove its public payload immediately.
        revoked = {item.get("url") for item in incoming if verify(item, source_map.get(item.get("source_id"), {}), at) in ("human_review_required", "unverified_source", "unverified_origin")}
        with store.db:
            for old in store.items():
                if old["url"] in revoked:
                    store.db.execute("DELETE FROM posts WHERE item_id=?", (old["id"],))
                    store.db.execute("DELETE FROM items WHERE id=?", (old["id"],))
        prepare(store, at)
        with store.db:
            store.db.execute("UPDATE runs SET finished_at=?,collected=?,errors=? WHERE id=?", ((now() if not fixture else at).isoformat(), collected, json.dumps(errors), run_id))
            store.db.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 100)")
        result = export(store, public_dir, sources, at, demo=bool(fixture))
        return {"collected": collected, "prepared": len([p for p in store.posts() if p["status"] == "prepared"]), "errors": len(errors), "assets": result}
    finally:
        store.close()


def unsafe_item_links(item: dict) -> bool:
    from urllib.parse import parse_qsl, urlsplit
    for url in [item["url"], item.get("ticket_url"), item.get("identity")] + item.get("sources", []):
        if not url:
            continue
        split = urlsplit(url)
        if split.scheme != "https" or split.username or split.password:
            return True
        if any(k.casefold() == "key" or any(sensitive in k.casefold() for sensitive in ("token", "api_key", "auth", "signature", "password", "secret", "credential")) for k, _ in parse_qsl(split.query)):
            return True
    return False


def export(store: Store, public_dir: Path, sources: list[dict], at: datetime, demo=False) -> dict:
    public_dir.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    for path in (root / "site").iterdir():
        if path.is_file():
            shutil.copy2(path, public_dir / path.name)
    posts = store.posts()
    assets = {}
    # Public output always rebuilt; removed/sensitive/superseded images cannot linger.
    shutil.rmtree(public_dir / "media", ignore_errors=True)
    for post in [p for p in posts if not p.get("publish_format")][:100]:
        if post["status"] in ("prepared", "published", "publishing", "uncertain"):
            assets[post["id"]] = render_post(post, public_dir)
    events = sorted((e for e in store.items("event") if parse_date(e["start"]).date() >= at.date() - timedelta(days=1)), key=lambda e: e["start"])
    news = sorted((i for i in store.items("news") if parse_date(i["published_at"]) >= at - timedelta(days=7)), key=lambda i: i["published_at"], reverse=True)
    public_posts = [{"id": p["id"], "kind": p["kind"], "title": p["title"], "due_at": p["due_at"], "status": p["status"],
                     "caption": p["caption"], "assets": assets.get(p["id"], {}), "category": p["category"]} for p in posts[:100] if p["status"] not in ("superseded", "expired") and not p.get("publish_format")]
    snapshot = {"schema_version": 1, "generated_at": at.isoformat(), "demo": demo,
                "publishing_enabled": False, "news": news, "events": events, "posts": public_posts,
                "withheld_count": store.db.execute("SELECT COUNT(*) FROM withheld").fetchone()[0],
                "sources": [public_source(s) for s in sources],
                "candidate_count": store.db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
                "runs": [{**r, "errors": json.loads(r["errors"])} for r in store.rows("SELECT * FROM runs ORDER BY id DESC LIMIT 20")]}
    (public_dir / "data.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    (public_dir / ".nojekyll").touch()
    export_calendar(events, public_dir)
    return assets


def public_source(source: dict) -> dict:
    from urllib.parse import urlsplit
    result = {k: source.get(k) for k in ("id", "name", "kind", "enabled", "trusted", "access")}
    parts = urlsplit(source["url"])
    result["url"] = f"https://{parts.hostname}{parts.path}"
    return result


def export_calendar(events: list[dict], public_dir: Path):
    def escape(value):
        return str(value or "").replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
    def fold(line):
        # RFC5545 folding is in octets, not Python code points (Turkish UTF-8).
        chunks, current = [], ""
        for char in line:
            if len((current + char).encode()) > 73:
                chunks.append(current)
                current = " "
            current += char
        chunks.append(current)
        return chunks
    from datetime import timezone
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Seferihisar Official//Etkinlik//TR", "CALSCALE:GREGORIAN"]
    for event in events:
        lines += ["BEGIN:VEVENT", f"UID:{event['id']}@seferihisarofficial", "SEQUENCE:" + str(event["revision"]),
                  "DTSTAMP:" + parse_date(event["last_seen"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")]
        start = parse_date(event["start"])
        if event.get("time_known"):
            lines.append("DTSTART:" + start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        else:
            lines.append("DTSTART;VALUE=DATE:" + start.strftime("%Y%m%d"))
        lines += ["SUMMARY:" + escape(event["title"]), "LOCATION:" + escape(event.get("location")), "URL:" + event["url"],
                  "STATUS:" + ("CANCELLED" if event["status"] == "cancelled" else "TENTATIVE" if event["status"] == "postponed" else "CONFIRMED"), "END:VEVENT"]
    lines.append("END:VCALENDAR")
    (public_dir / "events.ics").write_bytes(("\r\n".join(chunk for line in lines for chunk in fold(line)) + "\r\n").encode())
