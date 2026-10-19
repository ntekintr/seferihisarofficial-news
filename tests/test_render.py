from pathlib import Path

from PIL import Image, ImageDraw, ImageChops
import pytest

from seferihisar import render


def record_text(monkeypatch):
    observed = []
    original = ImageDraw.ImageDraw.text

    def track(draw, xy, text, **kwargs):
        if text:
            observed.append((text, draw.textbbox(xy, text, font=kwargs['font'], anchor=kwargs.get('anchor'))))
        return original(draw, xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, 'text', track)
    return observed


@pytest.mark.parametrize('story', [False, True])
def test_long_content_omits_legacy_attribution_and_keeps_text_inside_safe_area(tmp_path, monkeypatch, story):
    observed = record_text(monkeypatch)
    render.card('Seferihisar kültür ve sanat ' * 30,
                'Etkinlik duyurusundan alınan açıklama ' * 100 + '\n\nKaynak: Seferihisar Belediyesi',
                'event', tmp_path / 'card.jpg', story=story, index='1/2')
    assert not any('Kaynak' in text or 'Seferihisar Belediyesi' in text for text, _ in observed)
    assert any(text == '@seferihisarofficial' for text, _ in observed)
    assert any(text.endswith('…') for text, _ in observed)
    for _, (left, top, right, bottom) in observed:
        assert 0 <= left < right <= 1080
        assert (260 if story else 0) <= top < bottom <= (1600 if story else 1260)


def test_distinct_illustrations_do_not_change_logo_or_brand_strips(tmp_path, monkeypatch):
    observed = record_text(monkeypatch)
    for name, color in [('music', '#ce6b23'), ('weather', '#5ba3ac')]:
        source = tmp_path / (name + '.png')
        Image.new('RGB', (1600, 900), color).save(source)
        render.card('Örnek başlık', 'Örnek açıklama', 'news', tmp_path / (name + '.jpg'), illustration=source)
    with Image.open(tmp_path / 'music.jpg') as first, Image.open(tmp_path / 'weather.jpg') as second:
        assert first.size == second.size == (1080, 1350)
        assert ImageChops.difference(first.crop((0, 0, 1080, 128)), second.crop((0, 0, 1080, 128))).getbbox() is None
        assert ImageChops.difference(first.crop((0, 180, 1080, 440)), second.crop((0, 180, 1080, 440))).getbbox()
    assert 'Temsili çizim' not in [text for text, _ in observed]


def test_missing_illustration_does_not_claim_a_scene_or_ai_image(tmp_path, monkeypatch):
    observed = record_text(monkeypatch)
    render.card('Örnek başlık', 'Örnek açıklama', 'news', tmp_path / 'card.jpg')
    assert 'Temsili çizim' not in [text for text, _ in observed]


def test_illustration_is_assigned_to_its_slide_only(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(render, 'card', lambda *args, **kwargs: calls.append(kwargs.get('illustration')))
    post = {'id': 'a' * 24, 'kind': 'announcement', 'category': 'event',
            'slides': [{'title': 'Seferihisar örnek etkinliği', 'body': 'Açıklama'}],
            'source_urls': ['https://seferihisar.bel.tr/etkinlik']}
    selected = Path('only-this-item.png')
    assets = render.render_post(post, tmp_path, {0: selected})
    assert calls == [selected, selected]
    assert len(assets['feed']) == len(assets['story']) == 1


def test_turkish_uppercase_keeps_dotted_i():
    assert render.upper_tr('Seferihisar’ın gündemi') == 'SEFERİHİSAR’IN GÜNDEMİ'


@pytest.mark.parametrize('kind', ['news', 'announcement', 'reminder_3d', 'reminder_day',
                                 'update', 'cancellation', 'weekly', 'monthly'])
def test_every_feed_story_and_carousel_frame_omits_source_attribution(tmp_path, monkeypatch, kind):
    observed = record_text(monkeypatch)
    body = '14.10.2026 · 20:00\n\nUrla kültür merkezi\n\nKaynak: KaynakKurumu\nhttps://example.org/duyuru'
    post = {'id': 'a' * 24, 'kind': kind, 'category': 'theatre',
            'slides': [{'title': 'Hafifletici Sebepler', 'body': body}],
            'source_urls': ['https://example.org/duyuru']}
    if kind in ('weekly', 'monthly'):
        post['slides'].insert(0, {'title': 'Etkinlik takvimi', 'body': 'Bu haftanın etkinlikleri'})
    assets = render.render_post(post, tmp_path)
    text = '\n'.join(value for value, _ in observed)
    assert 'Kaynak' not in text and 'KaynakKurumu' not in text
    assert 'https://' not in text and 'example.org' not in text
    assert '@seferihisarofficial' in text and 'Urla kültür merkezi' in text
    assert len(assets['feed']) == len(assets['story'])


def test_legacy_source_filter_keeps_following_content():
    assert render.graphic_body('Bilgi\n\n Kaynak: Kurum\nhttps://example.org/1\n\nDevam eden haber') == 'Bilgi\n\nDevam eden haber'


def test_legacy_graphic_omits_matching_rss_credit_without_changing_news_facts(tmp_path, monkeypatch):
    observed = record_text(monkeypatch)
    render.card('Belediye: Yeni proje',
                'Belediye projeyi onayladı. Yeni proje yazısı ilk önce YerelGazete üzerinde ortaya çıktı.\n\nKaynak: YerelGazete',
                'municipality', tmp_path / 'legacy.jpg')
    text = '\n'.join(value for value, _ in observed)
    assert 'Belediye projeyi onayladı.' in text
    assert 'YerelGazete' not in text and 'ortaya çıktı' not in text

