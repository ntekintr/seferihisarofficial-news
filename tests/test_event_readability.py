import json
from copy import deepcopy
from datetime import timedelta

import pytest

from seferihisar.editor import caption, event_title, headline
from seferihisar.schedule import prepare, queue_item, slide_body
from seferihisar.render import readable_date_line


@pytest.mark.parametrize("category,label", [
    ("theatre", "Tiyatro oyunu"), ("concert", "Konser"),
    ("cinema", "Film gösterimi"), ("festival", "Festival"),
])
def test_event_name_keeps_source_title_and_explains_verified_type(event, category, label):
    event.update(title="Hafifletici Sebepler", category=category)
    original = deepcopy(event)
    assert headline(event, "announcement") == "Hafifletici Sebepler — " + label
    assert headline(event, "reminder_3d") == "3 gün kaldı: Hafifletici Sebepler — " + label
    assert headline(event, "reminder_day").startswith("Bugün yakınınızda:")
    assert headline(event, "cancellation").startswith("İptal duyurusu:")
    assert headline(event, "update").startswith("Etkinlik bilgisi güncellendi:")
    assert event == original


def test_general_category_does_not_guess_type_from_an_event_name(event):
    event.update(title="Konser salonunda buluşma", category="event")
    assert event_title(event) == "Konser salonunda buluşma — Etkinlik"


def test_event_card_omits_unknown_extras_and_caption_keeps_full_address(event):
    address = "Urla Belediyesi Atatürk Kültür Merkezi · Sıra mahallesi Zafer Caddesi No:80 Urla / İzmir"
    event.update(title="Hafifletici Sebepler", category="theatre", location=address,
                 organizer=None, free=None, price=None, currency=None)
    body = slide_body(event)
    assert "Urla Belediyesi Atatürk Kültür Merkezi" in body
    assert "Zafer Caddesi" not in body
    assert "Organizatör açıklanmadı" not in body
    assert "Ücret bilgisi açıklanmadı" not in body
    content = caption(event, headline(event, "announcement"))
    assert address in content
    assert "Organizatör: Açıklanmadı" in content
    assert "Ücret bilgisi açıklanmadı" in content
    assert content.split("\n\n")[0] == "Hafifletici Sebepler — Tiyatro oyunu"


def test_event_card_keeps_known_organizer_price_and_unambiguous_location(event):
    event.update(location="Ürkmez Hizmet Binası · Ürkmez Tiyatro Salonu",
                 organizer="Seferihisar Belediyesi", free=False, price="200", currency="TRY")
    body = slide_body(event)
    assert event["location"] in body
    assert "Düzenleyen: Seferihisar Belediyesi" in body
    assert "Ücret: 200 TL" in body
    event.update(free=True, price=None, currency=None)
    assert "Ücretsiz" in slide_body(event)


def test_known_price_without_currency_does_not_invent_one(event):
    event.update(price='200', currency=None, free=False)
    assert 'Ücret: 200' in slide_body(event)


@pytest.mark.parametrize('value,expected', [
    ('14.10.2026 · 20:00', '14 Ekim 2026 · 20:00'),
    ('31.12.2026 – 01.01.2027 · Saat açıklanmadı', '31 Aralık 2026 – 1 Ocak 2027 · Saat açıklanmadı'),
    ('31.02.2026', '31.02.2026'),
])
def test_visual_date_wording_keeps_verified_year_time_and_unknowns(value, expected):
    assert readable_date_line(value) == expected


def test_digest_slides_and_caption_make_each_event_type_explicit(store, event, at):
    event.update(title="Hafifletici Sebepler", category="theatre")
    store.upsert(event, at.isoformat())
    prepare(store, at)
    for post in store.posts():
        if post["kind"] not in ("weekly", "monthly"):
            continue
        assert post["slides"][1]["title"] == "Hafifletici Sebepler — Tiyatro oyunu"
        assert post["slides"][1]["category"] == "theatre"
        assert "Hafifletici Sebepler — Tiyatro oyunu" in post["caption"]


@pytest.mark.parametrize("status", ["prepared", "blocked_source"])
def test_refresh_unclaimed_card_keeps_identity_dates_bindings_and_source_revision(store, event, at, status):
    event.update(title="Hafifletici Sebepler", category="theatre")
    store.upsert(event, at.isoformat())
    item = store.items()[0]
    due = at + timedelta(hours=5)
    queue_item(store, item, "announcement", due, at)
    old = next(p for p in store.posts() if p["kind"] == "announcement")
    payload = json.loads(store.rows("SELECT payload FROM posts WHERE id=?", (old["id"],))[0]["payload"])
    payload.update(title="Bölge takviminde: Hafifletici Sebepler", caption="Eski metin",
                   illustration_keys={"0": "a" * 24})
    with store.db:
        store.db.execute("UPDATE posts SET payload=?,status=? WHERE id=?", (json.dumps(payload), status, old["id"]))
    source_payload = deepcopy(item)
    queue_item(store, item, "announcement", due + timedelta(hours=2), at + timedelta(minutes=15))
    refreshed = store.posts()[0]
    assert refreshed["id"] == old["id"]
    assert refreshed["due_at"] == due.isoformat()
    assert refreshed["created_at"] == at.isoformat()
    assert refreshed["title"] == "Hafifletici Sebepler — Tiyatro oyunu"
    assert refreshed["illustration_keys"] == {"0": "a" * 24}
    assert refreshed["status"] == status
    assert store.items()[0] == source_payload


@pytest.mark.parametrize("status", ["published", "publishing", "uncertain"])
def test_new_card_wording_does_not_change_a_claimed_payload(store, event, at, status):
    store.upsert(event, at.isoformat())
    item = store.items()[0]
    queue_item(store, item, "announcement", at, at)
    post = store.posts()[0]
    with store.db:
        store.db.execute("UPDATE posts SET status=? WHERE id=?", (status, post["id"]))
    before = store.rows("SELECT * FROM posts WHERE id=?", (post["id"],))[0]
    queue_item(store, item, "announcement", at + timedelta(hours=1), at + timedelta(minutes=15))
    assert store.rows("SELECT * FROM posts WHERE id=?", (post["id"],))[0] == before


def test_existing_card_revision_mismatch_is_not_refreshed(store, event, at):
    store.upsert(event, at.isoformat())
    item = store.items()[0]
    queue_item(store, item, "announcement", at, at)
    post = store.posts()[0]
    with store.db:
        store.db.execute("UPDATE posts SET revision=revision+1 WHERE id=?", (post["id"],))
    before = store.rows("SELECT * FROM posts WHERE id=?", (post["id"],))[0]
    queue_item(store, item, "announcement", at + timedelta(hours=1), at + timedelta(minutes=15))
    assert store.rows("SELECT * FROM posts WHERE id=?", (post["id"],))[0] == before
