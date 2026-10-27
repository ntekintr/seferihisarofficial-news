import io
from contextlib import closing
from copy import deepcopy
from PIL import Image
import pytest
from seferihisar.domain import digest,parse_date
from seferihisar.editor import editorial_category,headline,caption
from seferihisar.source_photos import cleaned_photo,news_subject
from seferihisar.visual_subject import subject
from seferihisar.illustrations import image_key
from seferihisar.store import Store
from test_editorial_stock import manager,item

@pytest.mark.parametrize('title',[
    'HÜDA PAR Isparta İl Başkanı Salih Demir’den Yeni Müftüye Ziyaret',
    'İl Müftüsüne ziyaret', 'Valiye ziyaret', 'Kaymakama ziyaret',
])
def test_official_recipient_visit_has_meeting_visual(title):
    row={'kind':'news','category':'news','title':title}
    assert subject(row)=='meeting_room' and news_subject(row)=='meeting'

@pytest.mark.parametrize('title',[
    'Vali antik kenti ziyaret etti','Başkan tarihi müzeyi ziyaret etti',
    'Müftü ziyaret saatlerini açıkladı','Müftüye ziyaret yarın yapılacak',
])
def test_title_alone_does_not_invent_a_meeting_photo(title):
    assert news_subject({'kind':'news','category':'news','title':title}) is None

@pytest.mark.parametrize('orientation',[0,1,2,3,4,5,6,7,8,9])
def test_undefined_orientation_is_upright_but_rotations_remain_rejected(orientation):
    image=Image.new('RGB',(960,540),'#567890');exif=image.getexif();exif[274]=orientation
    buffer=io.BytesIO();image.save(buffer,format='JPEG',exif=exif)
    if orientation not in (0,1):
        with pytest.raises(ValueError):cleaned_photo(buffer.getvalue())
    else:
        cleaned=cleaned_photo(buffer.getvalue())
        with Image.open(io.BytesIO(cleaned)) as result:
            assert result.width>result.height and result.getexif().get(274,1)==1
        exif[274]=1;other=io.BytesIO();image.save(other,format='JPEG',exif=exif)
        assert cleaned==cleaned_photo(other.getvalue())

@pytest.mark.parametrize('status',['published','publishing','uncertain'])
@pytest.mark.parametrize('ready',[False,True])
def test_pruning_never_removes_claimed_image_or_failed_binding(tmp_path,monkeypatch,status,ready):
    with closing(Store(tmp_path/'state.sqlite')) as store:
        row=item();key=image_key(row);generator=manager(store,tmp_path,monkeypatch)
        pixels=generator.image(row,True).read_bytes() if ready else None
        if not ready:
            store.db.execute('INSERT INTO illustrations VALUES(?,?,?,NULL,?,?,?)',
                (key,row['id'],'failed',2,'2026-10-12T00:00:00+00:00','2026-10-12T00:00:00+00:00'))
        store.queue({'id':digest('frozen'),'item_id':row['id'],'revision':1,'kind':'announcement',
                     'due_at':'2026-10-12T08:30:00+03:00','illustration_keys':{'0':key}})
        store.db.execute('UPDATE posts SET status=?',(status,));store.db.commit()
        before=store.rows('SELECT * FROM illustrations');claims=store.rows('SELECT * FROM posts')
        monkeypatch.setattr('seferihisar.illustrations.MAX_CACHE_BYTES',0)
        generator.prune(set())
        assert store.rows('SELECT * FROM illustrations')==before
        assert store.rows('SELECT * FROM posts')==claims

def test_meeting_does_not_become_festival_when_body_mentions_one():
    row={'kind':'news','category':'festival','title':'Serdar Kısaağa, yatırımlar için Cemil Tugay ile bir araya geldi',
         'description':'İzmir Kültür Yolu Festivali kapsamında görüşüldü.',
         'source_name':'Kaynak','url':'https://example.com/news'}
    before=deepcopy(row)
    assert editorial_category(row)=='news'
    title=headline(row,'news');assert title.startswith('Yerel Haberler:')
    assert '#festival' not in caption(row,title)
    assert row==before
    assert editorial_category({**row,'kind':'event'})=='festival'

def test_pending_category_refresh_preserves_all_frozen_claims(tmp_path):
    from seferihisar.schedule import queue_item
    at=parse_date('2026-10-27T02:00:00+03:00')
    row={'id':digest('meeting'),'revision':1,'kind':'news','category':'festival',
         'title':'Başkanlar bir araya geldi','description':'Festival kapsamında görüşüldü.',
         'source_name':'Kaynak','url':'https://example.com/news','sources':['https://example.com/news']}
    with closing(Store(tmp_path/'state.sqlite')) as store:
        queue_item(store,row,'news',at,at)
        p=store.posts()[0];assert p['category']=='news' and p['title'].startswith('Yerel Haberler:')
        for status in ('published','publishing','uncertain'):
            store.db.execute('UPDATE posts SET status=?',(status,));store.db.commit()
            before=store.rows('SELECT * FROM posts');queue_item(store,row,'news',at,at)
            assert store.rows('SELECT * FROM posts')==before


@pytest.mark.skipif(__import__('os').getenv('RUN_VISUAL_NATIVE')!='true',reason='Native source photo and headline checks')
def test_actual_exif_zero_source_photo_format_is_valid_but_model_rejection_stays_closed():
    from pathlib import Path
    from seferihisar.visual_match import validate_news_photo,validate_headline_photo,MatchRejected
    raw=Path('tests/fixtures/visual-followup/official-visit-exif-zero.jpg').read_bytes()
    data=cleaned_photo(raw)
    # This reviewed publisher graphic does not pass the pinned automatic model.
    # Format support is not subject approval; generic meeting stock remains available.
    with pytest.raises(MatchRejected):
        validate_news_photo(data,'meeting')
    with pytest.raises(MatchRejected):
        validate_headline_photo(data,'meeting','HÜDA PAR Isparta İl Başkanı Salih Demir’den Yeni Müftüye Ziyaret')
