import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

from seferihisar.state_git import persist, restore
from seferihisar.store import Store


def test_state_survives_a_fresh_runner_without_contaminating_code_branch(tmp_path,monkeypatch):
    remote=tmp_path/'remote.git'
    subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
    repo=tmp_path/'repo'
    repo.mkdir()
    subprocess.run(['git','init','-b','main'],cwd=repo,check=True,capture_output=True)
    subprocess.run(['git','remote','add','origin',str(remote)],cwd=repo,check=True,capture_output=True)
    monkeypatch.chdir(repo)
    path=repo/'state/platform.sqlite'
    restore(path)
    db=Store(path)
    db.withhold('private content','human_review_required','2026-10-10T10:00:00+03:00')
    with db.db:
        db.db.execute('INSERT INTO facebook_deliveries VALUES(?,?,?,?,?,?,?,?,NULL)',
            ('a'*24,'b'*24,'1234','feed','uncertain','2026-10-10T10:00:00+03:00','2026-10-10T10:00:00+03:00','[]'))
    db.close()
    persist(path)
    fresh=repo/'fresh/platform.sqlite'
    restore(fresh)
    restored=Store(fresh)
    assert restored.db.execute('SELECT COUNT(*) FROM withheld').fetchone()[0]==1
    assert restored.rows('SELECT status FROM facebook_deliveries')==[{'status':'uncertain'}]
    restored.close()
    assert subprocess.run(['git','branch','--show-current'],check=True,capture_output=True,text=True).stdout.strip()=='main'


def fake_push(monkeypatch, outcomes, heads):
    """Push results in order (True ok, False refused) and the heads ls-remote reports."""
    import seferihisar.state_git as state_git
    monkeypatch.setattr(state_git.time, 'sleep', lambda _: None)
    pushes = []
    def git(*args, input=None):
        if args[0] == 'push':
            pushes.append(args)
            if not outcomes.pop(0):
                raise subprocess.CalledProcessError(1, 'git')
            return b''
        assert args[0] == 'ls-remote'
        head = heads.pop(0)
        if isinstance(head, Exception):
            raise head
        return f'{head}\trefs/heads/automation-state\n'.encode()
    monkeypatch.setattr(state_git, 'git', git)
    return state_git.push, pushes


def test_refused_push_retries_while_the_remote_head_is_unchanged(monkeypatch):
    # 4 Nov 2026: pushes were refused for two hours with the lease head unchanged.
    push, pushes = fake_push(monkeypatch, [False, False, True], ['old', subprocess.CalledProcessError(1, 'git')])
    push('new', 'old')
    assert len(pushes) == 3 and all(p[1] == '--force-with-lease=refs/heads/automation-state:old' for p in pushes)


def test_lost_push_response_is_not_repeated_once_the_commit_is_there(monkeypatch):
    push, pushes = fake_push(monkeypatch, [False], ['new'])
    push('new', 'old')
    assert len(pushes) == 1


def test_concurrent_writer_stops_the_retry(monkeypatch):
    import pytest
    push, pushes = fake_push(monkeypatch, [False, True], ['other'])
    with pytest.raises(subprocess.CalledProcessError):
        push('new', 'old')
    assert len(pushes) == 1


def test_persistent_refusal_still_fails_after_bounded_tries(monkeypatch):
    import pytest
    push, pushes = fake_push(monkeypatch, [False] * 4, ['old'] * 3)
    with pytest.raises(subprocess.CalledProcessError):
        push('new', 'old')
    assert len(pushes) == 4


def test_write_credential_is_scoped_to_git_environment_and_preserves_existing_config(monkeypatch):
    from seferihisar.state_git import git
    token='SYNTHETIC_STATE_WRITE_CREDENTIAL'
    monkeypatch.setenv('STATE_WRITE_TOKEN',token)
    monkeypatch.setenv('GIT_CONFIG_COUNT','1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0','http.proxy')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0','http://proxy:8080')
    run=Mock(return_value=SimpleNamespace(stdout=b'ok'))
    monkeypatch.setattr('seferihisar.state_git.subprocess.run',run)
    assert git('ls-remote','origin')==b'ok'
    args,kwargs=run.call_args
    assert token not in str(args)
    assert kwargs['env']['GIT_CONFIG_COUNT']=='2'
    assert kwargs['env']['GIT_CONFIG_VALUE_0']=='http://proxy:8080'
    assert kwargs['env']['GIT_CONFIG_KEY_1']=='http.https://github.com/.extraheader'
