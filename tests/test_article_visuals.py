"""Unclassified current news: the article's own photo first, then a described scene."""
import io
import json
import shutil
from contextlib import closing
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image

from seferihisar import article_scenes, image_safety, visual_match
from seferihisar.domain import digest, parse_date
from seferihisar.illustrations import Illustrator, scene_version
from seferihisar.image_safety import IllustrationTextRejected, validate_jpeg
from seferihisar.security import validate_state
from seferihisar.source_photo_data import validate_evidence, validate_record
from seferihisar.source_photos import SourcePhotos, photo_subject
from seferihisar.store import Store
from seferihisar.visual_match import MatchRejected
from seferihisar.visual_topics import unclassified_news

AT = parse_date('2026-10-30T09:00:00+03:00')
ACCOUNT = 'a' * 32
GOOD = ('{"objects": ["open notebook", "fountain pen", "red flag"], '
        '"scene": "An open old notebook with a fountain pen and a small plain red flag on a wooden desk '
        'in soft daylight.", "description": "a photograph of an open notebook, a fountain pen and a small red flag"}')


def jpeg(size=(768, 432), color='#447799'):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, 'JPEG')
    return out.getvalue()


def news(number=1, title='Ethem amca cumhuriyetin 103’üncü yılını okuduğu şiirlerle kutladı'):
    return {'id': digest('article-' + str(number)), 'revision': 1, 'kind': 'news', 'category': 'news',
            'title': title, 'description': 'Isparta’da yaşayan Ethem amca bayram için yazdığı şiirleri okudu.'}


@pytest.mark.parametrize('title,expected', [
    ('Ethem amca cumhuriyetin 103’üncü yılını okuduğu şiirlerle kutladı', True),
    ('Cumhuriyet Bayramı Coşkuyla Kutlandı', True),
    ('Kermes yarın yapılacak', False),        # advance notice
    ('Yarın sel riski bekleniyor', False),    # photo deliberately withheld
    ('Mandalina hasadı başlayacak', False),   # photo deliberately withheld
    ('Muhtarlarla bir araya geldi', False),   # reviewed topic keeps its label
])
def test_only_current_unclassified_news_takes_the_article_paths(title, expected):
    item = {'kind': 'news', 'category': 'news', 'title': title}
    assert unclassified_news(item) is expected
    assert (photo_subject(item) == 'article_photo') is expected
    assert unclassified_news({**item, 'kind': 'event'}) is False
    assert (scene_version({**item, 'id': 'x', 'revision': 1}) == article_scenes.VERSION) is expected


def test_scene_brief_is_untrusted_and_strictly_validated():
    item = news()
    body = article_scenes.request(item)
    assert body['messages'][0]['content'] == article_scenes.SYSTEM and body['temperature'] == 0
    assert json.loads(body['messages'][1]['content'])['headline'] == item['title']
    brief = article_scenes.parse('Here you go: ' + GOOD, item)
    assert brief == {'scene': json.loads(GOOD)['scene'],
                     'description': 'a photograph of an open notebook, a fountain pen and a small red flag'}
    for bad in ('{"scene": null}', 'no json at all', '["list"]',
                GOOD.replace('An open old notebook', 'An old man reading a notebook'),
                GOOD.replace('small plain red flag', 'banner with the words Happy Day'),
                GOOD.replace('soft daylight', 'soft daylight in the year'),  # still valid, control below
                GOOD.replace('An open old notebook', 'Ethem holding an open old notebook'),
                GOOD.replace('a photograph of an open', 'an open'),
                GOOD.replace('wooden desk', 'wooden desk near Seferihisar castle'),
                '{"scene": "A desk.", "description": "a photograph of a desk"}',
                GOOD.replace('"objects": ["open notebook", "fountain pen", "red flag"], ', ''),
                GOOD.replace('"red flag"]', '"red flag", "brass medal"]'),         # listed, not drawn
                GOOD.replace('on a wooden desk', 'on a coffee table in a living room'),
                GOOD.replace('in soft daylight', 'by a window with a city view'),
                GOOD.replace('"fountain pen"', '"Ethem pen"')):
        if 'in the year' in bad:
            article_scenes.parse(bad, item)
            with pytest.raises(article_scenes.SceneRejected):
                article_scenes.parse(bad.replace('in the year', 'in 1923'), item)
            continue
        with pytest.raises(article_scenes.SceneRejected):
            article_scenes.parse(bad, item)


