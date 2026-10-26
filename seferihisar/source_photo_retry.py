"""Bounded public-safe cooldowns; failed pictures cannot monopolize later runs."""
from datetime import datetime, timedelta
import re

MAX_ROWS = 400
STAGES = frozenset(('source_read', 'source_binding', 'image_read', 'image_format',
                    'event_text', 'visual_subject', 'cache_binding', 'checker_unavailable'))
COLUMNS = ['item_id', 'revision', 'checked_at', 'retry_at', 'stage']


def wait(stage):
    if stage not in STAGES:
        raise ValueError('Unknown photo retry stage')
    return timedelta(minutes=15 if stage == 'checker_unavailable' else
                     60 if stage in ('source_read', 'image_read') else 360)


def validate_row(row):
    item, revision, checked, retry, stage = row
    if not isinstance(item, str) or not re.fullmatch(r'[a-f0-9]{24}', item):
        raise ValueError('Invalid photo retry identity')
    if type(revision) is not int or not 1 <= revision <= 1000000:
        raise ValueError('Invalid photo retry revision')
    start, end = datetime.fromisoformat(checked), datetime.fromisoformat(retry)
    if start.tzinfo is None or end.tzinfo is None or end - start != wait(stage):
        raise ValueError('Invalid photo retry interval')


def active(store, item, at):
    rows = store.rows('SELECT * FROM source_photo_retries WHERE item_id=? AND revision=?',
                      (item['id'], item['revision']))
    if not rows:
        return False
    row = rows[0]
    validate_row(tuple(row[k] for k in COLUMNS))
    checked, retry = datetime.fromisoformat(row['checked_at']), datetime.fromisoformat(row['retry_at'])
    return checked - timedelta(minutes=5) <= at < retry


def remember(store, item, at, stage):
    row = (item['id'], item['revision'], at.isoformat(), (at + wait(stage)).isoformat(), stage)
    validate_row(row)
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO source_photo_retries VALUES(?,?,?,?,?)', row)
        store.db.execute('DELETE FROM source_photo_retries WHERE rowid NOT IN '
                         '(SELECT rowid FROM source_photo_retries ORDER BY checked_at DESC,rowid DESC LIMIT ?)',
                         (MAX_ROWS,))


def clear(store, item):
    with store.db:
        store.db.execute('DELETE FROM source_photo_retries WHERE item_id=?', (item['id'],))


def prune(store, allowed_ids):
    with store.db:
        for row in store.rows('SELECT item_id,revision FROM source_photo_retries'):
            if row['item_id'] not in allowed_ids:
                store.db.execute('DELETE FROM source_photo_retries WHERE item_id=? AND revision=?',
                                 (row['item_id'], row['revision']))
