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
    parser.add_argument("--instagram-manifest", type=Path)
    parser.add_argument("--site-url", default="")
    parser.add_argument("--story", action="store_true")
    parser.add_argument("--automatic", action="store_true", help="Two daily feed/story pairs in configured Turkish time windows")
    parser.add_argument("--post-id", help="Explicitly requested parent; keep daily budget and all publication checks")
    args = parser.parse_args()
    if args.post_id:
        import re
        if (args.command != 'publish' or args.automatic or args.story
                or not re.fullmatch(r'[a-f0-9]{24}', args.post_id)):
            parser.error('--post-id requires publish and one valid parent identity, without other format flags')
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
        result = run(args.db, args.public, args.sources, at, args.fixture, args.instagram_manifest)
    else:
        from .instagram import publish_one, publish_automatic, publish_requested
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
            from .owner_requests import publish as publish_owner_request, pending as pending_owner_request
            owner_request = pending_owner_request(store, at) if args.automatic and not args.post_id else None
            owner_result = publish_owner_request(store, at, args.site_url, assets, checkpoint) if args.automatic and not args.post_id else None
            result = owner_result if owner_result is not None else (publish_requested(store, at, args.site_url, assets, args.post_id, checkpoint=checkpoint, require_visual_review=True) if args.post_id else
                      publish_automatic(store, at, args.site_url, assets, checkpoint=checkpoint, require_visual_review=True) if args.automatic
                      else publish_one(store, at, args.site_url, assets, args.story, checkpoint=checkpoint, require_visual_review=True))
            if args.automatic or args.post_id:
                from .facebook import publish_recent
                result['facebook'] = publish_recent(store, at, args.site_url, assets, checkpoint=checkpoint, require_visual_review=True,
                                                    target_id=args.post_id or (owner_request['post_id'] if owner_result is not None and owner_request else None))
            if args.automatic and not args.post_id and owner_result is None:
                from .instagram import publish_outage_story
                from .facebook import publish_outage_story as mirror_outage_story
                result['outage_story'] = publish_outage_story(store, at, args.site_url, assets, checkpoint=checkpoint, require_visual_review=True)['status']
                result['outage_facebook'] = mirror_outage_story(store, at, args.site_url, checkpoint=checkpoint, require_visual_review=True)['status']
            from .operations import record_check, write_job_summary, failed
            observation = record_check(store, result, at, 'automatic' if args.automatic else 'story' if args.story else 'feed')
            write_job_summary(observation)
        finally:
            store.close()
    # Never print captions, source bodies or authentication details in Actions logs.
    print(json.dumps({k: v for k, v in result.items() if k != "assets"}, ensure_ascii=False))
    if args.command == 'publish' and failed(observation):
        raise SystemExit(1)  # The workflow still persists state in its always() step.


if __name__ == "__main__":
    main()
