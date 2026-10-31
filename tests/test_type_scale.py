from PIL import ImageFont
import pytest

from seferihisar import editorial_render
from seferihisar.card_layout import FITTED, VERSION, fixed_scale
from seferihisar.editorial_render import FITTED_SCALE, SCALE, TextFields, editorial_card
from seferihisar.render import ASSETS, render_post


def roles(monkeypatch):
    seen = {}
    original = TextFields.line

    def spy(self, value, x, y, size, color, role, box, bold=False):
        seen.setdefault(role, set()).add(size)
        return original(self, value, x, y, size, color, role, box, bold)
    monkeypatch.setattr(TextFields, 'line', spy)
    return seen


CARDS = [
    ('Urla’da planlı elektrik kesintisi', '31.10.2026 · 07:00 – 13:00\n\nUrla · Birgi'),
    ('Orhanlı Köyü 3.Erkence Zeytin Festivali', '31.10.2026 – 01.11.2026 · Saat açıklanmadı\n\nOrhanlı Köyü Piknik Alanı'),
    ('Ozbi Konseri', '04.11.2026 · 21:30\n\nIsparta Holly Stone\n\nÜcret: 900 TL'),
]


@pytest.mark.parametrize('story', [False, True])
def test_every_event_card_uses_the_same_size_for_each_role(tmp_path, monkeypatch, story):
    seen = roles(monkeypatch)
    for index, (title, body) in enumerate(CARDS):
        editorial_card(title, body, 'festival', tmp_path/f'{index}.jpg', story=story, event_details=True,
                       caption_note=True, illustration=photo(tmp_path))
    assert seen['heading'] == {52} and seen['date'] == {34} and seen['details'] == {30}
    assert seen['note'] == {26} and seen['category'] == {28}
    assert seen['brand'] == {34, 24} and seen['handle'] == {23}


def photo(tmp_path):
    from PIL import Image
    path = tmp_path/'photo.jpg'
    Image.new('RGB', (1080, 600), '#335577').save(path)
    return path


def test_news_and_event_body_text_match(tmp_path, monkeypatch):
    seen = roles(monkeypatch)
    editorial_card('Seferihisar’da yeni park açıldı', 'Yeni park mahalle sakinlerinin kullanımına açıldı.', 'news',
                   tmp_path/'news.jpg', illustration=photo(tmp_path))
    assert seen['summary'] == set(SCALE['summary']) == set(SCALE['details'])


def test_only_a_headline_that_cannot_fit_steps_down_once(tmp_path, monkeypatch):
    seen = roles(monkeypatch)
    title = 'Seferihisar Belediye Meclisi yeni meydan düzenlemesi için ek bütçe ayırdı ve ihaleye çıkıyor'
    editorial_card(title, 'Ayrıntılar açıklandı.', 'news', tmp_path/'long.jpg', illustration=photo(tmp_path))
    assert seen['heading'] == {44}


def test_long_summary_keeps_its_size_and_shows_an_ellipsis(tmp_path, monkeypatch):
    seen = roles(monkeypatch)
    editorial_card('Kısa başlık', 'Uzun özet metni kartın alanını aşacak kadar sürer. ' * 12, 'news',
                   tmp_path/'long.jpg', illustration=photo(tmp_path))
    assert seen['summary'] == {30}


def test_claimed_first_version_card_keeps_its_published_fitting(tmp_path, monkeypatch):
    seen = roles(monkeypatch)
    post = {'id': 'a'*24, 'kind': 'news', 'status': 'published', 'category': 'news', 'card_layout': FITTED,
            'title': 'Kısa', 'slides': [{'title': 'Kısa başlık', 'body': 'Kısa özet metni burada duruyor.'}]}
    assert fixed_scale(post) is False
    render_post(post, tmp_path)
    assert seen['heading'] == {FITTED_SCALE['heading'][0]}


def test_new_layout_is_the_default_for_unclaimed_cards():
    assert fixed_scale({'card_layout': VERSION}) and fixed_scale({})


@pytest.mark.parametrize('name', ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'])
def test_bundled_typeface_draws_turkish_text(name):
    face = ImageFont.truetype(str(ASSETS/'fonts'/name), 40)
    assert face.getname()[0] == 'DejaVu Sans'
    editorial_render.ensure_glyphs('SEFERİHİSAR ığüşöçİĞÜŞÖÇ', face)
