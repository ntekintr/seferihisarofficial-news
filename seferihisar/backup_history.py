"""Restore a previous Actions backup in isolation, without touching live state."""
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .domain import now, parse_date
from .ops_watch import Github
from .state_backup import MAX_BYTES, restore_drill


def drill(api, session, at, current_run):
    rows = api.call('GET', 'actions/artifacts', params={'name': 'durable-state-backup', 'per_page': 100}).get('artifacts', [])
    candidates = [r for r in rows if r.get('name') == 'durable-state-backup' and not r.get('expired')
                  and r.get('workflow_run', {}).get('head_branch') == 'main'
                  and str(r.get('workflow_run', {}).get('id')) != str(current_run)
                  and parse_date(r.get('created_at')) and parse_date(r['created_at']).date() < at.date()]
    if not candidates:
        return {'status': 'previous_day_backup_not_yet_available', 'production_modified': False}
    target = max(candidates, key=lambda r: r['created_at'])
    run = api.call('GET', 'actions/runs/' + str(target['workflow_run']['id']))
    if run.get('path') != '.github/workflows/state-backup.yml' or run.get('head_branch') != 'main' or run.get('conclusion') != 'success':
        raise ValueError('Unverified historical backup producer')
    # Signed storage locations and provider bodies never enter logs or state.
    response = session.get('https://api.github.com/repos/ntekintr/seferihisarofficial-news/actions/artifacts/' + str(target['id']) + '/zip',
        headers={'Authorization': 'Bearer ' + api.token, 'Accept': 'application/vnd.github+json'},
        timeout=(5, 20), allow_redirects=False)
    location = response.headers.get('Location', '')
    parts = urlsplit(location)
    if (response.status_code != 302 or parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or not parts.hostname.endswith(('.blob.core.windows.net', '.actions.githubusercontent.com'))):
        raise ValueError('Invalid backup download location')
    raw = session.get(location, timeout=(5, 30), allow_redirects=False, stream=True)
    if raw.status_code != 200:
        raise ValueError('Historical backup unavailable')
    chunks, total = [], 0
    for chunk in raw.iter_content(65536):
        total += len(chunk)
        if total > MAX_BYTES + 1048576:
            raise ValueError('Historical backup download exceeds limit')
        chunks.append(chunk)
    with zipfile.ZipFile(io.BytesIO(b''.join(chunks))) as archive, tempfile.TemporaryDirectory() as directory:
        entry = archive.getinfo('state.zip')
        if entry.file_size > MAX_BYTES + 65536:
            raise ValueError('Historical backup exceeds limit')
        path = Path(directory) / 'state.zip'
        path.write_bytes(archive.read('state.zip'))
        proof = restore_drill(path)
    return {'status': 'restored_previous_day', 'artifact_id': target['id'], **proof}


def main():
    import requests
    session = requests.Session()
    api = Github(os.environ['GITHUB_TOKEN'], session)
    value = drill(api, session, now(), os.getenv('GITHUB_RUN_ID'))
    path = Path('work/state-backup/history-proof.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
