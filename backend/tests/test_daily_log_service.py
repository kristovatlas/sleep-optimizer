"""Tests for daily log service layer."""

import datetime as dt

from sqlalchemy.orm import Session

from backend.models import (
    CaffeineEntry,
    CaffeineSource,
    DailyLog,
    NSDRType,
    SectionAbsence,
    SexualActivityType,
    SupplementProduct,
)
from backend.schemas import (
    CaffeineEntryCreate,
    DailyLogCreate,
    NapEntryCreate,
    NSDREntryCreate,
    SexualActivityCreate,
    SupplementEntryCreate,
)
from backend.services.daily_log_service import (
    add_sub_entry,
    copy_day,
    delete_daily_log,
    delete_sub_entry,
    get_daily_log,
    get_or_create_daily_log,
    has_entries,
    list_daily_logs,
    save_daily_log,
    update_sub_entry,
)

D1 = dt.date(2025, 6, 15)
D2 = dt.date(2025, 6, 16)
D3 = dt.date(2025, 6, 17)


# --- get_or_create ---


def test_get_or_create_creates_new(db: Session) -> None:
    log = get_or_create_daily_log(db, D1)
    assert log.date == D1
    assert db.get(DailyLog, D1) is not None


def test_get_or_create_returns_existing(db: Session) -> None:
    existing = DailyLog(date=D1, is_sick=True)
    db.add(existing)
    db.flush()
    log = get_or_create_daily_log(db, D1)
    assert log.is_sick is True


# --- save_daily_log ---


def test_save_creates_log_with_entries(db: Session) -> None:
    data = DailyLogCreate(
        is_sick=False,
        notes="Good day",
        caffeine_entries=[
            CaffeineEntryCreate(amount_mg=95, source=CaffeineSource.DRIP_COFFEE),
            CaffeineEntryCreate(amount_mg=40, source=CaffeineSource.TEA),
        ],
        nap_entries=[NapEntryCreate(duration_minutes=20)],
    )
    log = save_daily_log(db, D1, data)
    assert log.date == D1
    assert log.is_sick is False
    assert log.notes == "Good day"
    assert len(log.caffeine_entries) == 2
    assert len(log.nap_entries) == 1


def test_save_upserts_replaces_entries(db: Session) -> None:
    data1 = DailyLogCreate(
        caffeine_entries=[CaffeineEntryCreate(amount_mg=95, source=CaffeineSource.DRIP_COFFEE)],
    )
    save_daily_log(db, D1, data1)

    data2 = DailyLogCreate(
        caffeine_entries=[CaffeineEntryCreate(amount_mg=200, source=CaffeineSource.COLD_BREW)],
    )
    log = save_daily_log(db, D1, data2)
    assert len(log.caffeine_entries) == 1
    assert log.caffeine_entries[0].amount_mg == 200


def test_save_with_sexual_activity(db: Session) -> None:
    data = DailyLogCreate(
        sexual_activity_entry=SexualActivityCreate(
            activity_type=SexualActivityType.PARTNERED,
        ),
    )
    log = save_daily_log(db, D1, data)
    assert log.sexual_activity_entry is not None
    assert log.sexual_activity_entry.activity_type == SexualActivityType.PARTNERED


def test_save_empty_log(db: Session) -> None:
    log = save_daily_log(db, D1, DailyLogCreate())
    assert log.date == D1
    assert log.caffeine_entries == []


# --- save_daily_log: section absences + supplement product links (#161 Lane 3a) ---


def test_save_preserves_absence_in_payload(db: Session) -> None:
    """The validated write-path landmine: save deletes-then-recreates the log,
    and the cascade wipes absences — a save that carries the absence forward in
    its payload must recreate it, not orphan-delete it."""
    save_daily_log(db, D1, DailyLogCreate(section_absences=["caffeine", "sauna"]))
    assert {a.section_key for a in db.query(SectionAbsence).all()} == {"caffeine", "sauna"}

    # Edit an unrelated field; keep "caffeine" in the payload, drop "sauna".
    log = save_daily_log(db, D1, DailyLogCreate(notes="edited", section_absences=["caffeine"]))
    keys = {a.section_key for a in log.section_absences}
    # "caffeine" survives (it was in the payload); "sauna" is gone (replace
    # semantics — it was omitted), proving the save discriminates by payload.
    assert keys == {"caffeine"}
    assert db.query(SectionAbsence).count() == 1


def test_save_dedupes_repeated_absence_keys(db: Session) -> None:
    log = save_daily_log(db, D1, DailyLogCreate(section_absences=["sauna", "sauna", "nsdr"]))
    assert sorted(a.section_key for a in log.section_absences) == ["nsdr", "sauna"]


