import re
from copy import deepcopy

import pytest

from seferihisar.editor import caption, caption_with_hashtags, digest_hashtags, hashtags, headline
from seferihisar.schedule import prepare


def test_theatre_tags_are_lowercase_local_and_do_not_invent_a_genre(event):
    event.update(title="Hafifletici Sebepler", category="theatre",
                 location="Urla Belediyesi Atatürk Kültür Merkezi", description="Tiyatro oyunu duyurusu.")
    original = deepcopy(event)
    assert hashtags(event) == ["#urla", "#tiyatro", "#tiyatrooyunu", "#etkinlik", "#seferihisarofficial"]
    assert "#komedi" not in hashtags(event)
    assert event == original


def test_location_precedes_other_real_mentions_and_source_hashtags_do_not_supply_a_location(event):
    event.update(title="Urla'da konser #SEFERİHİSAR #Keşfet", category="concert",
                 location="Güzelbahçe Yelki", description="Özdere'deki dinleyicilere duyuru. #viral #fyp")
    tags = hashtags(event)
    assert tags == ["#guzelbahce", "#yelki", "#konser", "#canlimuzik", "#seferihisarofficial"]
    content = caption(event, headline(event, "announcement"))
    assert content.endswith(" ".join(tags))
    assert "#SEFERİHİSAR" not in content
    assert "#Keşfet" not in content
    assert "#viral" not in content
    assert "#fyp" not in content


@pytest.mark.parametrize("place,expected", [
    ("Sığacık", "#sigacik"), ("Ürkmez", "#urkmez"), ("Güzelbahçe", "#guzelbahce"),
    ("Özdere", "#ozdere"), ("Seferihisar", "#seferihisar"),
])
def test_turkish_location_names_use_readable_lowercase_ascii(event, place, expected):
    event.update(location=place, title="Etkinlik", description="", category="event")
    assert hashtags(event)[0] == expected
    assert all(re.fullmatch(r"#[a-z0-9_]+", tag) for tag in hashtags(event))


def test_a_place_inside_a_larger_word_is_not_a_location(event):
    event.update(title="Buralarda kültür", location=None, description="Yelkili tekne", category="culture")
    assert not any(tag in hashtags(event) for tag in ("#urla", "#yelki"))


def test_source_links_and_attached_campaign_tags_do_not_supply_topic_or_place(event):
    event.update(title="Duyuru#FYP", location="Urla", category="transport",
                 description="Ayrıntı: https://example.org/seferihisar/yol-calismasi#program #Yelki")
    assert hashtags(event) == ["#urla", "#ulasim", "#trafik", "#kamuduyurusu", "#seferihisarofficial"]
    content = caption(event, headline(event, "announcement"))
    assert "#FYP" not in content and "#Yelki" not in content
    assert "https://example.org/seferihisar/yol-calismasi#program" in content


def test_traffic_roadwork_tag_requires_an_actual_roadwork_cue(event):
    event.update(kind="news", title="Seferihisar ulaşım duyurusu", category="transport",
                 location="Seferihisar", description="Otobüs güzergâhı güncellendi.")
    assert hashtags(event) == ["#seferihisar", "#ulasim", "#trafik", "#yerelhaber", "#seferihisarofficial"]
    event["description"] = "Yol çalışması nedeniyle trafik düzenlemesi yapıldı."
    assert hashtags(event) == ["#seferihisar", "#ulasim", "#yolcalismasi", "#trafik", "#seferihisarofficial"]


def test_news_about_a_theatre_building_does_not_promise_a_performance(event):
    event.update(kind="news", category="theatre", title="Urla tiyatro salonu yenilendi",
                 location="Urla", description="Bina yenileme çalışmaları tamamlandı.")
    assert "#tiyatro" in hashtags(event)
    assert "#tiyatrooyunu" not in hashtags(event)


def test_caption_reserves_complete_source_url_and_hashtags_before_trimming(event):
    event.update(title="Urla " + "duyuru " * 500, location="Urla", description="Açıklama " * 300,
                 category="theatre", source_name="İzmir Art", url="https://www.izmir.art/etkinlik/123#program")
    content = caption(event, headline(event, "announcement"))
    assert len(content) <= 2200
    assert "Kaynak: İzmir Art\n" + event["url"] in content
    assert content.endswith("#urla #tiyatro #tiyatrooyunu #etkinlik #seferihisarofficial")
    assert "#program" in content  # Preserve the canonical source URL fragment.


def test_caption_formatter_never_outputs_partial_or_invalid_footer_tags():
    content = caption_with_hashtags("Uzun açıklama " * 300,
                                    ["#urla", "#konser", "#CANLIMUZIK", "#urla", "#seferihisarofficial"])
    assert len(content) <= 2200
    assert content.endswith("#urla #konser #seferihisarofficial")


def test_calendar_tags_include_selected_category_diversity_without_repetition(event):
    theatre = {**event, "category": "theatre", "location": "Urla", "title": "Oyun", "description": ""}
    festival = {**event, "category": "festival", "location": "Ürkmez Seferihisar", "title": "Festival", "description": ""}
    assert digest_hashtags([theatre, festival]) == ["#urla", "#urkmez", "#tiyatro", "#festival", "#seferihisarofficial"]


def test_weekly_and_monthly_caption_have_contextual_footer(store, event, at):
    event.update(title="Hafifletici Sebepler", category="theatre", location="Urla", description="")
    store.upsert(event, at.isoformat())
    prepare(store, at)
    for post in store.posts():
        if post["kind"] in ("weekly", "monthly"):
            assert post["caption"].endswith("#urla #tiyatro #tiyatrooyunu #etkinlik #seferihisarofficial")
            assert len(post["caption"]) <= 2200

