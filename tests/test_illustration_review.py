import io
import json
from pathlib import Path

from PIL import Image

from seferihisar import illustration_review as review
from seferihisar.illustrations import Illustrator, clean_image, image_key
from seferihisar.image_safety import IllustrationTextRejected


def jpeg():
    buffer = io.BytesIO()
    Image.new('RGB', (512, 512), '#346175').save(buffer, 'PNG')
    return clean_image(buffer.getvalue())


def test_review_is_opt_in_bounded_and_not_a_public_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    review.save_rejected_image('a' * 24, jpeg(), [])
    assert not (tmp_path / 'work').exists()
    monkeypatch.setenv('ILLUSTRATION_REVIEW_ENABLED', 'true')
    for n in range(6):
        review.save_rejected_image(f'{n:024x}', jpeg(), [])
    folder = tmp_path / 'work' / 'illustration-review'
    assert len(list(folder.glob('*.jpg'))) == 4
    assert len(list(folder.glob('*.json'))) == 4
    assert not (tmp_path / 'dist').exists()
    assert all(json.loads(p.read_text())['approved_for_publication'] is False for p in folder.glob('*.json'))
    review.save_rejected_image('../outside', jpeg(), [])
    assert not (tmp_path / 'outside.jpg').exists()


def test_rejected_generation_is_quarantined_and_review_never_enters_state(store, event, at, tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    for name, value in [('ILLUSTRATION_REVIEW_ENABLED', 'true'), ('ILLUSTRATIONS_ENABLED', 'true'),
                        ('CLOUDFLARE_API_TOKEN', 'SYNTHETIC_CLOUDFLARE_CREDENTIAL_0123456789'),
                        ('CLOUDFLARE_ACCOUNT_ID', 'a' * 32)]:
        monkeypatch.setenv(name, value)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.illustrations.validate_match', lambda data, expected: {})
    finding = {'text': '2021', 'confidence': 35, 'box': {'left': 10, 'top': 10, 'width': 50, 'height': 20}}
    def reject(data):
        raise IllustrationTextRejected(findings=[finding])
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration', reject)
    monkeypatch.setattr(Illustrator, 'generate', lambda self, item: jpeg())
    store.upsert(event, at.isoformat())
    item = store.items()[0]
    illustrator = Illustrator(store, at, tmp_path / 'materialized')
    assert illustrator.image(item, generate=True) is None
    key = image_key(item)
    row = store.rows('SELECT * FROM illustrations WHERE id=?', (key,))[0]
    assert row['status'] == 'failed' and row['image'] is None and row['attempts'] == 2
    folder = tmp_path / 'work' / 'illustration-review'
    assert (folder / (key + '.jpg')).read_bytes() == jpeg()
    report = json.loads((folder / (key + '.json')).read_text())
    assert report['findings'] == [finding]
    assert '2021' not in json.dumps(row)
    assert not (tmp_path / 'materialized').exists()


def test_workflow_review_upload_is_separate_from_pages_and_state():
    import yaml
    workflow = yaml.load(Path('.github/workflows/automation.yml').read_text(), Loader=yaml.BaseLoader)
    uploads = [s for s in workflow['jobs']['research']['steps'] if s.get('with', {}).get('name') == 'illustration-review']
    assert len(uploads) == 1
    assert uploads[0]['with']['path'] == 'work/illustration-review'
    assert uploads[0]['with']['retention-days'] == '3'
    assert uploads[0]['if'] == 'always()'
    assert 'illustration-review' not in json.dumps(workflow['jobs']['deploy'])
    assert 'illustration-review' not in json.dumps(workflow['jobs']['persist'])

