from __future__ import annotations

import argparse
import json
from pathlib import Path

from .domain import now, parse_date
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Seferihisar Official — güvenli haber ve etkinlik otomasyonu")
    parser.add_argument("command", choices=("run", "demo", "publish"))
    parser.add_argument("--db", type=Path, default=Path("state/platform.sqlite"))
    parser.add_argument("--public", type=Path, default=Path("dist"))
    parser.add_argument("--sources", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--at", help="ISO8601 time, Europe/Istanbul if no offset")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--site-url", default="")
    parser.add_argument("--story", action="store_true")
    args = parser.parse_args()
    at = parse_date(args.at) if args.at else now()
    if not at:
        parser.error("Invalid --at timestamp")
    if args.command == "demo":
        # Isolated demo state must never contaminate the production branch.
        if args.db == Path("state/platform.sqlite"):
            args.db = Path("work/demo.sqlite")
        fixture = args.fixture or Path("tests/fixtures/items.json")
        at = parse_date("2026-10-10T10:00:00+03:00") if not args.at else at
        result = run(args.db, args.public, args.sources, at, fixture)
    elif args.command == "run":
        result = run(args.db, args.public, args.sources, at, args.fixture)
    else:
        from .instagram import publish_one
        from .store import Store
        import os
        store = Store(args.db)
        try:
            snapshot = json.loads((args.public / "data.json").read_text())
            if snapshot.get("demo"):
                parser.error("Demo content cannot be published")
            assets = {p["id"]: p["assets"] for p in snapshot["posts"]}
            checkpoint = None
            if os.getenv("STATE_GIT_CHECKPOINT") == "true":
                from .state_git import persist
                checkpoint = lambda: persist(args.db)
            result = publish_one(store, at, args.site_url, assets, args.story, checkpoint=checkpoint)
        finally:
            store.close()
    # Never print captions, source bodies or authentication details in Actions logs.
    print(json.dumps({k: v for k, v in result.items() if k != "assets"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
