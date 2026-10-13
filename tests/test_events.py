from copy import deepcopy
from datetime import timedelta

from seferihisar.schedule import prepare
from seferihisar.editor import caption, event_date_label
from seferihisar.store import Store


def test_discover_20_days_ahead_and_persist(store, event, at, tmp_path):
    event["start"] = (at + timedelta(days=20)).isoformat()
    event["end"] = (at + timedelta(days=20, hours=2)).isoformat()
    store.upsert(event, at.isoformat())
    prepare(store, at)
    prepare(store, at + timedelta(minutes=15))
    assert len([p for p in store.posts() if p["kind"] == "announcement"]) == 1
    another = Store(tmp_path / "state.sqlite")
    assert another.items("event")[0]["start"] == event["start"]
    another.close()


def test_reminders_3_days_and_day_are_not_duplicated(store, event, at):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    prepare(store, at + timedelta(minutes=15))
    assert sum(p["kind"] == "reminder_3d" for p in store.posts()) == 1
    on_day = at + timedelta(days=3)
    store.upsert(event, on_day.isoformat())  # The source was rechecked on event day.
    prepare(store, on_day)
    prepare(store, on_day + timedelta(minutes=15))
    assert sum(p["kind"] == "reminder_day" for p in store.posts()) == 1


def test_delayed_schedule_catches_up_without_false_3_day_claim(store, event, at):
    store.upsert(event, at.isoformat())
    store.upsert(event, (at + timedelta(days=1)).isoformat())
    prepare(store, at + timedelta(days=1))
    reminder = next(p for p in store.posts() if p["kind"] == "reminder_3d")
    assert reminder["title"].startswith("2 gün kaldı")


def test_reschedule_supersedes_old_cards_and_rearms_reminders(store, event, at):
    key, _ = store.upsert(event, at.isoformat())
    prepare(store, at)
    event["start"] = (at + timedelta(days=15)).isoformat()
    event["end"] = (at + timedelta(days=15, hours=2)).isoformat()
    event["status"] = "rescheduled"
    new_key, changed = store.upsert(event, (at + timedelta(hours=1)).isoformat())
    assert new_key == key and changed
    prepare(store, at + timedelta(hours=1))
    assert store.items()[0]["revision"] == 2
    assert any(p["status"] == "superseded" for p in store.posts() if p.get("item_id") == key)
    assert any(p["kind"] == "update" and p["revision"] == 2 for p in store.posts())
    store.upsert(event, (at + timedelta(days=12)).isoformat())
    prepare(store, at + timedelta(days=12))
    assert any(p["kind"] == "reminder_3d" and p["revision"] == 2 for p in store.posts())


def test_cancelled_event_has_no_active_reminder_or_digest_slide(store, event, at):
    store.upsert(event, at.isoformat())
    prepare(store, at)
    event["status"] = "cancelled"
    store.upsert(event, at.isoformat())
    prepare(store, at)
    assert any(p["kind"] == "cancellation" for p in store.posts())
    assert not any(p["kind"].startswith("reminder") and p["status"] == "prepared" for p in store.posts())
    assert not any(event["title"] in str(p["slides"]) for p in store.posts() if p["kind"] in ("weekly", "monthly") and p["status"] == "prepared")


def test_cross_source_duplicate_and_same_title_different_dates(store, event, at):
    key, _ = store.upsert(event, at.isoformat())
    other = deepcopy(event)
    other["url"] = other["identity"] = "https://www.izmir.bel.tr/konser"
    other["source_id"] = "izmir-belediye"
    other["sources"] = [other["url"]]
    assert store.upsert(other, at.isoformat())[0] == key
    assert len(store.items()) == 1
    other["start"] = (at + timedelta(days=25)).isoformat()
    other["identity"] += "-2"
    store.upsert(other, at.isoformat())
    assert len(store.items()) == 2


def test_past_events_not_announced(store, event, at):
    event["start"] = (at - timedelta(days=2)).isoformat()
    event["end"] = event["start"]
    store.upsert(event, at.isoformat())
    prepare(store, at)
    assert not store.posts()


def test_unknown_time_can_have_event_day_reminder(store, event, at):
    event["start"] = at.replace(hour=0).isoformat()
    event["end"] = event["start"]
    event["time_known"] = False
    store.upsert(event, at.isoformat())
    prepare(store, at)
    assert any(p["kind"] == "reminder_day" and p["status"] == "prepared" for p in store.posts())


def test_multiday_unknown_time_reaches_item_and_digest_cards_and_captions(store, event, at):
    event.update(start='2026-10-13T00:00:00+03:00', end='2026-10-15T00:00:00+03:00',
                 time_known=False)
    store.upsert(event, at.isoformat())
    prepare(store, at)
    date_range = '13.10.2026 – 15.10.2026'
    for post in store.posts():
        assert date_range in post['caption']
        assert any(date_range in slide['body'] for slide in post['slides'])
        assert ' · 00:00' not in str(post)
    assert 'Saat açıklanmadı' in caption(event, 'Bölge takviminde')


def test_multiday_date_label_keeps_month_and_year_boundaries_and_start_time(event):
    event.update(start='2026-12-31T20:00:00+03:00', end='2027-01-01T00:00:00+03:00',
                 time_known=True)
    assert event_date_label(event) == '31.12.2026 – 01.01.2027 · Başlangıç 20:00'
    assert event_date_label(event, include_time=False) == '31.12.2026 – 01.01.2027'
    event.update(end='2026-12-31T22:00:00+03:00')
    assert event_date_label(event) == '31.12.2026 · 20:00'
