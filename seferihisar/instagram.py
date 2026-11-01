"""Official Meta Graph API adapter with durable publication claims.

    Explicit publishing requires all three controls, public JPEG URLs and a test
    authorization. In-flight/uncertain publish attempts never auto-retry.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit

import requests

from .domain import digest, parse_date
from .media_caption import generated_image_caption
from .store import Store
from .publication_policy import (NEWS_DAILY_LIMIT, OUTAGE_STORY_HOURS, daily_limit_reason, duplicate_reason, post_reason,
                                 day_claims, dispatch_window, evening_post, evening_window, outage_story_parents, story_only)


def delivery_error(exc: Exception) -> str:
    """A short code for the panel; never a response body, URL or token."""
    if isinstance(exc, requests.Timeout):
        return 'timeout'
    if isinstance(exc, requests.RequestException):
        return 'connection'
    if match := re.search(r'\(HTTP (\d{3})\)', str(exc)):
        return 'http_' + match[1]
    return 'media_processing' if str(exc).startswith('Meta media') else 'unverified_response'


class Instagram:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.account = os.getenv("INSTAGRAM_USER_ID", "")
        self.version = os.getenv("META_GRAPH_VERSION", "v25.0")
        if not re.fullmatch(r"v\d+\.0", self.version):
            raise ValueError("Invalid Graph API version")
        self.base = f"https://graph.facebook.com/{self.version}"

    def enabled(self) -> bool:
        return (os.getenv("INSTAGRAM_PUBLISH_ENABLED") == "true" and
                os.getenv("META_TESTS_COMPLETED") == "true" and
                os.getenv("INSTAGRAM_AUTH_MODE") == "facebook_login" and
                bool(self.token) and bool(re.fullmatch(r"\d+", self.account)))

    def call(self, path: str, method: str = "POST", **params) -> dict:
        response = self.session.request(method, f"{self.base}/{path}", headers={"Authorization": f"Bearer {self.token}"},
                                        params=params if method == "GET" else None,
                                        data=params if method != "GET" else None, timeout=(8, 30))
        # Do not propagate a response body, request URL, token or raw API error to logs.
        if not response.ok:
            raise RuntimeError(f"Meta API request failed (HTTP {response.status_code})")
        return response.json()

    def wait(self, container: str):
        for _ in range(10):
            state = self.call(container, "GET", fields="status_code").get("status_code")
            if state in ("FINISHED", "PUBLISHED"):
                return
            if state in ("ERROR", "EXPIRED"):
                raise RuntimeError("Meta media processing failed")
            time.sleep(2)
        raise RuntimeError("Meta media processing timed out")

    def container(self, images: list[str], caption: str, story: bool) -> str:
        if story:
            value = self.call(f"{self.account}/media", image_url=images[0], media_type="STORIES")["id"]
        elif len(images) == 1:
            value = self.call(f"{self.account}/media", image_url=images[0], caption=caption)["id"]
        else:
            children = []
            for image in images[:10]:
                child = self.call(f"{self.account}/media", image_url=image, is_carousel_item="true")["id"]
                self.wait(child)
                children.append(child)
            value = self.call(f"{self.account}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
        return value


def publish_one(store: Store, at: datetime, site_url: str, assets: dict[str, dict], story: bool = False, adapter=None, checkpoint=None, *, target_id: str | None = None, paired_story: bool = False, exclude_event_ids: set[str] | None = None, editorial: bool = False, require_visual_review: bool = False, requested: bool = False, evening_only: bool = False) -> dict:
    api = adapter or Instagram()
    if not api.enabled():
        return {"status": "disabled"}
    # An explicit manual publish must enforce the same source freshness rule.
    from .schedule import prepare
    prepare(store, at, refresh_digests=False)
    parsed = urlsplit(site_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("A public HTTPS media base URL is required")
    if story:
        prepare_story_jobs(store, assets)
        prepare(store, at, refresh_digests=False)  # Newly created frames also need fresh source evidence.
    prepared = sorted((p for p in store.posts() if p["status"] == "prepared" and
                       (parse_date(p["due_at"]) <= at or (requested and target_id == p['id'] and (not story or paired_story)))
                       and (p.get("publish_format") == "story") == story), key=lambda p: p["due_at"])
    if not story:
        prepared = [p for p in prepared if not story_only(p)]
    # Automatic announcements/reminders must not consume the daily feed slots
    # for the same event. Explicit corrections and cancellation notices remain eligible.
    if exclude_event_ids and not story:
        prepared = [p for p in prepared if p.get('item_id') not in exclude_event_ids
                    or p['kind'] not in ('announcement', 'reminder_3d', 'reminder_day')]
    if target_id:
        prepared = [p for p in prepared if p['id'] == target_id]
    if evening_only and not story:
        prepared = [p for p in prepared if evening_post(store, p, at, bonus=False)]
    if len(day_claims(store, at, story=story)) >= NEWS_DAILY_LIMIT:
        prepared = [p for p in prepared if daily_limit_reason(store, at, p, story=story) is None]
        if not prepared:
            return {'status': 'daily_limit'}
    if not story and (require_visual_review or isinstance(api, Instagram)):
        from .visual_policy import image_reason
        eligible_before_visual = bool(prepared)
        prepared = [p for p in prepared if image_reason(p) is None]
        if eligible_before_visual and not prepared:
            return {'status': 'awaiting_content_visual'}
    if editorial and not story:
        from .selection import EDITIONS, prioritize
        prepared = prioritize(store, prepared, at)
        # An edition leads the queue, so it must not hold the slot when it
        # cannot go out, and one a day leaves the other slots for news.
        taken = any(p['kind'] in EDITIONS for p in day_claims(store, at))
        prepared = [p for p in prepared if p['kind'] not in EDITIONS
                    or not taken and edition_ready(store, p, site_url, assets, api, require_visual_review)]
    post = prepared[0] if prepared else None
    if post:
        if reason := daily_limit_reason(store, at, post, story=story):
            return {'status': reason}
        if reason := post_reason(store, post, at) or duplicate_reason(store, post):
            return {'status': reason}
    recent = store.rows("SELECT payload FROM posts WHERE status IN ('publishing','published','uncertain')")
    import json
    recent_posts = [json.loads(row['payload']) for row in recent]
    # Only the first story card accompanying this already-published feed may
    # share its publication window. Other content retains the 45-minute limit.
    parent = next((p for p in store.posts() if post and p['id'] == post.get('parent_post_id') and p['status'] == 'published'), None)
    allowed_parent = parent['id'] if story and paired_story and post and post.get('story_index') == 0 and parent else None
    # A power-cut story waits for news, but like the weather it never delays news.
    if not (post and story_only(post)):
        recent_posts = [p for p in recent_posts if not (p.get('publish_format') and story_only(p))]
    if any(at - parse_date(p['published_at']) < timedelta(minutes=45) and p['id'] != allowed_parent for p in recent_posts):
        return {"status": "rate_limited"}
    if not prepared:
        return {"status": "empty"}
    media = ([post["story_asset"]] if story else assets.get(post["id"], {}).get("feed", []))
    if not media:
        return {"status": "media_missing"}
    if require_visual_review or isinstance(api, Instagram):
        from .visual_gate import deployed
        if reason := deployed(store, post, site_url, media, session=api.session, story=story):
            return {'status':reason}
    urls = [urljoin(site_url.rstrip("/") + "/", path) for path in media]
    # Verify media is deployed before container creation. No image upload API is used.
    for url in urls:
        response = api.session.head(url, timeout=15, allow_redirects=False)
        if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("image/jpeg"):
            return {"status": "media_not_deployed"}
    post["published_at"] = at.isoformat()
    with store.db:
        changed = store.db.execute("UPDATE posts SET status='publishing',payload=? WHERE id=? AND status='prepared'", (json.dumps(post, ensure_ascii=False), post["id"]))
    if changed.rowcount != 1:
        return {"status": "already_claimed"}
    # Ephemeral runners must remotely persist the claim BEFORE contacting Meta.
    # If the runner then dies, the next run sees 'publishing' and cannot resend.
    if checkpoint:
        checkpoint()
    try:
        container = api.container(urls, post["caption"], story)
        with store.db:
            store.db.execute("UPDATE posts SET container_id=? WHERE id=?", (container, post["id"]))
        if checkpoint:
            checkpoint()
        api.wait(container)
        # Crash/timeout after this POST might mean success. Never resend automatically.
        result = api.call(f"{api.account}/media_publish", creation_id=container)
        with store.db:
            store.db.execute("UPDATE posts SET status='published',media_id=? WHERE id=?", (result["id"], post["id"]))
        if checkpoint:
            checkpoint()
        return {"status": "published", "post_id": post["id"]}
    except (requests.RequestException, RuntimeError, KeyError, ValueError) as exc:
        post["delivery_error"] = delivery_error(exc)
        with store.db:
            store.db.execute("UPDATE posts SET status='uncertain',payload=? WHERE id=?", (json.dumps(post, ensure_ascii=False), post["id"]))
        if checkpoint:
            checkpoint()
        return {"status": "uncertain", "post_id": post["id"]}


def edition_ready(store, post, site_url, assets, api, require_visual_review) -> bool:
    media = assets.get(post['id'], {}).get('feed', [])
    if not media or not (require_visual_review or isinstance(api, Instagram)):
        return bool(media)
    from .visual_gate import deployed
    return deployed(store, post, site_url, media, session=api.session) is None


def publish_requested(store: Store, at: datetime, site_url: str, assets: dict[str, dict], target_id: str,
                      adapter=None, checkpoint=None, *, require_visual_review=False) -> dict:
    """One explicitly requested parent and first story, within the daily budget.

    May precede its scheduled window; never chooses another item, bypasses
    freshness/repeat/media checks, or replays an uncertain publication.
    """
    from .domain import TZ
    from .schedule import prepare
    if not isinstance(target_id, str) or not re.fullmatch(r'[a-f0-9]{24}', target_id):
        raise ValueError('Invalid requested post identity')
    api = adapter or Instagram()
    if not api.enabled():
        return {'status': 'disabled'}
    at = at.astimezone(TZ)
    prepare(store, at, refresh_digests=False)
    parent = next((p for p in store.posts() if p['id'] == target_id and not p.get('publish_format')), None)
    if not parent:
        return {'status': 'empty'}
    if parent['status'] in ('publishing', 'uncertain'):
        return {'status': 'awaiting_resolution'}
    if parent['status'] == 'published':
        if not at - timedelta(hours=1) <= parse_date(parent['published_at']) <= at:
            return {'status': 'already_published'}
        feed = {'status': 'already_published'}
    else:
        if parent['status'] != 'prepared':
            return {'status': 'blocked_source'}
        today = [p for p in store.posts() if not p.get('publish_format') and
                 p['status'] in ('published', 'publishing', 'uncertain') and p.get('published_at') and
                 parse_date(p['published_at']).astimezone(TZ).date() == at.date()]
        if daily_limit_reason(store, at, parent):
            return {'status': 'daily_limit'}
        feed = publish_one(store, at, site_url, assets, adapter=api, checkpoint=checkpoint,
                           target_id=target_id, requested=True, require_visual_review=require_visual_review)
        if feed['status'] != 'published':
            return {'status': feed['status']}
    child_id = digest(target_id + ':story:0')
    child = next((p for p in store.posts() if p['id'] == child_id), None)
    if child and child['status'] in ('published', 'publishing', 'uncertain'):
        return {'status': 'complete' if child['status'] == 'published' else 'awaiting_resolution',
                'feed': feed['status'], 'story': child['status']}
    story = publish_one(store, at, site_url, assets, story=True, adapter=api, checkpoint=checkpoint,
                        target_id=child_id, paired_story=True, requested=True, require_visual_review=require_visual_review)
    return {'status': 'complete' if story['status'] == 'published' else 'story_pending',
            'feed': feed['status'], 'story': story['status']}


def publish_automatic(store: Store, at: datetime, site_url: str, assets: dict[str, dict], adapter=None, checkpoint=None, *, require_visual_review: bool = False) -> dict:
    """Three regular feeds, with one bounded fresh-evening-news pair exception.

    A completed/uncertain claim consumes its slot and daily budget, including
    across runner restarts. Delays beyond one hour never dump the old queue.
    """
    from .domain import TZ
    from .schedule import SLOTS, prepare
    api = adapter or Instagram()
    if not api.enabled():
        return {'status':'disabled'}
    at = at.astimezone(TZ)
    window = dispatch_window(at, SLOTS)
    if window is None:
        return {'status':'outside_window'}
    slot, end, evening_only = window
    prepare(store, at, refresh_digests=False)
    claims = [p for p in store.posts() if not p.get('publish_format') and p['status'] in ('published','publishing','uncertain') and p.get('published_at')]
    today = [p for p in claims if parse_date(p['published_at']).astimezone(TZ).date() == at.date()]
    in_slot = [p for p in claims if slot <= parse_date(p['published_at']).astimezone(TZ) < end]
    parent = None
    if in_slot:
        parent = sorted(in_slot, key=lambda p:p['published_at'])[-1]
        if parent['status'] != 'published':
            return {'status':'awaiting_resolution'}
        child = next((p for p in store.posts() if p['id'] == digest(parent['id'] + ':story:0')), None)
        # A complete third pair must not permanently occupy the last evening
        # window and hide a later fresh fourth. Cooldown is still checked below.
        if (len(today) == NEWS_DAILY_LIMIT and evening_window(at)
                and child and child['status'] == 'published'):
            parent = None
    if parent is None:
        covered = {p['item_id'] for p in today if p.get('item_id')}
        feed = publish_one(store, at, site_url, assets, adapter=api, checkpoint=checkpoint, exclude_event_ids=covered,
                           editorial=True, require_visual_review=require_visual_review, evening_only=evening_only)
        if feed['status'] != 'published':
            return {'status':feed['status']}
        parent = next(p for p in store.posts() if p['id'] == feed['post_id'])
    else:
        feed = {'status':'already_published','post_id':parent['id']}
    child_id = digest(parent['id'] + ':story:0')
    child = next((p for p in store.posts() if p['id'] == child_id), None)
    if child and child['status'] in ('published','publishing','uncertain'):
        return {'status':'complete' if child['status']=='published' else 'awaiting_resolution', 'feed':feed['status'], 'story':child['status']}
    story_result = publish_one(store, at, site_url, assets, story=True, adapter=api, checkpoint=checkpoint, target_id=child_id, paired_story=True, require_visual_review=require_visual_review)
    return {'status':'complete' if story_result['status']=='published' else 'story_pending', 'feed':feed['status'], 'story':story_result['status']}


def publish_outage_story(store: Store, at: datetime, site_url: str, assets: dict[str, dict], adapter=None, checkpoint=None, *, require_visual_review: bool = False) -> dict:
    """At most one power-cut story per run, beside the daily news pairs."""
    from .domain import TZ
    from .schedule import prepare
    api = adapter or Instagram()
    if not api.enabled():
        return {'status':'disabled'}
    at = at.astimezone(TZ)
    if not OUTAGE_STORY_HOURS[0] <= at.time().replace(tzinfo=None) < OUTAGE_STORY_HOURS[1]:
        return {'status':'outside_window'}
    prepare(store, at, refresh_digests=False)
    prepare_story_jobs(store, assets)
    prepare(store, at, refresh_digests=False)  # Newly created frames also need fresh source evidence.
    parents = outage_story_parents(store, at)
    if require_visual_review or isinstance(api, Instagram):
        from .visual_policy import image_reason
        parents = [p for p in parents if image_reason(p) is None]
    if not parents:
        return {'status':'empty'}
    return publish_one(store, at, site_url, assets, story=True, adapter=api, checkpoint=checkpoint,
                       target_id=digest(parents[0]['id'] + ':story:0'), require_visual_review=require_visual_review)


def prepare_story_jobs(store: Store, assets: dict[str, dict]):
    """Persist only the first matching news card; never build extra story frames."""
    import json
    parents = [p for p in store.posts() if not p.get("publish_format") and p["status"] in ("prepared", "published")]
    # A blocked parent can come back, so only a parent that is gone drops its story.
    valid_parents = {p["id"] for p in store.posts() if not p.get("publish_format") and p["status"] in ("prepared", "published", "blocked_source")}
    with store.db:
        for child in store.posts():
            if child.get("publish_format") == "story" and child["status"] in ("prepared", "blocked_source") and child.get("parent_post_id") not in valid_parents:
                store.db.execute("UPDATE posts SET status='superseded' WHERE id=?", (child["id"],))
    for parent in parents:
        for index, path in enumerate(assets.get(parent["id"], {}).get("story", [])[:1]):
            child = {**parent, "id": digest(parent["id"] + f":story:{index}"), "publish_format": "story",
                     "parent_post_id": parent["id"], "story_asset": path, "story_index": index,
                     "title": parent["title"] + f" · Story {index+1}"}
            # A future story can inherit an already-published feed caption.
            # Clean its own unclaimed copy without rewriting the parent claim.
            child['caption'] = generated_image_caption(child['caption'], bool(child.get('illustration_keys')))
            child.pop("published_at", None)
            store.queue(child)
            with store.db:
                # A story id never changes, so a story dropped while its parent
                # was blocked can only return here, before the parent is claimed.
                if parent["status"] == "prepared":
                    store.db.execute("UPDATE posts SET status='prepared' WHERE id=? AND status='superseded'", (child["id"],))
                store.db.execute("UPDATE posts SET payload=? WHERE id=? AND status='prepared'", (json.dumps(child, ensure_ascii=False), child["id"]))