def test_save_with_no_absences_leaves_none(db: Session) -> None:
    log = save_daily_log(db, D1, DailyLogCreate(notes="plain"))
    assert log.section_absences == []


def test_save_preserves_supplement_product_link(db: Session) -> None:
    product = SupplementProduct(name="Magnesium Glycinate", unit="mg")
    db.add(product)
    db.flush()

    save_daily_log(
        db,
        D1,
        DailyLogCreate(
            supplement_entries=[
                SupplementEntryCreate(
                    name="Magnesium Glycinate", dose_mg=200, product_id=product.id
                )
            ]
        ),
    )
    reloaded = get_daily_log(db, D1)
    assert reloaded is not None
    assert len(reloaded.supplement_entries) == 1
    assert reloaded.supplement_entries[0].product_id == product.id
    assert reloaded.supplement_entries[0].dose_mg == 200


def test_save_free_text_supplement_keeps_product_id_null(db: Session) -> None:
    """Regression: legacy free-text supplement (no product) stays un-linked."""
    log = save_daily_log(
        db,
        D1,
        DailyLogCreate(supplement_entries=[SupplementEntryCreate(name="Fish oil", dose_mg=1000)]),
    )
    assert log.supplement_entries[0].product_id is None


# --- get_daily_log ---


def test_get_existing(db: Session) -> None:
    save_daily_log(db, D1, DailyLogCreate(notes="test"))
    log = get_daily_log(db, D1)
    assert log is not None
    assert log.notes == "test"


def test_get_nonexistent(db: Session) -> None:
    assert get_daily_log(db, D1) is None


# --- list_daily_logs ---


def test_list_all(db: Session) -> None:
    save_daily_log(db, D1, DailyLogCreate())
    save_daily_log(db, D2, DailyLogCreate())
    save_daily_log(db, D3, DailyLogCreate())
    logs = list_daily_logs(db)
    assert len(logs) == 3
    assert logs[0].date == D1  # ordered by date


def test_list_with_date_range(db: Session) -> None:
    save_daily_log(db, D1, DailyLogCreate())
    save_daily_log(db, D2, DailyLogCreate())
    save_daily_log(db, D3, DailyLogCreate())
    logs = list_daily_logs(db, start_date=D2, end_date=D2)
    assert len(logs) == 1
    assert logs[0].date == D2


def test_list_empty(db: Session) -> None:
    assert list_daily_logs(db) == []


# --- delete_daily_log ---


def test_delete_existing(db: Session) -> None:
    save_daily_log(
        db,
        D1,
        DailyLogCreate(
            caffeine_entries=[CaffeineEntryCreate(amount_mg=95, source=CaffeineSource.OTHER)],
        ),
    )
    assert delete_daily_log(db, D1) is True
    assert get_daily_log(db, D1) is None
    # Cascade should have deleted entries
    assert db.query(CaffeineEntry).count() == 0


def test_delete_nonexistent(db: Session) -> None:
    assert delete_daily_log(db, D1) is False


# --- copy_day ---


def test_copy_day_copies_entries(db: Session) -> None:
    data = DailyLogCreate(
        is_sick=True,
        notes="Source notes",
        caffeine_entries=[CaffeineEntryCreate(amount_mg=100, source=CaffeineSource.ESPRESSO)],
        nap_entries=[NapEntryCreate(duration_minutes=30)],
        nsdr_entries=[NSDREntryCreate(duration_minutes=15, nsdr_type=NSDRType.YOGA_NIDRA)],
    )
    save_daily_log(db, D1, data)

    target = copy_day(db, D2, D1)
    assert target is not None
    assert target.date == D2
    assert target.copied_from_date == D1
    assert target.is_sick is True
    assert target.notes is None  # Notes NOT copied per spec
    assert len(target.caffeine_entries) == 1
    assert target.caffeine_entries[0].amount_mg == 100
    assert target.caffeine_entries[0].date == D2
    assert len(target.nap_entries) == 1
    assert len(target.nsdr_entries) == 1


def test_copy_day_overwrites_target(db: Session) -> None:
    save_daily_log(
        db,
        D1,
        DailyLogCreate(
            caffeine_entries=[CaffeineEntryCreate(amount_mg=100, source=CaffeineSource.OTHER)],
        ),
    )
    save_daily_log(
        db,
        D2,
        DailyLogCreate(
            caffeine_entries=[CaffeineEntryCreate(amount_mg=200, source=CaffeineSource.OTHER)],
        ),
    )

    target = copy_day(db, D2, D1)
    assert target is not None
    assert len(target.caffeine_entries) == 1
    assert target.caffeine_entries[0].amount_mg == 100


