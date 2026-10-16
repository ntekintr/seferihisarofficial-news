import json
from copy import deepcopy
from datetime import timedelta

import pytest

from seferihisar.editor import caption, headline, news_body, news_title
from seferihisar.schedule import queue_item, slide_body


@pytest.fixture
def course_notice(at):
    introduction = ('Halk eğitimi merkezimize gelen talepler çerçevesinde açmayı planladığımız '
                    '" Dekoratif Ev Aksesuarları Hazırlama Kursu " ile " Tığ Örücülüğü Kursu " '
                    'ile ilgili ayrıntılı bilgi için lütfen tıklayınız.')
    return {
        'kind': 'news', 'category': 'culture', 'source_id': 'seferihisar-hem',
        'source_name': 'Seferihisar Atatürk Halk Eğitimi Merkezi',
        'title': 'Yeni Başlayacak El Sanatları Kurslarımıza Kayıtlarımız Devam Ediyor',
        'description': introduction + ' ' + introduction + ' ' +
            'Kursların; gün, saat, yer ve başlama tarihleri ile ilgili bilgiler aşağıdaki kurs afişimizde yer almaktadır. '
            'Açılacak kurslarımıza kayıt devam etmekte olup kurslarımıza kayıtlar Bakanlığımız e-Yaygın Eğitim Sistemi üzerinden yapılmaktadır. '
            '"Başka kurs" hakkında bilgi almak için lütfen TIKLAYINIZ.',
        'published_at': at.isoformat(),
        'url': 'https://seferihisarhem.meb.k12.tr/icerikler/kurslar_17746870.html',
        'sources': ['https://seferihisarhem.meb.k12.tr/icerikler/kurslar_17746870.html'],
    }


def test_reviewed_course_notice_is_concise_neutral_and_preserves_planned_status(course_notice):
    original = deepcopy(course_notice)
    assert news_title(course_notice) == 'El sanatları kurslarına kayıtlar sürüyor'
    description = news_body(course_notice)
    assert description == ('Seferihisar Atatürk Halk Eğitimi Merkezi, “Dekoratif Ev Aksesuarları Hazırlama” '
                           've “Tığ Örücülüğü” kurslarını açmayı planlıyor. Kurslara kayıtlar sürüyor.')
    assert len(description) < 300
    assert 'tıkla' not in description.lower() and 'Başka kurs' not in description
    assert 'açıldı' not in description and 'ücretsiz' not in description
    assert '10.10.2026' not in description and 'saat' not in description
    assert course_notice == original


def test_course_names_are_only_extracted_from_same_planned_sentence(course_notice):
    course_notice['description'] = (
        '"Farklı eğitim Kursu" geçmiş duyuruda yer alıyor. '
        'Talepler çerçevesinde açmayı planladığımız “Tığ Örücülüğü Kursu” için duyuru yapıldı. '
        '"Dekoratif Ev Aksesuarları Hazırlama Kursu" başka bir duyuruda yer alıyor.')
    description = news_body(course_notice)
    assert '“Tığ Örücülüğü”' in description
    assert 'Farklı eğitim' not in description and 'Dekoratif' not in description


def test_unrecognized_course_names_or_registration_status_are_not_inferred(course_notice):
    course_notice['description'] = 'Açmayı planladığımız "Başka bir şey" için talepler alınıyor.'
    assert course_notice['description'] in news_body(course_notice)
    assert news_body(course_notice).startswith('Kaynak açıklamasında “')
    course_notice['title'] = 'El Sanatları Kurslarımız İçin Talepler Alınıyor'
    course_notice['description'] = 'Açmayı planladığımız "Tığ Örücülüğü Kursu" için talepler alınıyor.'
    assert course_notice['description'] in news_body(course_notice)
    assert 'kayıtlar sürüyor' not in news_title(course_notice)


def test_source_specific_neutral_wording_does_not_apply_to_unreviewed_sources(course_notice):
    course_notice['source_id'] = 'other'
    assert news_title(course_notice) == 'Kaynak duyurusu: “'+course_notice['title']+'”'
    assert 'açmayı planladığımız' in news_body(course_notice)


def test_exact_repeated_news_sentences_and_standalone_ui_call_to_action_are_removed(course_notice):
    course_notice['source_id'] = 'other'
    sentence = 'Seferihisar Halk Eğitimi Merkezi tarafından yeni kursların açılması planlanıyor.'
    course_notice['description'] = sentence + ' Başvurular sürüyor. ' + sentence + ' Ayrıntılı bilgi için lütfen tıklayınız.'
    assert news_body(course_notice) == sentence + ' Başvurular sürüyor.'


