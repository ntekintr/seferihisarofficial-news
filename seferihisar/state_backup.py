"""A second, bounded archive and an isolated restore drill. Never restore production."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .security import assert_no_secrets, validate_state

MAX_BYTES = 48 * 1024 * 1024


def inspect(path):
    validate_state(path)
    with closing(sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity failed')
        names = sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        counts = {name: db.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0] for name in names}
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size, 'tables': counts}


def create(source, target, at, state_sha):
    import re
    if at.tzinfo is None or not re.fullmatch(r'[a-f0-9]{40}', state_sha):
        raise ValueError('Verified state provenance required')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        copy = Path(directory) / 'platform.sqlite'
        with closing(sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True)) as src, closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
        info = inspect(copy)
        if info['bytes'] > MAX_BYTES:
            raise ValueError('Backup exceeds bounded archive limit')
        manifest = {'version': 'state-backup-v1', 'created_at': at.isoformat(), 'state_sha': state_sha, **info}
        assert_no_secrets(manifest)
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            out.write(copy, 'platform.sqlite')
            out.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
    return restore_drill(target)


def restore_drill(archive):
    import re
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory() as directory:
        entries = source.infolist()
        if len(entries) != 2 or {r.filename for r in entries} != {'platform.sqlite', 'manifest.json'}:
            raise ValueError('Unexpected backup archive entries')
        if sum(r.file_size for r in entries) > MAX_BYTES + 65536:
            raise ValueError('Backup archive exceeds limit')
        manifest = json.loads(source.read('manifest.json'))
        assert_no_secrets(manifest)
        if (set(manifest) != {'version', 'created_at', 'state_sha', 'sha256', 'bytes', 'tables'}
                or manifest['version'] != 'state-backup-v1'
                or datetime.fromisoformat(manifest['created_at']).tzinfo is None
                or not re.fullmatch(r'[a-f0-9]{40}', str(manifest['state_sha']))
                or not re.fullmatch(r'[a-f0-9]{64}', str(manifest['sha256']))):
            raise ValueError('Invalid backup manifest')
        target = Path(directory) / 'platform.sqlite'
        target.write_bytes(source.read('platform.sqlite'))
        observed = inspect(target)
        if any(observed[k] != manifest[k] for k in observed):
            raise ValueError('Restored backup differs from manifest')
    return {'version': 'state-backup-v1', 'created_at': manifest['created_at'], 'state_sha': manifest['state_sha'],
            'bytes': manifest['bytes'], 'integrity': 'ok', 'restored_in_isolation': True,
            'production_modified': False, 'provider_independent': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['capture', 'create', 'drill'])
    parser.add_argument('--archive', type=Path, default=Path('work/state-backup/state.zip'))
    parser.add_argument('--state-sha')
    args = parser.parse_args()
    from .domain import now
    if args.action == 'capture':
        from .state_git import remote_head, git
        head = remote_head()
        if not head:
            raise SystemExit('Existing durable state required; no empty backup created.')
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / 'platform.sqlite'
            snapshot.write_bytes(git('show', head + ':platform.sqlite'))
            value = create(snapshot, args.archive, now(), head)
    else:
        value = create(Path('state/platform.sqlite'), args.archive, now(), args.state_sha) if args.action == 'create' else restore_drill(args.archive)
    result = args.archive.parent / ('create-proof.json' if args.action != 'drill' else 'restore-proof.json')
    result.write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
