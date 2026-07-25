"""Business logic for daily log CRUD operations."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.models import (
    CaffeineEntry,
    DailyLog,
    HabitEntry,
    MealEntry,
    NapEntry,
    NSDREntry,
    PreBedRitualEntry,
    RedLightEntry,
    SectionAbsence,
    SexualActivityEntry,
    StimulatingActivityEntry,
    SunlightEntry,
    SupplementEntry,
)
from backend.schemas import (
    CaffeineEntryCreate,
    DailyLogCreate,
    HabitEntryCreate,
    MealEntryCreate,
    NapEntryCreate,
    NSDREntryCreate,
    PreBedRitualCreate,
    RedLightEntryCreate,
    SexualActivityCreate,
    StimulatingActivityCreate,
    SunlightEntryCreate,
    SupplementEntryCreate,
)

# Maps entry_type URL segment → (ORM model, Pydantic create schema, DailyLog relationship name)
ENTRY_TYPE_MAP: dict[str, tuple[type[Any], type[Any], str]] = {
    "caffeine": (CaffeineEntry, CaffeineEntryCreate, "caffeine_entries"),
    "meals": (MealEntry, MealEntryCreate, "meal_entries"),
    "supplements": (SupplementEntry, SupplementEntryCreate, "supplement_entries"),
    "habits": (HabitEntry, HabitEntryCreate, "habit_entries"),
    "stimulating-activities": (
        StimulatingActivityEntry,
        StimulatingActivityCreate,
        "stimulating_activity_entries",
    ),
    "sexual-activity": (SexualActivityEntry, SexualActivityCreate, "sexual_activity_entry"),
    "pre-bed-rituals": (PreBedRitualEntry, PreBedRitualCreate, "pre_bed_ritual_entries"),
    "naps": (NapEntry, NapEntryCreate, "nap_entries"),
    "sunlight": (SunlightEntry, SunlightEntryCreate, "sunlight_entries"),
    "red-light": (RedLightEntry, RedLightEntryCreate, "red_light_entries"),
    "nsdr": (NSDREntry, NSDREntryCreate, "nsdr_entries"),
}


def get_or_create_daily_log(db: Session, date: dt.date) -> DailyLog:
    """Get existing DailyLog or create a new one."""
    log = db.get(DailyLog, date)
    if log is None:
        log = DailyLog(date=date)
        db.add(log)
        db.flush()
    return log


def get_daily_log(db: Session, date: dt.date) -> DailyLog | None:
    """Get a daily log by date."""
    return db.get(DailyLog, date)


def list_daily_logs(
    db: Session,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> list[DailyLog]:
    """List daily logs with optional date range filter."""
    query = db.query(DailyLog)
    if start_date is not None:
        query = query.filter(DailyLog.date >= start_date)
    if end_date is not None:
        query = query.filter(DailyLog.date <= end_date)
    return list(query.order_by(DailyLog.date).all())


def save_daily_log(db: Session, date: dt.date, data: DailyLogCreate) -> DailyLog:
    """Upsert a composite daily log — replace all sub-entries."""
    log = db.get(DailyLog, date)
    if log is not None:
        db.delete(log)
        db.flush()

    log = DailyLog(date=date, is_sick=data.is_sick, notes=data.notes)
    db.add(log)
    db.flush()

    _create_sub_entries(db, date, data)
    db.commit()
    db.refresh(log)
    return log


def delete_daily_log(db: Session, date: dt.date) -> bool:
    """Delete a daily log and all cascaded entries. Returns True if found."""
    log = db.get(DailyLog, date)
    if log is None:
        return False
    db.delete(log)
    db.commit()
    return True


def copy_day(db: Session, target_date: dt.date, source_date: dt.date) -> DailyLog | None:
    """Copy all entries from source_date to target_date.

    Returns None if source log doesn't exist.
    """
    source = db.get(DailyLog, source_date)
    if source is None:
        return None

    # Delete existing target if present
    existing = db.get(DailyLog, target_date)
    if existing is not None:
        db.delete(existing)
        db.flush()

    # Create new log with copied_from_date
    target = DailyLog(
        date=target_date,
        copied_from_date=source_date,
        is_sick=source.is_sick,
    )
    db.add(target)
    db.flush()

    # Clone all sub-entries
    for _entry_type, (model_cls, _schema_cls, rel_name) in ENTRY_TYPE_MAP.items():
        source_entries = getattr(source, rel_name)
        if source_entries is None:
            continue
        if isinstance(source_entries, list):
            for entry in source_entries:
                _clone_entry(db, entry, model_cls, target_date)
        else:
            _clone_entry(db, source_entries, model_cls, target_date)

    # ENTRY_TYPE_MAP omits section absences, so a plain copy would drop the
    # day's explicit negatives (#161 Lane 3a). Clone them onto the target date;
    # supplement_entries' product_id rides along via _clone_entry's column
    # introspection (it copies every non-id column, product_id included).
    for absence in source.section_absences:
        db.add(SectionAbsence(date=target_date, section_key=absence.section_key))

    db.commit()
    db.refresh(target)
    return target


def _clone_entry(db: Session, entry: Any, model_cls: type[Any], target_date: dt.date) -> None:
    """Clone a single entry to a new date by introspecting ORM columns."""
    mapper = inspect(model_cls)
    data: dict[str, Any] = {}
    for col in mapper.columns:
        if col.key == "id":
            continue
        if col.key == "date":
            data["date"] = target_date
        else:
            data[col.key] = getattr(entry, col.key)
    new_entry = model_cls(**data)
    db.add(new_entry)


def add_sub_entry(db: Session, date: dt.date, entry_type: str, data: dict[str, Any]) -> Any:
    """Add a single sub-entry to a daily log."""
    model_cls, schema_cls, _rel_name = ENTRY_TYPE_MAP[entry_type]
    validated = schema_cls(**data)
    get_or_create_daily_log(db, date)
    entry = model_cls(date=date, **validated.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_sub_entry(
    db: Session, entry_type: str, entry_id: int, data: dict[str, Any]
) -> Any | None:
    """Update a single sub-entry. Returns None if not found."""
    model_cls, schema_cls, _rel_name = ENTRY_TYPE_MAP[entry_type]
    entry = db.get(model_cls, entry_id)
    if entry is None:
        return None
    validated = schema_cls(**data)
    for key, value in validated.model_dump().items():
        setattr(entry, key, value)
    db.commit()
    db.refresh(entry)
    return entry


def delete_sub_entry(db: Session, entry_type: str, entry_id: int) -> bool:
    """Delete a single sub-entry. Returns True if found."""
    model_cls = ENTRY_TYPE_MAP[entry_type][0]
    entry = db.get(model_cls, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True


def _create_sub_entries(db: Session, date: dt.date, data: DailyLogCreate) -> None:
    """Create all sub-entries from a DailyLogCreate payload."""
    _entry_list: list[tuple[str, Sequence[BaseModel]]] = [
        ("caffeine", data.caffeine_entries),
        ("meals", data.meal_entries),
        ("supplements", data.supplement_entries),
        ("habits", data.habit_entries),
        ("stimulating-activities", data.stimulating_activity_entries),
        ("pre-bed-rituals", data.pre_bed_ritual_entries),
        ("naps", data.nap_entries),
        ("sunlight", data.sunlight_entries),
        ("red-light", data.red_light_entries),
        ("nsdr", data.nsdr_entries),
    ]
    for _entry_type_key, entries in _entry_list:
        model_cls = ENTRY_TYPE_MAP[_entry_type_key][0]
        for entry_data in entries:
            entry = model_cls(date=date, **entry_data.model_dump())
            db.add(entry)

    # Handle singular sexual_activity_entry
    if data.sexual_activity_entry is not None:
        entry = SexualActivityEntry(date=date, **data.sexual_activity_entry.model_dump())
        db.add(entry)

    # Section absences (#161 Lane 3a): explicit "did not do X" rows share the
    # sub-entry lifecycle. save_daily_log deletes-then-recreates the DailyLog,
    # and cascade="all, delete-orphan" wipes the old absences with it — so they
    # MUST be recreated here or every save would silently destroy them (the
    # validated Lane-1 write-path landmine). Dedupe on section_key; the model's
    # unique (date, section_key) is the backstop.
    _seen_absences: set[str] = set()
    for section_key in data.section_absences:
        if section_key in _seen_absences:
            continue
        _seen_absences.add(section_key)
        db.add(SectionAbsence(date=date, section_key=section_key))

    db.flush()


def has_entries(log: DailyLog) -> bool:
    """Check if a daily log has any sub-entries or explicit absence records.

    Section absences count: an explicit "none today" is recorded data (ADR 003
    amendment), so an absence-only day is a day with data in list/summary views.
    """
    for _entry_type, (_model_cls, _schema_cls, rel_name) in ENTRY_TYPE_MAP.items():
        entries = getattr(log, rel_name)
        if entries is None:
            continue
        if isinstance(entries, list) and len(entries) > 0:
            return True
        if not isinstance(entries, list) and entries is not None:
            return True
    return len(log.section_absences) > 0