def test_repeated_short_abbreviations_and_numbered_facts_are_preserved(course_notice):
    course_notice['source_id'] = 'other'
    course_notice['description'] = 'Adresler: No. 5. No. 8. Dr. A. Dr. B. aynı duyuruda yer alıyor.'
    assert news_body(course_notice) == course_notice['description']


def test_matching_rss_syndication_credit_is_only_in_caption_footer(course_notice):
    course_notice.update(source_id='other', title='Yeni kurslar', source_name='Yerel Gazete',
                         description='Yeni kurslar için kayıtlar sürüyor. Yeni kurslar yazısı ilk önce Yerel Gazete üzerinde ortaya çıktı.')
    assert news_body(course_notice) == 'Yeni kurslar için kayıtlar sürüyor.'
    assert 'Yerel Gazete' not in slide_body(course_notice)
    content = caption(course_notice, headline(course_notice, 'news'))
    assert 'Kaynak: Yerel Gazete\n' + course_notice['url'] in content
    assert 'üzerinde ortaya çıktı' not in content
    course_notice['description'] = 'Yerel Gazete, açılacak kursları araştırdı.'
    assert news_body(course_notice) == course_notice['description']


def test_course_caption_and_card_use_same_news_wording_with_source_attribution(course_notice):
    title = headline(course_notice, 'news')
    content = caption(course_notice, title)
    body = slide_body(course_notice)
    assert title == 'Kültür & Sanat: El sanatları kurslarına kayıtlar sürüyor'
    assert content.count('El sanatları kurslarına kayıtlar sürüyor') == 1
    assert news_body(course_notice) in body and news_body(course_notice) in content
    assert 'Kaynak duyurusuna göre: ' in content
    assert 'Kaynak duyurusundan: “' not in content
    assert course_notice['url'] in content
    assert 'Kaynak: ' not in body
    assert 'Kaynak: ' + course_notice['source_name'] in content
    assert course_notice['title'] not in content and 'tıklayınız' not in content


@pytest.mark.parametrize('status', ['prepared', 'blocked_source'])
def test_only_unclaimed_news_wording_refreshes_and_keeps_source_identity_and_image_binding(
        store, course_notice, at, status):
    store.upsert(course_notice, at.isoformat())
    item = store.items()[0]
    source_row = store.rows('SELECT * FROM items')[0]
    queue_item(store, item, 'news', at, at)
    post = store.posts()[0]
    payload = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    payload.update(title=course_notice['title'], caption=course_notice['description'],
                   slides=[{'title': course_notice['title'], 'body': course_notice['description']}],
                   illustration_keys={'0': 'f' * 24})
    with store.db:
        store.db.execute('UPDATE posts SET payload=?,status=? WHERE id=?', (json.dumps(payload), status, post['id']))
    queue_item(store, item, 'news', at + timedelta(hours=1), at + timedelta(minutes=15))
    refreshed = store.posts()[0]
    assert refreshed['id'] == post['id'] and refreshed['revision'] == item['revision']
    assert refreshed['due_at'] == at.isoformat() and refreshed['created_at'] == at.isoformat()
    assert refreshed['status'] == status
    assert refreshed['illustration_keys'] == {'0': 'f' * 24}
    assert 'Görsel: yapay zekâyla hazırlanmış temsili görsel.' not in refreshed['caption']
    assert 'El sanatları kurslarına kayıtlar sürüyor' in refreshed['title']
    assert refreshed['slides'][0]['body'] == slide_body(item)
    assert store.rows('SELECT * FROM items')[0] == source_row


@pytest.mark.parametrize('status', ['published', 'publishing', 'uncertain'])
def test_claimed_news_payload_and_media_are_frozen(store, course_notice, at, status):
    store.upsert(course_notice, at.isoformat())
    item = store.items()[0]
    queue_item(store, item, 'news', at, at)
    post = store.posts()[0]
    payload = json.loads(store.rows('SELECT payload FROM posts WHERE id=?', (post['id'],))[0]['payload'])
    payload.update(title=course_notice['title'], caption=course_notice['description'],
                   slides=[{'title': course_notice['title'], 'body': course_notice['description']}],
                   illustration_keys={'0': 'f' * 24})
    with store.db:
        store.db.execute('UPDATE posts SET payload=?,status=?,container_id=?,media_id=? WHERE id=?',
                         (json.dumps(payload), status, 'test-container', 'test-media', post['id']))
    original = store.rows('SELECT * FROM posts WHERE id=?', (post['id'],))[0]
    queue_item(store, item, 'news', at + timedelta(hours=1), at + timedelta(minutes=15))
    assert store.rows('SELECT * FROM posts WHERE id=?', (post['id'],))[0] == original

