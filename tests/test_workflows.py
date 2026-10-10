from pathlib import Path

import yaml


def test_scheduled_run_never_has_instagram_credentials_or_publish_command():
    workflow=yaml.load(Path('.github/workflows/automation.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['on']['schedule'][0]['cron']=='7,22,37,52 * * * *'
    assert workflow['concurrency']['cancel-in-progress']=='false'
    text=Path('.github/workflows/automation.yml').read_text()
    assert 'INSTAGRAM_ACCESS_TOKEN' not in text
    assert 'cli publish' not in text
    assert 'state_git restore' in text and 'state_git persist' in text


def test_publication_is_dispatch_only_and_double_gated():
    workflow=yaml.load(Path('.github/workflows/publish.yml').read_text(),Loader=yaml.BaseLoader)
    assert list(workflow['on'])==['workflow_dispatch']
    assert 'META_TESTS_COMPLETED' in workflow['jobs']['publish']['if']
    assert "inputs.confirm == 'PUBLISH'" in workflow['jobs']['publish']['if']
