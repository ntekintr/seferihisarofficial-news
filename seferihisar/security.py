"""Public-data boundary. Standard library only, including for the state writer."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ITEM_FIELDS = {"kind", "title", "description", "url", "source_id", "source_name", "category", "sources", "published_at",
               "identity", "start", "end", "time_known", "location", "organizer", "free", "price", "currency", "ticket_url", "status", "previous_start"}
PUBLIC_ITEM_FIELDS = ITEM_FIELDS - {"identity"}
POST_FIELDS = {"id", "item_id", "revision", "kind", "due_at", "title", "caption", "category", "source_urls", "slides", "created_at", "formats",
               "publish_format", "parent_post_id", "story_asset", "story_index", "published_at", "status", "container_id", "media_id"}
SECRET_PATTERN = re.compile(
    r"AIza[\w-]{35}|(?:gh[pousr]_[A-Za-z0-9]{20,})|github_pat_[A-Za-z0-9_]{20,}|EAA[A-Za-z0-9]{50,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:access[_-]?token|api[_-]?key|password|secret|authorization)\s*[=:]\s*[\"']?[^\s\"'&,;<>]{8,}", re.I)
SECRET_VARIABLES = ("GEMINI_API_KEY", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "GITHUB_TOKEN", "GH_TOKEN", "STATE_WRITE_TOKEN")


def contains_secret(value) -> bool:
    serialized = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    # Source URLs and text can percent-encode credential names or values.
    decoded = unquote(unquote(serialized))
    if SECRET_PATTERN.search(decoded):
        return True
    return any(len(secret := os.getenv(name, "")) >= 8 and secret in decoded for name in SECRET_VARIABLES)


def public_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            return False
        if contains_secret(url):
            return False
        return not any(k.casefold() == "key" or any(word in k.casefold() for word in ("token", "api_key", "auth", "signature", "password", "secret", "credential")) for k, _ in parse_qsl(parts.query))
    except (ValueError, TypeError):
        return False


def assert_no_secrets(value):
    if contains_secret(value):
        # A controlled exception must not reproduce the offending payload.
        raise ValueError("Public-data validation rejected credential-like content")


def validate_state(path: Path):
    """Refuse to upload/commit a state file containing unapproved payload fields."""
    db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables <= {"items", "posts", "withheld", "runs", "candidates", "annotations"}:
            raise ValueError("Unexpected state tables")
        for table in sorted(tables):
            for row in db.execute(f'SELECT * FROM "{table}"'):
                assert_no_secrets(row)
            if table in ("items", "posts"):
                allowed = ITEM_FIELDS if table == "items" else POST_FIELDS
                for row in db.execute(f'SELECT payload FROM "{table}"'):
                    if not set(json.loads(row[0])) <= allowed:
                        raise ValueError("Unexpected state payload fields")
    finally:
        db.close()


def validate_public(path: Path):
    allowed_files = {"index.html", "style.css", "app.js", "data.json", "events.ics", ".nojekyll"}
    for entry in path.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Public output must not contain symlinks")
        if entry.is_file():
            relative = entry.relative_to(path)
            if len(relative.parts) == 1 and relative.name in allowed_files:
                assert_no_secrets(entry.read_text(encoding="utf-8"))
            elif len(relative.parts) == 3 and relative.parts[0] == "media" and re.fullmatch(r"[a-f0-9]{24}", relative.parts[1]) and re.fullmatch(r"(?:feed|story)-\d+\.jpg", relative.name):
                continue
            else:
                raise ValueError("Unexpected file in public output")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("state", "public"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        (validate_state if args.kind == "state" else validate_public)(args.path)
    except (ValueError, sqlite3.Error, OSError):
        raise SystemExit("Public-data safety check failed; upload blocked.") from None
