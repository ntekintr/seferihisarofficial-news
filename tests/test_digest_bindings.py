import json
from datetime import timedelta

import pytest

from seferihisar.schedule import prepare

AI_NOTICE = "Görsel: yapay zekâyla hazırlanmış temsili görsel."


def bind_calendar(store, post, bindings, status="prepared"):
    payload = json.loads(store.rows("SELECT payload FROM posts WHERE id=?", (post["id"],))[0]["payload"])
    payload["illustration_keys"] = bindings
    with store.db:
        store.db.execute("UPDATE posts SET payload=?,status=? WHERE id=?",
                         (json.dumps(payload), status, post["id"]))


@pytest.mark.parametrize("status", ["prepared", "blocked_source"])
def test_unclaimed_calendar_refresh_preserves_same_slide_bindings(store, event, at, status):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    original = {p["kind"]: p for p in store.posts() if p["kind"] in ("weekly", "monthly")}
    for post in original.values():
        bind_calendar(store, post, {"1": "a" * 24}, status)
    prepare(store, at + timedelta(minutes=15))
    for post in store.posts():
        if post["kind"] in original:
            assert post["illustration_keys"] == {"1": "a" * 24}
            assert post["source_urls"] == original[post["kind"]]["source_urls"]
            assert post["due_at"] == original[post["kind"]]["due_at"]
            assert AI_NOTICE not in post["caption"]


def test_changed_event_order_drops_calendar_bindings(store, event, at):
    first = {**event, "start": (at + timedelta(days=1)).isoformat(),
             "end": (at + timedelta(days=1, hours=2)).isoformat()}
    second = {**event, "title": "İkinci etkinlik", "url": event["url"] + "-2",
              "identity": event["identity"] + "-2", "sources": [event["url"] + "-2"],
              "start": (at + timedelta(days=2)).isoformat(),
              "end": (at + timedelta(days=2, hours=2)).isoformat()}
    store.upsert(first, at.isoformat())
    store.upsert(second, at.isoformat())
    prepare(store, at)
    for post in store.posts():
        if post["kind"] in ("weekly", "monthly"):
            assert post["source_urls"] == [first["url"], second["url"]]
            bind_calendar(store, post, {"1": "a" * 24, "2": "b" * 24})
    first.update(start=(at + timedelta(days=3)).isoformat(), end=(at + timedelta(days=3, hours=2)).isoformat())
    refreshed_at = at + timedelta(minutes=15)
    store.upsert(first, refreshed_at.isoformat())
    prepare(store, refreshed_at)
    for post in store.posts():
        if post["kind"] in ("weekly", "monthly"):
            assert post["source_urls"] == [second["url"], first["url"]]
            assert "illustration_keys" not in post
            assert AI_NOTICE not in post["caption"]


def test_changed_slide_count_drops_calendar_bindings(store, event, at):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    for post in store.posts():
        if post["kind"] not in ("weekly", "monthly"):
            continue
        payload = json.loads(store.rows("SELECT payload FROM posts WHERE id=?", (post["id"],))[0]["payload"])
        payload["illustration_keys"] = {"1": "a" * 24}
        payload["slides"].append({"title": "Eski fazladan slayt", "body": "Eski içerik"})
        with store.db:
            store.db.execute("UPDATE posts SET payload=? WHERE id=?", (json.dumps(payload), post["id"]))
    prepare(store, at + timedelta(minutes=15))
    for post in store.posts():
        if post["kind"] in ("weekly", "monthly"):
            assert len(post["slides"]) == 2
            assert "illustration_keys" not in post
            assert AI_NOTICE not in post["caption"]