def model_session(*answers):
    responses = []
    for answer in answers:
        response = MagicMock(status_code=200)
        response.iter_content.return_value = [json.dumps({'success': True, 'result': {'response': answer}}).encode()]
        responses.append(response)
    session = MagicMock()
    session.post.return_value.__enter__.side_effect = responses
    return session, responses


def test_brief_request_uses_existing_account_and_returns_only_validated_text():
    session, responses = model_session(GOOD, '{"score": 8}', GOOD)
    brief = article_scenes.describe(session, ACCOUNT, 'test-token', news())
    url = session.post.call_args.args[0]
    assert url.endswith('/accounts/' + ACCOUNT + '/ai/run/' + article_scenes.TEXT_MODEL)
    assert session.post.call_args.kwargs['headers'] == {'Authorization': 'Bearer test-token'}
    assert brief['description'].startswith('a photograph of ')
    judged = session.post.call_args_list[1].kwargs['json']
    assert judged['messages'][0]['content'] == article_scenes.JUDGE and judged['temperature'] == 0
    assert json.loads(judged['messages'][1]['content'])['image_brief'] == brief['scene']
    responses[2].status_code = 403
    with pytest.raises(ValueError):
        article_scenes.describe(session, ACCOUNT, 'test-token', news())


@pytest.mark.parametrize('verdict', ['{"score": 6}', '{"score": 2}', 'Looks fine to me', '{"score": 11}',
                                     '{"score": "seven"}'])
def test_brief_that_does_not_clearly_fit_the_story_is_rejected(verdict):
    session, _ = model_session(GOOD, verdict)
    with pytest.raises(article_scenes.SceneRejected) as rejected:
        article_scenes.describe(session, ACCOUNT, 'test-token', news())
    assert session.post.call_count == 2
    assert rejected.value.code in ('low_relevance', 'no_score')
    assert (rejected.value.score is None) == (rejected.value.code == 'no_score')
    assert article_scenes.relevance('{"score": "7"}') == 7 == article_scenes.MIN_RELEVANCE


@pytest.mark.parametrize('answer', ['{"score": 8}', 'Here is the JSON object:\n\n{"score": 8}', '{"score": 8, "reason": "the medal cl',
                                    'Score: 8', '**score** = 8', '8', '8/10', ' 8. '])
def test_relevance_reads_the_score_however_the_model_wraps_it(answer):
    # 31 Oct: a valid v13 brief ended in `no_score`; the reply limit was 20 tokens.
    assert article_scenes.relevance(answer) == 8
    assert article_scenes.judge_request(news(), {'scene': 'x'})['max_tokens'] >= 60


@pytest.mark.parametrize('answer', ['{"score": 100}', 'On a score of 0 to 10 this is fine', '{"score": null}', '8 or 9'])
def test_relevance_refuses_anything_that_is_not_a_clear_score(answer):
    with pytest.raises(article_scenes.SceneRejected) as rejected:
        article_scenes.relevance(answer)
    assert rejected.value.code == 'no_score'


@pytest.mark.parametrize('change,code', [
    (('in soft daylight.', 'in soft daylight ' + 'with warm morning tones ' * 16 + '.'), 'unsafe_length'),
    (('a photograph of an open', 'an open'), 'unsafe_description'),
    (('in soft daylight', 'in soft daylight in 1923'), 'unsafe_characters'),
    (('An open old notebook', 'An old man reading a notebook'), 'unsafe_word_man'),
    (('a fountain pen and a small red flag"', 'a fountain pen and a small red sign"'), 'unsafe_word_sign')])
def test_unsafe_rejection_names_the_rule_that_fired(change, code):
    with pytest.raises(article_scenes.SceneRejected) as rejected:
        article_scenes.parse(GOOD.replace(*change), news())
    assert rejected.value.code == code


