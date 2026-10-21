"""Coarse fixed-age observations, without raw private Meta measurements."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from .domain import CATEGORIES, digest, parse_date

MAX_ROWS = 400
WINDOWS = {'day1': (24, 30), 'day7': (168, 174)}


def cohort_for(stamp, at):
    age = (at - stamp).total_seconds() / 3600
    return next((key for key, (start, end) in WINDOWS.items() if start <= age < end), None)


def validate_row(row):
    key, post, category, cohort, age, band, reached, checked = row
    if (not all(isinstance(v, str) and re.fullmatch(r'[a-f0-9]{24}', v) for v in (key, post))
            or key != digest(post + ':' + cohort) or category not in CATEGORIES or cohort not in WINDOWS
            or type(age) is not int or not WINDOWS[cohort][0] <= age < WINDOWS[cohort][1]
            or type(band) is not int or not 0 <= band <= 50 or type(reached) is not int or reached not in (0, 1)
            or datetime.fromisoformat(checked).tzinfo is None):
        raise ValueError('Invalid coarse learning observation')


def pending(store, at):
    known = {r['id'] for r in store.rows('SELECT id FROM learning_samples')}
    result = []
    for post in store.posts():
        stamp = parse_date(post.get('published_at'))
        if (post['status'] != 'published' or post.get('publish_format') or not post.get('item_id')
                or not stamp or post.get('category') not in CATEGORIES):
            continue
        cohort = cohort_for(stamp, at)
        if cohort and digest(post['id'] + ':' + cohort) not in known:
            result.append((post, cohort))
    return sorted(result, key=lambda row: row[0]['published_at'])[:20]


def record(store, post, cohort, values, at):
    stamp = parse_date(post['published_at'])
    if cohort_for(stamp, at) != cohort:
        raise ValueError('Outside fixed-age observation window')
    reach = values['reach']
    # Each step is one percentage point, capped at 50. It is not a raw counter,
    # probability, unique-person total or proof of organic attribution.
    score = values['total_interactions'] + values['saved'] + values['shares']
    band = min(50, math.floor(100 * score / reach)) if reach else 0
    row = (digest(post['id'] + ':' + cohort), post['id'], post['category'], cohort,
           int((at - stamp).total_seconds() // 3600), band, int(reach >= 100), at.isoformat())
    validate_row(row)
    with store.db:
        store.db.execute('INSERT OR IGNORE INTO learning_samples VALUES (?,?,?,?,?,?,?,?)', row)
        store.db.execute('DELETE FROM learning_samples WHERE id NOT IN (SELECT id FROM learning_samples ORDER BY checked_at DESC,id LIMIT ?)', (MAX_ROWS,))


def weights(store, at):
    rows = [r for r in store.rows('SELECT * FROM learning_samples')
            if at - timedelta(days=28) <= parse_date(r['checked_at']) <= at and r['reach_gate']]
    for cohort in ('day1', 'day7'):
        groups = defaultdict(list)
        for row in rows:
            if row['cohort'] == cohort:
                groups[row['category']].append(row['score_band'])
        eligible = {k: v for k, v in groups.items() if len(v) >= 3}
        if len(eligible) < 2 or sum(map(len, eligible.values())) < 10:
            continue
        baseline = median([score for values in eligible.values() for score in values])
        return {key: int(median(values) >= max(2, baseline * 1.25)) for key, values in eligible.items()}
    return {}


def summary(store, at):
    rows = store.rows('SELECT cohort,COUNT(*) AS n FROM learning_samples GROUP BY cohort')
    return {'version': 'fixed-age-feedback-v1', 'observations': {r['cohort']: r['n'] for r in rows},
            'windows_hours': {k: list(v) for k, v in WINDOWS.items()}, 'pending': len(pending(store, at)),
            'attribution': 'paid_and_organic_not_separated', 'raw_measurements_retained': False,
            'comparison': 'same_age_cohort_only', 'minimum_posts': 10, 'minimum_topics': 2}