def test_copy_day_carries_absences(db: Session) -> None:
    """copy_day iterates ENTRY_TYPE_MAP, which omits absences — the copy must
    clone them onto the target date or a "None today" negative is silently lost.
    The supplement key references a real product (round 3: save validates
    supplement:* keys against the library)."""
    product = SupplementProduct(name="Melatonin", unit="mg")
    db.add(product)
    db.flush()
    supp_key = f"supplement:{product.id}"
    save_daily_log(db, D1, DailyLogCreate(section_absences=["caffeine", supp_key]))
    target = copy_day(db, D2, D1)
    assert target is not None
    assert {a.section_key for a in target.section_absences} == {"caffeine", supp_key}
    assert all(a.date == D2 for a in target.section_absences)


def test_copy_day_carries_supplement_product_id(db: Session) -> None:
    product = SupplementProduct(name="L-Theanine", unit="mg")
    db.add(product)
    db.flush()
    save_daily_log(
        db,
        D1,
        DailyLogCreate(
            supplement_entries=[
                SupplementEntryCreate(name="L-Theanine", dose_mg=200, product_id=product.id)
            ]
        ),
    )
    target = copy_day(db, D2, D1)
    assert target is not None
    assert len(target.supplement_entries) == 1
    assert target.supplement_entries[0].product_id == product.id
    assert target.supplement_entries[0].date == D2


def test_copy_day_source_not_found(db: Session) -> None:
    assert copy_day(db, D2, D1) is None


def test_copy_day_sexual_activity(db: Session) -> None:
    data = DailyLogCreate(
        sexual_activity_entry=SexualActivityCreate(
            activity_type=SexualActivityType.PARTNERED,
        ),
    )
    save_daily_log(db, D1, data)
    target = copy_day(db, D2, D1)
    assert target is not None
    assert target.sexual_activity_entry is not None
    assert target.sexual_activity_entry.activity_type == SexualActivityType.PARTNERED


# --- add_sub_entry ---


def test_add_sub_entry_creates_log_if_needed(db: Session) -> None:
    entry = add_sub_entry(db, D1, "caffeine", {"amount_mg": 95, "source": "other"})
    assert entry.amount_mg == 95
    assert db.get(DailyLog, D1) is not None


def test_add_sub_entry_to_existing_log(db: Session) -> None:
    save_daily_log(db, D1, DailyLogCreate())
    entry = add_sub_entry(db, D1, "naps", {"duration_minutes": 20})
    assert entry.duration_minutes == 20
    assert entry.date == D1


# --- update_sub_entry ---


def test_update_sub_entry(db: Session) -> None:
    entry = add_sub_entry(db, D1, "caffeine", {"amount_mg": 95, "source": "other"})
    updated = update_sub_entry(db, "caffeine", entry.id, {"amount_mg": 200, "source": "espresso"})
    assert updated is not None
    assert updated.amount_mg == 200


def test_update_sub_entry_not_found(db: Session) -> None:
    assert update_sub_entry(db, "caffeine", 999, {"amount_mg": 200, "source": "other"}) is None


# --- delete_sub_entry ---


def test_delete_sub_entry(db: Session) -> None:
    entry = add_sub_entry(db, D1, "caffeine", {"amount_mg": 95, "source": "other"})
    assert delete_sub_entry(db, "caffeine", entry.id) is True
    assert db.get(CaffeineEntry, entry.id) is None


def test_delete_sub_entry_not_found(db: Session) -> None:
    assert delete_sub_entry(db, "caffeine", 999) is False


# --- has_entries ---


def test_has_entries_true(db: Session) -> None:
    log = save_daily_log(
        db,
        D1,
        DailyLogCreate(
            caffeine_entries=[CaffeineEntryCreate(amount_mg=95, source=CaffeineSource.OTHER)],
        ),
    )
    assert has_entries(log) is True


def test_has_entries_false(db: Session) -> None:
    log = save_daily_log(db, D1, DailyLogCreate())
    assert has_entries(log) is False


def test_has_entries_with_sexual_activity(db: Session) -> None:
    log = save_daily_log(
        db,
        D1,
        DailyLogCreate(
            sexual_activity_entry=SexualActivityCreate(
                activity_type=SexualActivityType.PARTNERED,
            ),
        ),
    )
    assert has_entries(log) is True


def test_has_entries_absence_only_day(db: Session) -> None:
    """An explicit 'none today' record is recorded data (ADR 003 amendment):
    a day holding only a SectionAbsence counts as a day with entries."""
    log = save_daily_log(db, D1, DailyLogCreate(section_absences=["caffeine"]))
    assert has_entries(log) is True