def test_rejection_reason_and_score_reach_the_panel_stats(tmp_path, monkeypatch):
    # 30 Oct: two v12 scenes were rejected and nothing said why.
    verdicts = iter([article_scenes.SceneRejected('Generic interior scene', 'generic_interior'),
                     article_scenes.SceneRejected('Scene unrelated to the story', 'low_relevance', 4)])

    def fake_describe(session, account, token, item):
        verdict = next(verdicts, None)
        if verdict:
            raise verdict
        return {**article_scenes.parse(GOOD, item), 'relevance': 8}
    monkeypatch.setattr('seferihisar.illustrations.describe', fake_describe)
    monkeypatch.setattr(Illustrator, 'render', lambda self, prompt: jpeg())
    monkeypatch.setattr('seferihisar.illustrations.validate_described', lambda *args: None)
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        generator = illustrator(store, tmp_path, monkeypatch)
        generator.image(news(1, 'Fenomen köfteci anlamlı ziyaret 1'), True)
        generator.image(news(2, 'Fenomen köfteci anlamlı ziyaret 2'), True)
        stats = Illustrator(store, AT, tmp_path / 'images', session=Mock()).stats
        assert generator.stats['scene_rejections'] == {'generic_interior': 1, 'low_relevance': 1}
        assert generator.stats['scene_scores'] == [4] and stats['scene_rejections'] == {}
        later = illustrator(store, tmp_path, monkeypatch)
        assert later.image(news(3, 'Fenomen köfteci anlamlı ziyaret 3'), True) is not None
        assert later.stats['scene_scores'] == [8]


def test_living_room_brief_is_rejected_before_any_relevance_call():
    # The 30 Oct cards for Ethem amca and Yiğit were both this empty room.
    room = ('{"objects": ["sofa", "coffee table"], "scene": "A cozy living room with a sofa, a coffee table, a vase '
            'of pink flowers and sunlight through tall windows.", "description": "a photograph of a cozy living room"}')
    session, _ = model_session(room, room, '{"score": 9}')
    with pytest.raises(article_scenes.SceneRejected, match='Generic interior'):
        article_scenes.describe(session, ACCOUNT, 'test-token', news(title='Isparta’nın gururu Yiğit matematik olimpiyatında'))
    assert session.post.call_count == 2  # One varied retry, then no relevance call.


@pytest.mark.parametrize('clause', [', with no people or text', '. No people, text or logos are visible',
                                    ' without any signs', '; never a crowd'])
def test_wording_copied_from_the_rules_is_dropped_not_rendered(clause):
    # v12 counted "no people" as depicting people.
    brief = article_scenes.parse(GOOD.replace(' in soft daylight.', ' in soft daylight' + clause + '.'), news())
    assert brief['scene'] == json.loads(GOOD)['scene']
    with pytest.raises(article_scenes.SceneRejected):
        article_scenes.parse(GOOD.replace('in soft daylight', 'beside a crowd, with no text'), news())


def test_a_scene_over_the_old_length_limit_still_fits():
    long_scene = GOOD.replace('in soft daylight', 'in soft daylight ' + 'with warm morning tones ' * 11)
    assert len(json.loads(long_scene)['scene']) > 320
    article_scenes.parse(long_scene, news())


def test_rejected_draft_gets_one_varied_retry_but_a_refusal_does_not():
    bad = GOOD.replace('An open old notebook', 'An old man reading a notebook')
    session, _ = model_session(bad, GOOD, '{"score": 8}')
    assert article_scenes.describe(session, ACCOUNT, 'test-token', news())['relevance'] == 8
    temperatures = [call.kwargs['json']['temperature'] for call in session.post.call_args_list]
    assert temperatures == [0, article_scenes.RETRY_TEMPERATURE, 0]
    session, _ = model_session('{"scene": null}', GOOD, '{"score": 8}')
    with pytest.raises(article_scenes.SceneRejected) as rejected:
        article_scenes.describe(session, ACCOUNT, 'test-token', news())
    assert rejected.value.code == 'declined' and session.post.call_count == 1


def illustrator(store, tmp_path, monkeypatch):
    monkeypatch.setenv('ILLUSTRATIONS_ENABLED', 'true')
    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'test-token')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', ACCOUNT)
    monkeypatch.setattr('seferihisar.illustrations.ocr_available', lambda: True)
    monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration', validate_jpeg)
    return Illustrator(store, AT, tmp_path / 'images', session=Mock())


