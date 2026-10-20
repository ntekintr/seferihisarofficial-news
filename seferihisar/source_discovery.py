"""Bounded recurring discovery; an external link never inherits publisher trust."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from .domain import canonical, digest, parse_date
from .security import contains_secret, public_url

MAX_CANDIDATES = 300
MAX_ACTIVE = 8
DAILY_CHECKS = 3
EXCLUDED_HOSTS = {'guzelbahce.gov.tr', 'www.guzelbahce.gov.tr'}
RESULTS = {'observing', 'active', 'unverified_origin', 'no_current_items', 'access_failed'}
FIELDS = {'id', 'name', 'url', 'kind', 'enabled', 'trusted', 'access', 'max_pages', 'follow_feed_details'}


def host(url):
    return urlsplit(url).hostname


def eligible_origin(candidate, sources):
    destination = host(candidate['url'])
    if destination in EXCLUDED_HOSTS:
        return False
    trusted = {host(s['url']) for s in sources if s.get('trusted') and s.get('enabled')}
    if destination in trusted:
        return True
    origins = candidate.get('discovered_from', [])
    # A new Turkish public institution needs independent references from two
    # configured publishers, registry-restricted government/municipal naming,
    # valid TLS/robots and the same three-day content checks as existing hosts.
    # Arbitrary commercial domains never inherit trust through hyperlinks.
    return (bool(destination) and destination.endswith(('.gov.tr', '.bel.tr'))
            and isinstance(origins, list)
            and len({host(o) for o in origins if public_url(o) and host(o) in trusted}) >= 2)


def validate_check(row):
    key, stamp, result, successes, payload = row
    value = json.loads(payload)
    if (not re.fullmatch(r'[a-f0-9]{24}', key) or datetime.fromisoformat(stamp).tzinfo is None
            or result not in RESULTS or type(successes) is not int or not 0 <= successes <= 3
            or (result == 'active' and successes != 3)
            or not isinstance(value, dict) or set(value) != FIELDS
            or value['id'] != 'auto-' + key or not public_url(value['url']) or digest(value['url']) != key or contains_secret(value)
            or value['name'] != host(value['url']) or value['kind'] != 'rss'
            or value['access'] != 'robots' or value['max_pages'] != 1 or value['follow_feed_details'] is not False
            or value['enabled'] is not True or value['trusted'] is not True):
        raise ValueError('Invalid discovered reader')
    return value


def register(store, candidates, sources, at):
    """Persist only public endpoints/provenance from actually configured readers."""
    trusted = {host(s['url']) for s in sources if s.get('trusted') and s.get('enabled')}
    known = {r['id']: json.loads(r['payload']) for r in store.rows('SELECT * FROM candidates')}
    for candidate in candidates:
        raw = candidate.get('url', '')
        origin = candidate.get('discovered_from', '')
        if not public_url(raw) or not public_url(origin) or host(origin) not in trusted:
            continue
        split = urlsplit(raw)
        # Discard query, credentials, fragment and unbounded labels.
        kind = candidate.get('kind')
        if kind not in ('rss', 'html'):
            continue
        url = f"https://{split.hostname}{split.path if kind == 'rss' else '/'}"
        if not public_url(url) or len(url) > 500:
            continue
        key = digest(url)
        old = known.get(key, {})
        if key not in known and len(known) >= MAX_CANDIDATES:
            continue
        origins = [o for o in old.get('discovered_from', []) if isinstance(o, str) and public_url(o)] if isinstance(old.get('discovered_from'), list) else []
        origins = sorted(set(origins + [f'https://{host(origin)}/']))[:8]
        value = {'id': key, 'url': url, 'name': split.hostname, 'kind': kind,
                 'enabled': False, 'trusted': False, 'access': 'review_required',
                 'discovered_from': origins, 'first_seen': old.get('first_seen', at.isoformat()),
                 'last_seen': at.isoformat()}
        with store.db:
            store.db.execute('INSERT OR REPLACE INTO candidates VALUES (?,?)', (key, json.dumps(value)))
        known[key] = value


def active_sources(store, sources):
    configured = {s['id']: s for s in sources}
    urls = {s['url'] for s in sources}
    candidates = {r['id']: json.loads(r['payload']) for r in store.rows('SELECT * FROM candidates')}
    result = list(sources)
    for row in store.db.execute("SELECT * FROM source_checks WHERE result='active' ORDER BY candidate_id LIMIT ?", (MAX_ACTIVE,)):
        value = validate_check(tuple(row))
        # Re-evaluate origin references against today's configuration, even
        # when an old state still calls the derived feed active.
        candidate = candidates.get(row['candidate_id'])
        if candidate and candidate['url'] == value['url'] and eligible_origin(candidate, sources) and value['url'] not in urls and value['id'] not in configured:
            result.append(value)
            urls.add(value['url'])
    return result


def refresh(store, sources, at, *, fetcher_factory=None):
    from .collect import Fetcher, discover, feed_items
    from .editor import verify
    from .timeliness import publication_reason, with_validity
    fetcher_factory = fetcher_factory or Fetcher
    checked_today = store.db.execute("SELECT COUNT(*) FROM source_checks WHERE result!='unverified_origin' AND checked_at LIKE ?",
                                     (at.date().isoformat() + '%',)).fetchone()[0]
    remaining = max(0, DAILY_CHECKS - checked_today)
    active = store.db.execute("SELECT COUNT(*) FROM source_checks WHERE result='active'").fetchone()[0]
    configured_hosts = {host(s['url']) for s in sources if s.get('trusted') and s.get('enabled')}
    configured_urls = {canonical(s['url']) for s in sources}
    checks = {r['candidate_id']: r for r in store.rows('SELECT * FROM source_checks')}
    candidates = [json.loads(r['payload']) for r in store.rows('SELECT payload FROM candidates ORDER BY id')]
    # RSS from already verified publishers first; never retry the stopped
    # Instagram target or the disabled TLS endpoint through this feature.
    candidates.sort(key=lambda c: (host(c['url']) not in configured_hosts, c.get('first_seen', ''), c['id']))
    for candidate in candidates:
        if remaining <= 0:
            break
        if canonical(candidate['url']) in configured_urls:
            continue
        origins = candidate.get('discovered_from', [])
        if not isinstance(origins, list) or not any(public_url(o) and host(o) in configured_hosts for o in origins):
            continue
        old = checks.get(candidate['id'])
        eligible = eligible_origin(candidate, sources)
        if old:
            if old['result'] == 'active':
                continue
            interval = timedelta(hours=20) if old['result'] == 'observing' else timedelta(days=7)
            if not (old['result'] == 'unverified_origin' and eligible) and (parse_date(old['checked_at']).date() == at.date() or at - parse_date(old['checked_at']) < interval):
                continue
        remaining -= int(eligible)
        value = {'id': 'auto-' + candidate['id'], 'name': host(candidate['url']),
                 'url': candidate['url'], 'kind': 'rss', 'enabled': True, 'trusted': True,
                 'access': 'robots', 'max_pages': 1, 'follow_feed_details': False}
        result, successes = 'unverified_origin', 0
        # Unknown domains remain isolated; neither repeated reads nor model
        # confidence can promote them to a trusted factual publisher.
        if eligible:
            try:
                source = next((s for s in sources if host(s['url']) == host(value['url']) and s.get('trusted') and s.get('enabled')), {})
                probe = {**value, 'allow_missing_robots': source.get('allow_missing_robots', False)}
                fetcher = fetcher_factory([probe])
                body, final = fetcher.get(value['url'])
                if host(final) != host(value['url']):
                    raise ValueError('Changed source origin')
                if candidate['kind'] == 'html':
                    for origin in origins:
                        if host(origin) in configured_hosts:
                            discovered = [{**c, 'discovered_from': origin} for c in discover(body, final)]
                            register(store, discovered, sources, at)
                    result = 'no_current_items'
                else:
                    items = [with_validity(i) for i in feed_items(body, final, probe)]
                    valid = {i['url'] for i in items if verify(i, probe, at) is None and publication_reason(i, at) is None}
                    if len(valid) >= 2:
                        successes = min(3, (old['successes'] if old else 0) + 1)
                        result = 'active' if successes >= 3 and active < MAX_ACTIVE else 'observing'
                        active += int(result == 'active')
                    else:
                        result = 'no_current_items'
            except Exception:
                result = 'access_failed'  # No raw network/provider text.
        payload = json.dumps(value)
        row = (candidate['id'], at.isoformat(), result, successes, payload)
        validate_check(row)
        with store.db:
            store.db.execute('INSERT OR REPLACE INTO source_checks VALUES (?,?,?,?,?)', row)
    return summary(store)


def summary(store):
    return {'candidates': store.db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0],
            'checks': {r['result']: r['n'] for r in store.rows('SELECT result,COUNT(*) AS n FROM source_checks GROUP BY result')},
            'daily_check_limit': DAILY_CHECKS, 'automatic_reader_limit': MAX_ACTIVE,
            'promotion_policy': 'three_daily_current_rss_checks_with_trusted_origin_or_two_references_to_a_new_public_institution'}
