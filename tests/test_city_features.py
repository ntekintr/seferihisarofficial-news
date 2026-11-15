"""Reviewed city features: sourced history posts and reply-prompt stories (owner, 14 Nov 2026)."""
from datetime import date, datetime
from io import BytesIO
import hashlib
from pathlib import Path

from PIL import Image
import pytest
import requests

from seferihisar import city_features as cf
from seferihisar.domain import TZ
from seferihisar.security import validate_state
from seferihisar.store import Store
from seferihisar.weather_data import SITE

TUESDAY = datetime(2026, 11, 17, 19, 50, tzinfo=TZ)   # feed day
MONDAY = datetime(2026, 11, 16, 20, 50, tzinfo=TZ)    # story day


class Response:
    def __init__(self, data=None, content=b'', content_type='application/json'):
        self.status_code = 200
        self.data, self.content = data, content
        self.headers = {'Content-Type': content_type}

    def json(self):
        return self.data


class API:
    account = '17841400000000000'
    auth_mode = 'instagram_login'
    base = 'https://graph.instagram.com/v26.0'

    def __init__(self, snapshot, public_dir):
        self.session = self
        self.snapshot, self.public = snapshot, Path(public_dir)
        self.mutations, self.fail = [], False

    def get(self, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        if url == SITE + '/data.json':
            return Response({'city_feature': self.snapshot})
        path = url.removeprefix(SITE + '/')
        return Response(content=(self.public / path).read_bytes(), content_type='image/jpeg')

    def enabled(self):
        return True

    def call(self, path, method=None, **kwargs):
        if path == 'me':
            return {'user_id': self.account, 'username': 'seferihisarofficial', 'account_type': 'BUSINESS'}
        self.mutations.append(('publish', path, kwargs))
        return {'id': '222'}

    def container(self, urls, caption, story):
        self.mutations.append(('container', urls, caption, story))
        if self.fail:
            raise requests.Timeout()
        return '111'

    def wait(self, container):
        assert container == '111'


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(cf, '_profile_enabled', lambda: True)
    import seferihisar.pharmacy
    monkeypatch.setattr(seferihisar.pharmacy, 'account_matches', lambda api: True)
    value = Store(tmp_path / 'state.sqlite')
    yield value
    value.close()


def deployed(store, at, tmp_path):
    public = tmp_path / 'dist'
    snapshot = cf.export(store, public, at)
    return API(snapshot, public)


def test_bank_is_reviewed_complete_and_renders_every_card(tmp_path):
    bank = cf.load_bank()
    feeds = [e for e in bank['entries'] if e['format'] == 'feed']
    stories = [e for e in bank['entries'] if e['format'] == 'story']
    assert len(feeds) >= 8 and len(stories) >= 12
    from seferihisar.city_render import render
    for entry in bank['entries']:
        target = tmp_path / f"{entry['id']}.jpg"
        photo = bank['photos'][entry['photo']]
        render(entry, photo, cf.PHOTOS / photo['file'], target)
        with Image.open(target) as card:
            assert card.size == cf.SIZES[entry['format']]
    for entry in feeds:
        text = cf.caption(entry, bank)
        photo = bank['photos'][entry['photo']]
        assert photo['author'] in text and photo['license'] in text and entry['question'] in text
        assert all(s['url'] in text for s in entry['sources'])


def test_a_changed_photo_is_refused(tmp_path):
    bank = cf.load_bank()
    photos = tmp_path / 'photos'
    photos.mkdir()
    for photo in bank['photos'].values():
        (photos / photo['file']).write_bytes((cf.PHOTOS / photo['file']).read_bytes())
    first = next(iter(bank['photos'].values()))
    (photos / first['file']).write_bytes(b'not the reviewed photo')
    with pytest.raises(ValueError, match='reviewed record'):
        cf.load_bank(photos=photos)


def test_schedule_starts_16_november_story_mon_wed_fri_feed_tue_sat():
    assert cf.scheduled_format(date(2026, 11, 15)) is None
    assert cf.scheduled_format(date(2026, 11, 16)) == 'story'
    assert cf.scheduled_format(date(2026, 11, 17)) == 'feed'
    assert cf.scheduled_format(date(2026, 11, 21)) == 'feed'
    assert cf.scheduled_format(date(2026, 11, 19)) is None
    assert cf.scheduled_format(date(2026, 11, 22)) is None


def test_feed_published_once_in_its_evening_window_with_caption(store, tmp_path):
    api = deployed(store, TUESDAY.replace(hour=9), tmp_path)
    assert api.snapshot['status'] == 'planned' and api.snapshot['format'] == 'feed'
    assert cf.publish(store, TUESDAY.replace(hour=19, minute=0), SITE, api, lambda: None)['status'] == 'outside_window'
    result = cf.publish(store, TUESDAY, SITE, api, lambda: None)
    assert result == {'status': 'published', 'id': cf.load_bank()['entries'][0]['id'], 'format': 'feed'}
    container = api.mutations[0]
    assert container[3] is False and 'Fotoğraf:' in container[2] and 'Kaynak:' in container[2]
    assert cf.rows(store)[0]['status'] == 'published' and cf.rows(store)[0]['media_id'] == '222'
    assert cf.publish(store, TUESDAY.replace(minute=59), SITE, api, lambda: None)['status'] == 'already_published'
    assert len([m for m in api.mutations if m[0] == 'container']) == 1


def test_next_feed_day_takes_the_next_entry_never_a_repeat(store, tmp_path):
    api = deployed(store, TUESDAY, tmp_path)
    cf.publish(store, TUESDAY, SITE, api, lambda: None)
    saturday = datetime(2026, 11, 21, 20, 0, tzinfo=TZ)
    api = deployed(store, saturday, tmp_path)
    assert cf.publish(store, saturday, SITE, api, lambda: None)['status'] == 'published'
    ids = [r['id'] for r in cf.rows(store)]
    feeds = [e['id'] for e in cf.load_bank()['entries'] if e['format'] == 'feed']
    assert ids == feeds[:2]


def test_story_has_no_caption_and_uses_the_story_format(store, tmp_path):
    api = deployed(store, MONDAY, tmp_path)
    assert cf.publish(store, MONDAY, SITE, api, lambda: None)['status'] == 'published'
    assert api.mutations[0][2] == '' and api.mutations[0][3] is True
    with Image.open(tmp_path / 'dist' / api.snapshot['asset']) as card:
        assert card.size == (1080, 1920)


def test_media_not_yet_deployed_makes_no_claim(store, tmp_path):
    api = deployed(store, TUESDAY, tmp_path)
    api.snapshot = dict(api.snapshot, sha256={api.snapshot['asset']: '0' * 64})
    assert cf.publish(store, TUESDAY, SITE, api, lambda: None)['status'] == 'media_not_deployed'
    assert cf.rows(store) == [] and api.mutations == []


def test_uncertain_delivery_is_never_resent_and_stops_the_series(store, tmp_path):
    api = deployed(store, TUESDAY, tmp_path)
    api.fail = True
    assert cf.publish(store, TUESDAY, SITE, api, lambda: None)['status'] == 'uncertain'
    api.fail = False
    assert cf.publish(store, TUESDAY.replace(minute=59), SITE, api, lambda: None)['status'] == 'awaiting_resolution'
    wednesday = datetime(2026, 11, 18, 20, 45, tzinfo=TZ)
    assert cf.publish(store, wednesday, SITE, deployed(store, wednesday, tmp_path), lambda: None)['status'] == 'awaiting_resolution'
    assert len([m for m in api.mutations if m[0] == 'container']) == 1


def test_claim_is_checkpointed_before_the_first_meta_call(store, tmp_path):
    api = deployed(store, TUESDAY, tmp_path)
    seen = []
    def checkpoint():
        seen.append((len(api.mutations), [r['status'] for r in cf.rows(store)]))
    cf.publish(store, TUESDAY, SITE, api, checkpoint)
    assert seen[0] == (0, ['publishing'])


def test_disabled_without_profile_or_checkpoint(store, tmp_path, monkeypatch):
    api = deployed(store, TUESDAY, tmp_path)
    assert cf.publish(store, TUESDAY, SITE, api, None)['status'] == 'disabled'
    monkeypatch.setattr(cf, '_profile_enabled', lambda: False)
    assert cf.publish(store, TUESDAY, SITE, api, lambda: None)['status'] == 'disabled'
    assert api.mutations == []


def test_state_validation_accepts_the_record(store, tmp_path):
    api = deployed(store, TUESDAY, tmp_path)
    cf.publish(store, TUESDAY, SITE, api, lambda: None)
    store.db.commit()
    validate_state(store.path)
    with store.db:
        store.db.execute("UPDATE city_features SET media_id='x'")
    with pytest.raises(ValueError):
        validate_state(store.path)


def test_series_enabled_by_owner_decision():
    assert cf.ENABLED is True