def test_unclassified_news_gets_one_described_scene_and_reuses_it(tmp_path, monkeypatch):
    calls = {'describe': 0, 'render': [], 'described': []}

    def fake_describe(session, account, token, item):
        calls['describe'] += 1
        return article_scenes.parse(GOOD, item)
    monkeypatch.setattr('seferihisar.illustrations.describe', fake_describe)
    monkeypatch.setattr(Illustrator, 'render', lambda self, prompt: calls['render'].append(prompt) or jpeg())
    monkeypatch.setattr('seferihisar.illustrations.validate_described',
                        lambda data, description: calls['described'].append(description))
    path = tmp_path / 'state.sqlite'
    with closing(Store(path)) as store:
        generator = illustrator(store, tmp_path, monkeypatch)
        assert generator.image(news(), True).read_bytes() == jpeg()
        stats = generator.stats
        assert stats['article_scene'] == stats['generated'] == stats['attempted'] == 1 and stats['text_only'] == 0
        prompt = calls['render'][0]
        assert 'fountain pen' in prompt and 'Ethem' not in prompt and 'şiir' not in prompt
        assert calls['described'] == ['a photograph of an open notebook, a fountain pen and a small red flag']
        assert store.rows('SELECT status,attempts FROM illustrations') == [{'status': 'ready', 'attempts': 1}]
        assert store.rows('SELECT attempts FROM illustration_days') == [{'attempts': 1}]
        validate_state(path)
    with closing(Store(path)) as store:
        fresh = illustrator(store, tmp_path, monkeypatch)
        assert fresh.image(news(), False).read_bytes() == jpeg()
        assert calls['describe'] == 1 and len(calls['render']) == 1 and fresh.stats['reused'] == 1


@pytest.mark.parametrize('failure', ['scene', 'text', 'match'])
def test_rejected_brief_or_pixels_never_become_a_cover(tmp_path, monkeypatch, failure):
    render = Mock(return_value=jpeg())
    monkeypatch.setattr(Illustrator, 'render', lambda self, prompt: render(prompt))
    monkeypatch.setattr('seferihisar.illustrations.describe',
                        Mock(side_effect=article_scenes.SceneRejected('unsafe')) if failure == 'scene'
                        else lambda session, account, token, item: article_scenes.parse(GOOD, item))
    monkeypatch.setattr('seferihisar.illustrations.validate_described',
                        Mock(side_effect=MatchRejected('mismatch')) if failure == 'match' else lambda *args: None)
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        generator = illustrator(store, tmp_path, monkeypatch)
        if failure == 'text':
            monkeypatch.setattr('seferihisar.illustrations.validate_text_free_illustration',
                                Mock(side_effect=IllustrationTextRejected()))
        assert generator.image(news(), True) is None
        assert store.rows('SELECT status,attempts,image FROM illustrations') == [
            {'status': 'failed', 'attempts': 2, 'image': None}]
        assert render.call_count == (0 if failure == 'scene' else 1)
        assert generator.stats['scene_rejected'] == int(failure == 'scene')
        # The same story is not retried with a new brief in a later run.
        assert Illustrator(store, AT, tmp_path / 'images', session=Mock()).image(news(), True) is None
        assert render.call_count == (0 if failure == 'scene' else 1)


def test_described_scenes_share_the_existing_run_and_daily_limits(tmp_path, monkeypatch):
    describe = Mock(side_effect=lambda session, account, token, item: article_scenes.parse(GOOD, item))
    monkeypatch.setattr('seferihisar.illustrations.describe', describe)
    monkeypatch.setattr(Illustrator, 'render', lambda self, prompt: jpeg())
    monkeypatch.setattr('seferihisar.illustrations.validate_described', lambda *args: None)
    with closing(Store(tmp_path / 'state.sqlite')) as store:
        generator = illustrator(store, tmp_path, monkeypatch)
        results = [generator.image(news(n, 'Fenomen köfteci anlamlı ziyaret ' + str(n)), True) for n in range(3)]
        assert [bool(r) for r in results] == [True, True, False] and describe.call_count == 2
        assert generator.stats['deferred'] == 1
    with closing(Store(tmp_path / 'full.sqlite')) as store:
        store.db.execute('INSERT INTO illustration_days VALUES(?,20)', ('2026-10-30',))
        store.db.commit()
        generator = illustrator(store, tmp_path, monkeypatch)
        assert generator.image(news(9), True) is None and describe.call_count == 2


