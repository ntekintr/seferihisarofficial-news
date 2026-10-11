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
    db.close()
    persist(path)
    fresh=repo/'fresh/platform.sqlite'
    restore(fresh)
    restored=Store(fresh)
    assert restored.db.execute('SELECT COUNT(*) FROM withheld').fetchone()[0]==1
    restored.close()
    assert subprocess.run(['git','branch','--show-current'],check=True,capture_output=True,text=True).stdout.strip()=='main'


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
