"""Bounded, public-safe observations. These never retry or create publications."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .domain import TZ, parse_date
from .publication_policy import NEWS_DAILY_LIMIT, news_windows, evening_summary

STATUSES = frozenset(('complete', 'published', 'already_published', 'outside_window',
    'daily_limit', 'empty', 'disabled', 'rate_limited', 'media_missing',
    'media_not_deployed', 'already_claimed', 'awaiting_resolution', 'uncertain',
    'story_pending', 'blocked_source', 'account_mismatch', 'check_failed',
    'visual_review_missing', 'visual_review_stale', 'visual_review_unavailable',
    'editorial_review_required', 'editorial_copy_stale', 'event_metadata_stale',
    'duplicate_story', 'stale_parent', 'owner_excluded', 'awaiting_content_visual'))
RESULT_FIELDS = frozenset(('status', 'feed', 'story', 'facebook', 'outage_story', 'outage_facebook'))
FAILURES = frozenset(('media_missing', 'media_not_deployed', 'awaiting_resolution',
    'uncertain', 'account_mismatch', 'check_failed',
    'visual_review_missing', 'visual_review_stale', 'visual_review_unavailable',
    'editorial_review_required', 'editorial_copy_stale', 'event_metadata_stale'))


def safe_result(result):
    # Provider text, captions, URLs and identifiers have no place in this log.
    status = result.get('status')
    clean = {'status': status if isinstance(status, str) and status in STATUSES else 'check_failed'}
    for key in ('feed', 'story', 'outage_story', 'outage_facebook'):
        if key in result:
            clean[key] = result[key] if isinstance(result[key], str) and result[key] in STATUSES else 'check_failed'
    if isinstance(result.get('facebook'), dict):
        clean['facebook'] = {k: v for k, v in safe_result({k: v for k, v in result['facebook'].items() if k != 'facebook'}).items() if k != 'facebook'}
    return clean


def validate_result(result, nested=False):
    if not isinstance(result, dict) or not set(result) <= RESULT_FIELDS or not isinstance(result.get('status'), str) or result['status'] not in STATUSES:
        raise ValueError('Invalid publication check result')
    for key, value in result.items():
        if key == 'facebook':
            if nested:
                raise ValueError('Invalid publication check nesting')
            validate_result(value, True)
        elif not isinstance(value, str) or value not in STATUSES:
            raise ValueError('Invalid publication check status')


def failed(result):
    return (result['status'] == 'disabled'
            or any(result.get(k) in FAILURES for k in ('status', 'feed', 'story', 'outage_story', 'outage_facebook'))
            or any(result.get('facebook', {}).get(k) in FAILURES for k in ('status', 'feed', 'story')))


def record_check(store, result, at, mode):
    if mode not in ('automatic', 'feed', 'story') or at.tzinfo is None:
        raise ValueError('Invalid publication check')
    clean = safe_result(result)
    with store.db:
        store.db.execute('INSERT INTO publication_checks(checked_at,mode,result) VALUES(?,?,?)',
                         (at.isoformat(), mode, json.dumps(clean)))
        store.db.execute('DELETE FROM publication_checks WHERE id NOT IN (SELECT id FROM publication_checks ORDER BY id DESC LIMIT 100)')
    return clean


def never_sent(post):
    """An uncertain claim without a container never reached `media_publish`.

    `instagram.deliver` stores the container id right after Meta returns it
    and only then calls `media_publish`, so the exception came from container
    creation. The claim still holds its slot and is never resent.
    """
    return post.get('status') == 'uncertain' and not post.get('container_id')


def summary(store, at):
    from .schedule import SLOTS
    at = at.astimezone(TZ)
    posts = store.posts()
    parents = [p for p in posts if not p.get('publish_format')]
    def today(stamp):
        return bool(stamp) and parse_date(stamp).astimezone(TZ).date() == at.date()
    claims = [p for p in posts if p['status'] in ('published', 'publishing', 'uncertain')]
    deliveries = store.rows('SELECT format,status,claimed_at FROM facebook_deliveries')
    today_claims = [p for p in claims if today(p.get('published_at'))]
    checks = [{**r, 'result': json.loads(r['result'])} for r in store.rows('SELECT checked_at,mode,result FROM publication_checks ORDER BY id DESC LIMIT 10')]
    windows = [window for day in (0, 1) for window in news_windows(at.date() + timedelta(days=day), SLOTS)]
    window, window_end, _ = next(w for w in windows if at < w[1])
    utc_day = at.astimezone(timezone.utc).date()
    budget = store.rows('SELECT attempts FROM illustration_days WHERE day=?', (utc_day.isoformat(),))
    from .illustrations import DAILY_ATTEMPTS
    attempts = budget[0]['attempts'] if budget else 0
    from .quality import news_editorial_reason
    from .domain import digest
    reasons = ('editorial_headline_required','editorial_context_required','editorial_copy_required')
    editorial = dict.fromkeys(reasons,0)
    for item in store.items():
        stamp = parse_date(item.get('published_at'))
        if stamp and at-timedelta(hours=48) <= stamp <= at+timedelta(minutes=5):
            reason = news_editorial_reason(item)
            if reason in editorial:
                editorial[reason] += 1
    blocked = {digest(p['id']) for p in parents if p['status']=='blocked_source'}
    editorial['unrenderable_card_text'] = sum(r['id'] in blocked for r in store.rows(
        "SELECT id FROM withheld WHERE reason='unrenderable_card_text'"))
    return {'as_of': at.isoformat(), 'checks': checks,
        'editorial_holds': editorial,
        'window_start': window.isoformat(), 'window_end': window_end.isoformat(),
        'window_open': window <= at < window_end,
        'queue': {status: sum(p['status'] == status for p in parents) for status in ('prepared', 'blocked_source')}
            | {'due': sum(p['status'] == 'prepared' and parse_date(p['due_at']) <= at for p in parents)},
        'today': {'instagram_feed': sum(not p.get('publish_format') for p in today_claims),
                  'instagram_story': sum(p.get('publish_format') == 'story' for p in today_claims),
                  'facebook_feed': sum(r['format'] == 'feed' and today(r['claimed_at']) for r in deliveries),
                  'facebook_story': sum(r['format'] == 'story' and today(r['claimed_at']) for r in deliveries)},
        'unresolved': {'instagram': sum(p['status'] != 'published' and not never_sent(p) for p in claims),
                       'facebook': sum(r['status'] != 'published' for r in deliveries)},
        'not_sent': {'instagram': sum(never_sent(p) for p in claims)},
        'delivery_errors': dict(Counter(p['delivery_error'] for p in claims if p.get('delivery_error'))),
        'daily_feed_limit': NEWS_DAILY_LIMIT,
        'daily_story_limit': NEWS_DAILY_LIMIT, 'service_stories_extra': True,
        'evening_news': evening_summary(at),
        'illustrations': {'utc_day': utc_day.isoformat(), 'attempts': attempts, 'limit': DAILY_ATTEMPTS,
            'remaining': max(0, DAILY_ATTEMPTS - attempts),
            'reset_at': datetime.combine(utc_day + timedelta(days=1), datetime.min.time(), timezone.utc).astimezone(TZ).isoformat()}}


QUIET_AFTER_HOURS = 72
FAILING_RUNS = 4


def quiet_sources(store, sources, at):
    """Readers that produced items before but are now empty or failing.

    `last_seen` also moves when another source re-reports a merged duplicate,
    so the newest `first_seen` per source is the evidence of its own yield.
    Finite reviewed requests stop by design; seasonal readers may set
    `quiet_after_hours`, and a known, non-bypassable block `quiet_acknowledged`.
    A failed read must repeat in each of the last `FAILING_RUNS` runs: in the
    100 runs to 30 Oct, blips lasted at most 3 runs, real blocks 17-84.
    """
    config = {s['id']: s for s in sources}
    newest = {r['sid']: r['newest'] for r in store.rows(
        "SELECT json_extract(payload,'$.source_id') AS sid, MAX(first_seen) AS newest FROM items GROUP BY sid")}
    recent = [{e.get('source_id') for e in json.loads(r['errors'])} for r in store.rows(
        'SELECT errors FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT ?', (FAILING_RUNS,))]
    failing = set.intersection(*recent) if len(recent) == FAILING_RUNS else set()
    result = []
    for row in store.rows("SELECT source_id,status FROM source_health WHERE status IN ('empty','failed') ORDER BY source_id"):
        source, last = config.get(row['source_id']), parse_date(newest.get(row['source_id']))
        if not source or not source.get('enabled', True) or source.get('requested_until') or not last:
            continue
        if row['status'] == 'failed' and row['source_id'] not in failing:
            continue
        if at - last >= timedelta(hours=source.get('quiet_after_hours', QUIET_AFTER_HOURS)):
            result.append({'source_id': row['source_id'], 'status': row['status'],
                           'last_new_item_at': last.isoformat(), 'acknowledged': bool(source.get('quiet_acknowledged'))})
    return result


def write_job_summary(result):
    target = os.getenv('GITHUB_STEP_SUMMARY')
    if target:
        # Only enumerated strings enter Markdown, never arbitrary provider output.
        clean = safe_result(result)
        with Path(target).open('a', encoding='utf-8') as out:
            out.write('### Yayın kontrolü\n\n```json\n' + json.dumps(clean, ensure_ascii=False, indent=2) + '\n```\n\n')
            out.write('İşin tamamlanması yeni paylaşım yapıldığı anlamına gelmez. `outside_window`: yayın saati bekleniyor; `daily_limit`: günlük sınır doldu; `empty`: şu an yayımlanabilir içerik yok.\n')
