from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .domain import digest, normalized


class Store:
    """State is public-safe even when the dedicated Git branch is public.

    Withheld records retain only a hash, reason and timestamp, never their payload.
    SQLite transactions and a serialized workflow protect updates and outbox history.
    """

    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS items (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, fingerprint TEXT NOT NULL,
              payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
              first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS withheld (
              id TEXT PRIMARY KEY, reason TEXT NOT NULL, seen_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS posts (
              id TEXT PRIMARY KEY, item_id TEXT, revision INTEGER NOT NULL,
              kind TEXT NOT NULL, due_at TEXT NOT NULL, status TEXT NOT NULL,
              payload TEXT NOT NULL, container_id TEXT, media_id TEXT);
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
              collected INTEGER NOT NULL DEFAULT 0, errors TEXT NOT NULL DEFAULT '[]');
            CREATE TABLE IF NOT EXISTS candidates (
              id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS annotations (
              item_id TEXT PRIMARY KEY, priority INTEGER NOT NULL, reviewed_at TEXT NOT NULL);
        """)
        self.db.commit()

    def rows(self, query: str, params=()) -> list[dict]:
        return [dict(row) for row in self.db.execute(query, params)]

    def items(self, kind: str | None = None) -> list[dict]:
        rows = self.rows("SELECT * FROM items" + (" WHERE kind=?" if kind else ""), (kind,) if kind else ())
        return [dict(json.loads(row["payload"]), id=row["id"], revision=row["revision"], first_seen=row["first_seen"], last_seen=row["last_seen"]) for row in rows]

    def withhold(self, key: str, reason: str, at: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO withheld VALUES (?, ?, ?)", (digest(key), reason, at))

    def upsert(self, item: dict, at: str) -> tuple[str, bool]:
        # Stable organizer/source URL or schema.org @id survives date/title changes.
        key = digest(item["kind"] + ":" + item.get("identity", item["url"]))
        old = self.rows("SELECT * FROM items WHERE id=?", (key,))
        if not old:
            # Conservative cross-source duplicate detection; dates separate recurring editions.
            fingerprint = digest(normalized(item["title"]) + ":" + (item.get("start") or "") + ":" + item["kind"])
            duplicate = self.rows("SELECT * FROM items WHERE fingerprint=?", (fingerprint,))
            if duplicate:
                row = duplicate[0]
                existing = json.loads(row["payload"])
                sources = existing.setdefault("sources", [existing["url"]])
                if item["url"] not in sources:
                    sources.append(item["url"])
                with self.db:
                    self.db.execute("UPDATE items SET payload=?,last_seen=? WHERE id=?", (json.dumps(existing, ensure_ascii=False), at, row["id"]))
                return row["id"], False
        else:
            fingerprint = old[0]["fingerprint"]
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True)
        previous = json.loads(old[0]["payload"]) if old else None
        # Provenance additions do not regenerate cards; factual edits do.
        factual = lambda x: {k: v for k, v in x.items() if k != "sources"}
        changed = not previous or factual(previous) != factual(item)
        revision = (old[0]["revision"] + int(changed)) if old else 1
        with self.db:
            self.db.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,last_seen=excluded.last_seen", (key, item["kind"], fingerprint, payload, revision, at, at))
            if changed and old:
                self.db.execute("UPDATE posts SET status='superseded' WHERE item_id=? AND status='prepared'", (key,))
        return key, changed

    def queue(self, post: dict) -> bool:
        with self.db:
            result = self.db.execute("INSERT OR IGNORE INTO posts(id,item_id,revision,kind,due_at,status,payload) VALUES(?,?,?,?,?,'prepared',?)", (post["id"], post.get("item_id"), post.get("revision", 1), post["kind"], post["due_at"], json.dumps(post, ensure_ascii=False)))
        return result.rowcount > 0

    def posts(self) -> list[dict]:
        return [dict(json.loads(row["payload"]), status=row["status"], container_id=row["container_id"], media_id=row["media_id"]) for row in self.rows("SELECT * FROM posts ORDER BY due_at DESC")]

    def close(self):
        self.db.close()
