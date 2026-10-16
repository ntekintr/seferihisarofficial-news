from copy import deepcopy
import json

import pytest

from seferihisar.editor import caption, headline, news_body, news_title
from seferihisar.editorial_voice import neutral_body, neutral_title, source_voice
from seferihisar.schedule import queue_item, slide_body


def party_notice(at):
    return {'kind':'news','category':'news','source_id':'instagram-life','source_name':'SeferihisarLife Instagram',
            'url':'https://www.instagram.com/p/example/','sources':['https://www.instagram.com/p/example/'],
            'published_at':at.isoformat(),
            'title':'AK Parti Seferihisar İlçe Başkanı Serdar Kısaağa, 23 Mahalle Muhtarıyla Bir Araya Geldi',
            'description':('AK Parti Seferihisar İlçe Başkanımız Sayın Serdar Kısaağa, ilçemizde görev yapan '
                           '23 mahalle muhtarımızla bir araya gelerek mahallelerimizin ihtiyaçlarını ve '
                           'vatandaşlarımızdan gelen talepleri dinledi. '
                           "Seferihisar'ımızın tüm mahalleleri için omuz omuza çalışmaya, sorunların takipçisi olmaya devam edeceğiz! 🌟")}


def test_real_party_source_uses_news_voice_without_changing_names_numbers_or_provenance(at):
    item=party_notice(at);before=deepcopy(item)
    body=news_body(item)
    assert body==('AK Parti Seferihisar İlçe Başkanı Serdar Kısaağa, ilçede görev yapan '
                  '23 mahalle muhtarıyla bir araya gelerek mahallelerin ihtiyaçlarını ve '
                  'vatandaşlardan gelen talepleri dinledi.')
    # The actual source uses "23 mahalle muhtarımızla"; do not invent a new
    # actor, affiliation, meeting date, claim of endorsement, or outcome.
    assert not source_voice(body) and 'Sayın' not in body
    assert '23' in body and 'Serdar Kısaağa' in body and 'AK Parti' in body
    assert 'omuz omuza' not in body and 'devam edeceğiz' not in body
    content=caption(item,headline(item,'news'))
    assert body in content and 'Kaynak: SeferihisarLife Instagram\n'+item['url'] in content
    assert 'Başkanımız' not in content and 'Sayın' not in content
    assert 'AK Parti' in slide_body(item) and 'Başkanımız' not in slide_body(item)
    assert item==before


@pytest.mark.parametrize('role,expected',[
    ('İlçe Başkanımız Sayın Ali Kaya','İlçe Başkanı Ali Kaya'),
    ('Başkanımız Sayın Ali Kaya','Başkan Ali Kaya'),
    ('Belediyemizde toplantı','Belediyede toplantı'),
    ('İLÇEMİZDE TOPLANTI','İLÇEDE TOPLANTI'),
    ('Hastanemizin açıklaması','Hastanenin açıklaması'),
])
def test_same_neutral_roles_apply_to_all_sources(role,expected):
    assert neutral_title(role)==expected


def test_unknown_first_person_statement_is_explicitly_attributed_not_rewritten_as_fact():
    original='Yarın ücretsiz servis başlatacağız.'
    assert neutral_body(original)=='Kaynak açıklamasında “'+original+'” denildi.'
    assert neutral_title(original)=='Kaynak duyurusu: “'+original+'”'
    assert not source_voice(neutral_body(original))


def test_existing_direct_quotes_and_multi_sentence_quotes_stay_verbatim():
    original='Başkan, “Belediyemizde buluştuk. Talepleri dinledik.” dedi. Başvurular 21 Ekim’de bitecek.'
    assert neutral_body(original)==original
    assert neutral_title('“Başkanımız” adlı tiyatro oyunu')=='“Başkanımız” adlı tiyatro oyunu'
    assert neutral_title('Sayın Yargıç adlı tiyatro oyunu Seferihisar’da')=='Sayın Yargıç adlı tiyatro oyunu Seferihisar’da'
    event={'kind':'event','title':'Belediyemiz adlı tiyatro oyunu'}
    assert news_title(event)==event['title']


def test_campaign_filter_does_not_remove_a_specific_commitment():
    original='Omuz omuza çalışmaya devam edeceğiz ve 21 Ekim’de yeni hizmet sunacağız.'
    assert original in neutral_body(original)
    assert neutral_body(original).startswith('Kaynak açıklamasında “')


@pytest.mark.parametrize('status',['prepared','blocked_source','published','publishing','uncertain'])
def test_neutral_copy_changes_only_unclaimed_rows(store,at,status):
    item=party_notice(at);store.upsert(item,at.isoformat());item=store.items()[0]
    queue_item(store,item,'news',at,at)
    row=store.rows('SELECT * FROM posts')[0]
    legacy=json.loads(row['payload'])
    legacy.update(caption=item['description'],slides=[{'title':item['title'],'body':item['description']}])
    with store.db:
        store.db.execute('UPDATE posts SET status=?,payload=?',(status,json.dumps(legacy)))
    before=store.rows('SELECT * FROM posts')[0]
    queue_item(store,item,'news',at,at)
    if status in ('published','publishing','uncertain'):
        assert store.rows('SELECT * FROM posts')[0]==before
    else:
        assert 'Başkanımız' not in store.posts()[0]['caption']
