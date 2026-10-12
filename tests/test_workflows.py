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


def test_publication_requires_trusted_completed_research_or_explicit_dispatch():
    workflow=yaml.load(Path('.github/workflows/publish.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['on']['workflow_run']=={'workflows':['Research and prepare Seferihisar content'],'types':['completed'],'branches':['main']}
    assert 'META_TESTS_COMPLETED' in workflow['jobs']['publish']['if']
    assert "inputs.confirm == 'PUBLISH'" in workflow['jobs']['publish']['if']
    assert "github.event.workflow_run.conclusion == 'success'" in workflow['jobs']['publish']['if']
    assert 'github.event.workflow_run.head_repository.full_name == github.repository' in workflow['jobs']['publish']['if']
    assert workflow['jobs']['publish']['steps'][0]['with']['ref']=='main'
    assert workflow['jobs']['publish']['environment']=='instagram-production'
    assert workflow['concurrency']['group']=='seferihisar-production'


def test_permissions_are_scoped_to_the_jobs_that_need_them():
    workflow=yaml.load(Path('.github/workflows/automation.yml').read_text(),Loader=yaml.BaseLoader)
    assert workflow['permissions']=={'contents':'read'}
    jobs=workflow['jobs']
    assert jobs['research'].get('permissions',workflow['permissions'])=={'contents':'read'}
    assert jobs['persist']['permissions']=={'contents':'write'}
    assert jobs['deploy']['permissions']=={'contents':'read','pages':'write','id-token':'write'}
    assert jobs['persist']['needs']=='research'
    assert jobs['deploy']['needs']==['research','persist']
    assert jobs['research']['steps'][0]['with']['persist-credentials']=='false'
    assert 'GEMINI_API_KEY' not in jobs['research']['env']
    secret_steps=[s for s in jobs['research']['steps'] if 'GEMINI_API_KEY' in s.get('env',{})]
    assert len(secret_steps)==1 and secret_steps[0]['run']=='python -m seferihisar.cli run'
    image_steps=[s for s in jobs['research']['steps'] if 'CLOUDFLARE_API_TOKEN' in s.get('env',{})]
    assert len(image_steps)==1 and image_steps[0]['run']=='python -m seferihisar.cli run'
    assert image_steps[0]['env']['ILLUSTRATIONS_ENABLED']=='true'
    assert 'CLOUDFLARE_API_TOKEN' not in jobs['research']['env']
    assert 'env' not in jobs['persist'] and 'env' not in jobs['deploy']


def test_external_actions_are_pinned_and_uploads_are_validated():
    import re
    for path in Path('.github/workflows').glob('*.yml'):
        workflow=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
        assert 'pull_request_target' not in workflow['on']
        for job in workflow['jobs'].values():
            for step in job['steps']:
                if 'uses' in step:
                    assert re.fullmatch(r'actions/[a-z-]+@[a-f0-9]{40}',step['uses'])
                    if step['uses'].startswith('actions/checkout@'):
                        assert step['with']['persist-credentials']=='false'
    workflow=yaml.load(Path('.github/workflows/automation.yml').read_text(),Loader=yaml.BaseLoader)
    steps=workflow['jobs']['research']['steps']
    check=next(i for i,s in enumerate(steps) if 'security state' in s.get('run',''))
    uploads=[i for i,s in enumerate(steps) if s.get('uses','').startswith('actions/upload')]
    assert all(i>check for i in uploads)


def test_free_image_check_is_manual_and_cannot_publish_or_write_state():
    path=Path('.github/workflows/illustration-check.yml')
    workflow=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    assert list(workflow['on'])==['workflow_dispatch']
    assert workflow['permissions']=={'contents':'read'}
    assert workflow['jobs']['preview']['if']=="github.ref == 'refs/heads/main'"
    assert 'INSTAGRAM_ACCESS_TOKEN' not in path.read_text()
    assert 'state_git' not in path.read_text() and 'deploy-pages' not in path.read_text()
    uploads=[s for s in workflow['jobs']['preview']['steps'] if s.get('uses','').startswith('actions/upload')]
    assert len(uploads)==1
    assert uploads[0]['with']['path'].splitlines()==['work/illustration-preview/feed.jpg','work/illustration-preview/story.jpg']
