"""Official Meta Graph API adapter. No real publication in the scheduled workflow.

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
from .store import Store


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


def publish_one(store: Store, at: datetime, site_url: str, assets: dict[str, dict], story: bool = False, adapter=None, checkpoint=None) -> dict:
    api = adapter or Instagram()
    if not api.enabled():
        return {"status": "disabled"}
    parsed = urlsplit(site_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("A public HTTPS media base URL is required")
    if story:
        prepare_story_jobs(store, assets)
    prepared = sorted((p for p in store.posts() if p["status"] == "prepared" and parse_date(p["due_at"]) <= at and (p.get("publish_format") == "story") == story), key=lambda p: p["due_at"])
    recent = store.rows("SELECT payload FROM posts WHERE status IN ('publishing','published','uncertain')")
    import json
    if any(at - parse_date(json.loads(row["payload"])["published_at"]) < timedelta(minutes=45) for row in recent):
        return {"status": "rate_limited"}
    if not prepared:
        return {"status": "empty"}
    post = prepared[0]
    media = ([post["story_asset"]] if story else assets.get(post["id"], {}).get("feed", []))
    if not media:
        return {"status": "media_missing"}
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
    except (requests.RequestException, RuntimeError, KeyError, ValueError):
        with store.db:
            store.db.execute("UPDATE posts SET status='uncertain' WHERE id=?", (post["id"],))
        if checkpoint:
            checkpoint()
        return {"status": "uncertain", "post_id": post["id"]}


def prepare_story_jobs(store: Store, assets: dict[str, dict]):
    """Series frames are independently persisted; each dispatch sends one frame."""
    import json
    parents = [p for p in store.posts() if not p.get("publish_format") and p["status"] in ("prepared", "published")]
    valid_parents = {p["id"] for p in parents}
    with store.db:
        for child in store.posts():
            if child.get("publish_format") == "story" and child["status"] == "prepared" and child.get("parent_post_id") not in valid_parents:
                store.db.execute("UPDATE posts SET status='superseded' WHERE id=?", (child["id"],))
    for parent in parents:
        for index, path in enumerate(assets.get(parent["id"], {}).get("story", [])):
            child = {**parent, "id": digest(parent["id"] + f":story:{index}"), "publish_format": "story",
                     "parent_post_id": parent["id"], "story_asset": path, "story_index": index,
                     "title": parent["title"] + f" · Story {index+1}"}
            child.pop("published_at", None)
            store.queue(child)
            with store.db:
                store.db.execute("UPDATE posts SET payload=? WHERE id=? AND status='prepared'", (json.dumps(child, ensure_ascii=False), child["id"]))