def word(text, left=10, top=10, width=40, height=12, confidence=90):
    letters = ''.join(char for char in text if char.isalnum())
    return {'text': text, 'letters': letters, 'token': letters.casefold(), 'confidence': confidence,
            'box': {'left': left, 'top': top, 'width': width, 'height': height}}


def test_article_photo_allows_incidental_text_but_not_headline_graphics(monkeypatch):
    monkeypatch.setattr(shutil, 'which', lambda name: 'synthetic-ocr')
    data = jpeg()
    scans = {'words': [word('ECZANE')]}
    monkeypatch.setattr(image_safety, '_scan_words', lambda binary, image, mode: scans['words'])
    image_safety.validate_photo_not_text_graphic(data)
    for graphic in ([word(text, left=20 + 70 * index) for index, text in enumerate('Cumhuriyet coşkusu tüm Isparta sardı'.split())],
                    [word('1923')], [word('KUTLAMA', width=400, height=60)]):
        scans['words'] = graphic
        with pytest.raises(IllustrationTextRejected):
            image_safety.validate_photo_not_text_graphic(data)
    scans['words'] = []
    plain = {label: .1 for label in visual_match.PHOTO_LABELS}
    monkeypatch.setattr(visual_match, 'photo_scores', lambda images: [{**plain, 'people_together': .25}] * 3)
    assert visual_match.validate_news_photo(data, 'article_photo')['subject'] == 'article_photo'
    monkeypatch.setattr(visual_match, 'photo_scores', lambda images: [{**plain, 'real_scene': .25, 'flyer': .24}] * 3)
    with pytest.raises(MatchRejected):
        visual_match.validate_news_photo(data, 'article_photo')
    scans['words'] = [word('KUTLAMA', width=400, height=60)]
    with pytest.raises(MatchRejected):
        visual_match.validate_news_photo(data, 'article_photo')


def test_generated_scene_must_beat_people_and_graphic_alternatives(monkeypatch):
    data = jpeg()
    description = 'a photograph of an open notebook, a fountain pen and a small red flag'
    monkeypatch.setattr(visual_match, 'described_scores',
                        lambda images, labels: [[.29] + [.20] * (len(labels) - 1)] * 3)
    assert visual_match.validate_described(data, description)['subject'] == description
    distractors = visual_match.SCENE_DISTRACTORS
    portrait = [.29] + [.285 if label == 'a portrait photograph of a person' else .20 for label in distractors]
    lanterns = [.29] + [.30 if 'lanterns' in label else .20 for label in distractors]
    for row in ([.23] + [.10] * len(distractors), portrait, lanterns):
        monkeypatch.setattr(visual_match, 'described_scores', lambda images, labels, row=row: [row] * 3)
        with pytest.raises(MatchRejected):
            visual_match.validate_described(data, description)


def test_scene_decorations_must_suit_a_turkish_setting():
    from seferihisar.illustrations import article_prompt
    item = news(title='Cumhuriyet Bayramı Coşkuyla Kutlandı')
    assert 'paper lanterns' in article_scenes.SYSTEM
    assert 'no paper lanterns or East Asian ornaments' in article_prompt('A plain red flag on a pole.')
    flags = ('{"objects": ["red flag", "flag pole"], "scene": "Several plain red flags with a white crescent and star '
             'waving on poles under a clear autumn sky.", "description": "a photograph of red flags with a white crescent and star"}')
    assert article_scenes.parse(flags, item)['description'].startswith('a photograph of red flags')
    for bad in (flags.replace('waving on poles', 'beside hanging red paper lanterns'),
                flags.replace('under a clear', 'near a pagoda under a clear'),
                flags.replace('Several plain', 'Several Chinese style')):
        with pytest.raises(article_scenes.SceneRejected):
            article_scenes.parse(bad, item)
    # A new brief version: cached v11 scenes are not reused for prepared posts.
    assert article_scenes.VERSION == 'editorial-article-scene-v14'
