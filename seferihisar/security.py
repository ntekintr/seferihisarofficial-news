"""Public-data boundary. Standard library only, including for the state writer."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ITEM_FIELDS = {"kind", "title", "description", "url", "source_id", "source_name", "category", "sources", "published_at",
               "identity", "start", "end", "time_known", "location", "organizer", "free", "price", "currency", "ticket_url", "status", "previous_start", "valid_until"}
PUBLIC_ITEM_FIELDS = ITEM_FIELDS - {"identity"}
POST_FIELDS = {"id", "item_id", "revision", "kind", "due_at", "title", "caption", "category", "source_urls", "slides", "created_at", "formats",
               "publish_format", "parent_post_id", "story_asset", "story_index", "published_at", "status", "container_id", "media_id", "illustration_keys", "source_photo_keys", "visual_review", "card_layout", "brand_version"}
SECRET_PATTERN = re.compile(
    r"AIza[\w-]{35}|(?:gh[pousr]_[A-Za-z0-9]{20,})|github_pat_[A-Za-z0-9_]{20,}|EAA[A-Za-z0-9]{50,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"(?:access[_-]?token|api[_-]?key|password|secret|authorization)\s*[=:]\s*[\"']?[^\s\"'&,;<>]{8,}", re.I)
SECRET_VARIABLES = ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "INSTAGRAM_ACCESS_TOKEN", "FACEBOOK_PAGE_ACCESS_TOKEN", "INSTAGRAM_USER_ID", "IG_SOURCE_ACCESS_TOKEN", "IG_SOURCE_USER_ID", "GITHUB_TOKEN", "GH_TOKEN", "STATE_WRITE_TOKEN")


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


def valid_visual_review(value):
    """Standard-library boundary; no model/Pillow dependency in state writer."""
    if not isinstance(value, dict) or set(value) != {'version','content','edition','images','references','assets'}:
        return False
    if value['version'] not in ('content-visual-v1','content-visual-v2','content-visual-v3') or any(not isinstance(value[k], str) or not re.fullmatch(r'[a-f0-9]{24}', value[k]) for k in ('content','edition')):
        return False
    if not isinstance(value['images'], dict) or len(value['images']) > 10 or not isinstance(value['assets'], dict) or len(value['assets']) > 20:
        return False
    if not isinstance(value['references'], dict) or len(value['references']) > 10:
        return False
    for key, revision in value['references'].items():
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{24}', key) or type(revision) is not int or not 1 <= revision <= 1000000:
            return False
    for key, sha in value['images'].items():
        if not isinstance(key, str) or not re.fullmatch(r'[0-9]', key) or not isinstance(sha, str) or not re.fullmatch(r'(?:[a-f0-9]{2}:){31}[a-f0-9]{2}', sha):
            return False
    for path, sha in value['assets'].items():
        if not isinstance(path, str) or not re.fullmatch(r'media/'+value['edition']+r'/(?:feed|story)-(?:[1-9]|10)\.jpg', path) or not isinstance(sha, str) or not re.fullmatch(r'(?:[a-f0-9]{2}:){31}[a-f0-9]{2}', sha):
            return False
    return True


def validate_state(path: Path):
    """Refuse to upload/commit a state file containing unapproved payload fields."""
    db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables <= {"items", "posts", "withheld", "runs", "candidates", "annotations", "illustrations", "illustration_days", "source_photos", "source_photo_retries", "source_health", "facebook_deliveries", "publication_checks", "weather_stories", "learning_profile", "source_checks", "delivery_audits", "learning_samples", "pharmacy_stories"}:
            raise ValueError("Unexpected state tables")
        for table in sorted(tables):
            if table == 'pharmacy_stories':
                from .pharmacy_data import validate_record
                if [r[1] for r in db.execute('PRAGMA table_info(pharmacy_stories)')] != ['day','bulletin','status','checked_at','last_result','container_ids','media_ids','published_at']:
                    raise ValueError('Unexpected pharmacy story fields')
                for row in db.execute('SELECT * FROM pharmacy_stories'):
                    validate_record(row)
                continue
            if table == 'learning_samples':
                from .learning_cohorts import MAX_ROWS, validate_row
                if [r[1] for r in db.execute('PRAGMA table_info(learning_samples)')] != ['id', 'post_id', 'category', 'cohort', 'age_hours', 'score_band', 'reach_gate', 'checked_at']:
                    raise ValueError('Unexpected coarse measurement fields')
                if db.execute('SELECT COUNT(*) FROM learning_samples').fetchone()[0] > MAX_ROWS:
                    raise ValueError('Coarse measurement limit exceeded')
                for row in db.execute('SELECT * FROM learning_samples'):
                    assert_no_secrets(row)
                    validate_row(row)
                continue
            if table == 'delivery_audits':
                from .delivery_audit import MAX_ROWS, validate_row
                if [r[1] for r in db.execute('PRAGMA table_info(delivery_audits)')] != ['id', 'channel', 'format', 'checked_at', 'status']:
                    raise ValueError('Unexpected delivery observation fields')
                if db.execute('SELECT COUNT(*) FROM delivery_audits').fetchone()[0] > MAX_ROWS:
                    raise ValueError('Delivery observation limit exceeded')
                for row in db.execute('SELECT * FROM delivery_audits'):
                    assert_no_secrets(row)
                    validate_row(row)
                continue
            if table == 'learning_profile':
                from .learning import validate_profile
                if [r[1] for r in db.execute('PRAGMA table_info(learning_profile)')] != ['id', 'payload']:
                    raise ValueError('Unexpected learning fields')
                if db.execute('SELECT COUNT(*) FROM learning_profile').fetchone()[0] > 1:
                    raise ValueError('Unexpected learning history')
                for key, payload in db.execute('SELECT * FROM learning_profile'):
                    assert_no_secrets(payload)
                    if key != 'instagram':
                        raise ValueError('Invalid learning identity')
                    validate_profile(json.loads(payload))
                continue
            if table == 'source_checks':
                from .source_discovery import MAX_CANDIDATES, validate_check
                if [r[1] for r in db.execute('PRAGMA table_info(source_checks)')] != ['candidate_id', 'checked_at', 'result', 'successes', 'source']:
                    raise ValueError('Unexpected source check fields')
                if db.execute('SELECT COUNT(*) FROM source_checks').fetchone()[0] > MAX_CANDIDATES:
                    raise ValueError('Source check limit exceeded')
                for row in db.execute('SELECT * FROM source_checks'):
                    assert_no_secrets(row)
                    validate_check(row)
                continue
            if table == 'source_photo_retries':
                from .source_photo_retry import COLUMNS, MAX_ROWS, validate_row
                if [r[1] for r in db.execute('PRAGMA table_info(source_photo_retries)')] != COLUMNS:
                    raise ValueError('Unexpected source photo retry fields')
                if db.execute('SELECT COUNT(*) FROM source_photo_retries').fetchone()[0] > MAX_ROWS:
                    raise ValueError('Source photo retry limit exceeded')
                for row in db.execute('SELECT * FROM source_photo_retries'):
                    assert_no_secrets(row)
                    validate_row(row)
                continue
            if table=='source_photos':
                from .source_photo_data import validate_record,MAX_CACHE_BYTES,MAX_CACHED_IMAGES
                if [r[1] for r in db.execute('PRAGMA table_info(source_photos)')]!=['id','item_id','revision','payload','image']:
                    raise ValueError('Unexpected source photo fields')
                size,count=0,0
                for row in db.execute('SELECT * FROM source_photos'):
                    validate_record(*row)
                    size+=len(row[4]);count+=1
                if size>MAX_CACHE_BYTES or count>MAX_CACHED_IMAGES:
                    raise ValueError('Source photo cache exceeds limit')
                continue
            if table == 'weather_stories':
                from datetime import date, datetime
                from .weather_data import RESULTS, STATES, validate_forecast
                if [r[1] for r in db.execute('PRAGMA table_info(weather_stories)')] != ['day','forecast','status','checked_at','last_result','container_id','media_id','published_at']:
                    raise ValueError('Unexpected weather story fields')
                for row in db.execute('SELECT * FROM weather_stories'):
                    assert_no_secrets(row)
                    day, payload, status, checked, result, container, media, published = row
                    if date.fromisoformat(day).isoformat() != day or status not in STATES or result not in RESULTS or datetime.fromisoformat(checked).tzinfo is None:
                        raise ValueError('Invalid weather story')
                    if payload:
                        forecast = validate_forecast(json.loads(payload))
                        if forecast['date'] != day:
                            raise ValueError('Weather story date mismatch')
                    elif status != 'blocked':
                        raise ValueError('Missing forecast')
                    if any(v is not None and (not isinstance(v,str) or not re.fullmatch(r'\d{1,32}',v)) for v in (container,media)):
                        raise ValueError('Invalid weather media identity')
                    from .domain import TZ
                    if published and (datetime.fromisoformat(published).tzinfo is None or datetime.fromisoformat(published).astimezone(TZ).date().isoformat() != day):
                        raise ValueError('Invalid weather publication timestamp')
                    if (status in ('publishing','published','uncertain') and not published) or (status == 'published' and not media):
                        raise ValueError('Incomplete weather publication claim')
                continue
            if table == 'publication_checks':
                from datetime import datetime
                from .operations import validate_result
                if [r[1] for r in db.execute('PRAGMA table_info(publication_checks)')] != ['id', 'checked_at', 'mode', 'result']:
                    raise ValueError('Unexpected publication check fields')
                if db.execute('SELECT COUNT(*) FROM publication_checks').fetchone()[0] > 100:
                    raise ValueError('Publication check history exceeds limit')
                for key, stamp, mode, result in db.execute('SELECT * FROM publication_checks'):
                    assert_no_secrets((stamp, mode, result))
                    if type(key) is not int or key < 1 or mode not in ('automatic', 'feed', 'story') or datetime.fromisoformat(stamp).tzinfo is None:
                        raise ValueError('Invalid publication check')
                    validate_result(json.loads(result))
                continue
            if table == 'facebook_deliveries':
                from datetime import datetime
                columns = ['id', 'post_id', 'page_id', 'format', 'status', 'claimed_at', 'updated_at', 'photo_ids', 'media_id']
                if [r[1] for r in db.execute('PRAGMA table_info(facebook_deliveries)')] != columns:
                    raise ValueError('Unexpected Facebook delivery fields')
                for row in db.execute('SELECT * FROM facebook_deliveries'):
                    assert_no_secrets(row)
                    key, post, page, kind, status, claimed, updated, photos, media = row
                    if not all(re.fullmatch(r'[a-f0-9]{24}', v) for v in (key, post)) or not re.fullmatch(r'\d{1,32}', page):
                        raise ValueError('Invalid Facebook delivery identity')
                    if kind not in ('feed', 'story') or status not in ('publishing', 'published', 'uncertain'):
                        raise ValueError('Invalid Facebook delivery status')
                    ids = json.loads(photos)
                    if not isinstance(ids, list) or len(ids) > 10 or not all(isinstance(v, str) and re.fullmatch(r'\d{1,32}', v) for v in ids):
                        raise ValueError('Invalid Facebook photo identifiers')
                    if media is not None and not re.fullmatch(r'\d{1,32}(?:_\d{1,32})?', media):
                        raise ValueError('Invalid Facebook media identifier')
                    if status == 'published' and not media:
                        raise ValueError('Missing Facebook publication identifier')
                    if any(datetime.fromisoformat(v).tzinfo is None for v in (claimed, updated)):
                        raise ValueError('Invalid Facebook delivery timestamp')
                continue
            if table == 'source_health':
                from datetime import datetime
                if [r[1] for r in db.execute('PRAGMA table_info(source_health)')] != ['source_id', 'checked_at', 'status', 'parsed', 'accepted', 'error_count', 'latest_published_at']:
                    raise ValueError('Unexpected source health fields')
                for row in db.execute('SELECT * FROM source_health'):
                    sid, stamp, status, parsed, accepted, errors, latest = row
                    assert_no_secrets(row)
                    if not re.fullmatch(r'[a-z0-9-]{1,80}', sid) or status not in ('ok', 'empty', 'partial', 'failed'):
                        raise ValueError('Invalid source health status')
                    if any(type(v) is not int or not 0 <= v <= 10000 for v in (parsed, accepted, errors)) or accepted > parsed:
                        raise ValueError('Invalid source health counters')
                    if datetime.fromisoformat(stamp).tzinfo is None or (latest and datetime.fromisoformat(latest).tzinfo is None):
                        raise ValueError('Invalid source health timestamp')
                if db.execute('SELECT COUNT(*) FROM source_health').fetchone()[0] > 200:
                    raise ValueError('Source health exceeds limit')
                continue
            if table == 'illustrations':
                from .image_safety import MAX_CACHE_BYTES, MAX_CACHED_IMAGES, validate_jpeg
                columns = [r[1] for r in db.execute('PRAGMA table_info(illustrations)')]
                if columns != ['id', 'item_id', 'status', 'image', 'attempts', 'retry_at', 'updated_at']:
                    raise ValueError('Unexpected illustration fields')
                size, count = 0, 0
                for key, item_id, status, image, attempts, retry_at, updated_at in db.execute('SELECT * FROM illustrations'):
                    assert_no_secrets((key, item_id, status, attempts, retry_at, updated_at))
                    if not all(re.fullmatch(r'[a-f0-9]{24}', v) for v in (key, item_id)) or status not in ('ready', 'pending', 'failed') or type(attempts) is not int or not (0 if status == 'ready' else 1) <= attempts <= 2:
                        raise ValueError('Invalid illustration record')
                    from datetime import datetime
                    for stamp in (retry_at, updated_at):
                        if datetime.fromisoformat(stamp).tzinfo is None:
                            raise ValueError('Invalid illustration timestamp')
                    if status == 'ready':
                        validate_jpeg(image)
                        size += len(image)
                        count += 1
                    elif image is not None:
                        raise ValueError('Unexpected failed illustration bytes')
                if count > MAX_CACHED_IMAGES or size > MAX_CACHE_BYTES:
                    raise ValueError('Illustration cache exceeds limit')
                continue
            if table == 'illustration_days':
                if [r[1] for r in db.execute('PRAGMA table_info(illustration_days)')] != ['day', 'attempts']:
                    raise ValueError('Unexpected illustration counter fields')
                from datetime import date
                for day, attempts in db.execute('SELECT * FROM illustration_days'):
                    if date.fromisoformat(day).isoformat() != day or type(attempts) is not int or not 0 <= attempts <= 20:
                        raise ValueError('Invalid illustration counter')
                continue
            for row in db.execute(f'SELECT * FROM "{table}"'):
                assert_no_secrets(row)
            if table in ("items", "posts"):
                allowed = ITEM_FIELDS if table == "items" else POST_FIELDS
                for row in db.execute(f'SELECT payload FROM "{table}"'):
                    if not set(json.loads(row[0])) <= allowed:
                        raise ValueError("Unexpected state payload fields")
                    payload = json.loads(row[0])
                    if table == 'posts' and 'visual_review' in payload and not valid_visual_review(payload['visual_review']):
                        raise ValueError('Invalid visual review')
                    if table=='posts' and 'source_photo_keys' in payload:
                        from .source_photo_data import valid_bindings
                        if not valid_bindings(payload['source_photo_keys']):
                            raise ValueError('Invalid source photo bindings')
                    if table=='posts' and 'card_layout' in payload:
                        from .card_layout import SUPPORTED
                        if payload['card_layout'] not in SUPPORTED:
                            raise ValueError('Invalid card layout policy')
                    if table=='posts' and 'brand_version' in payload:
                        from .brand import logo_path
                        logo_path(payload['brand_version'])
    finally:
        db.close()


def validate_public(path: Path):
    from .brand import PUBLIC_ASSET, logo_path
    allowed_files = {"index.html", "style.css", "app.js", "data.json", "events.ics", ".nojekyll"}
    for entry in path.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Public output must not contain symlinks")
        if entry.is_file():
            relative = entry.relative_to(path)
            if relative.as_posix() == PUBLIC_ASSET:
                if entry.read_bytes() != logo_path().read_bytes():
                    raise ValueError('Unexpected public brand asset')
            elif len(relative.parts) == 1 and relative.name in allowed_files:
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
