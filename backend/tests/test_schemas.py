"""Tests for Pydantic schema validation — hard rejects and response wrappers."""

import datetime as dt

import pytest
from pydantic import ValidationError

from backend.models import CaffeineSource, HabitType
from backend.schemas import (
    CaffeineEntryCreate,
    DailyLogCreate,
    DailyLogOut,
    DailyLogResponse,
    DailyLogSummary,
    ExportData,
    HabitEntryCreate,
    NapEntryCreate,
    RedLightEntryCreate,
)

# --- Hard rejects (Pydantic Field constraints) ---


def test_caffeine_amount_too_low() -> None:
    with pytest.raises(ValidationError):
        CaffeineEntryCreate(amount_mg=0, source=CaffeineSource.OTHER)


def test_caffeine_amount_too_high() -> None:
    with pytest.raises(ValidationError):
        CaffeineEntryCreate(amount_mg=601, source=CaffeineSource.OTHER)


def test_caffeine_amount_valid() -> None:
    entry = CaffeineEntryCreate(amount_mg=200, source=CaffeineSource.ESPRESSO)
    assert entry.amount_mg == 200


def test_nap_duration_too_high() -> None:
    with pytest.raises(ValidationError):
        NapEntryCreate(duration_minutes=241)


def test_nap_duration_valid() -> None:
    entry = NapEntryCreate(duration_minutes=240)
    assert entry.duration_minutes == 240


def test_red_light_duration_too_high() -> None:
    with pytest.raises(ValidationError):
        RedLightEntryCreate(duration_minutes=61)


def test_red_light_duration_valid() -> None:
    entry = RedLightEntryCreate(duration_minutes=60)
    assert entry.duration_minutes == 60


def test_habit_duration_too_high() -> None:
    with pytest.raises(ValidationError):
        HabitEntryCreate(habit_type=HabitType.EXERCISE, duration_minutes=301)


def test_habit_duration_at_limit() -> None:
    entry = HabitEntryCreate(habit_type=HabitType.EXERCISE, duration_minutes=300)
    assert entry.duration_minutes == 300


# --- Response wrappers ---


def test_daily_log_response_with_warnings() -> None:
    data = DailyLogOut(date=dt.date(2025, 6, 15))
    resp = DailyLogResponse(data=data, warnings=["Test warning"])
    assert resp.warnings == ["Test warning"]
    assert resp.data.date == dt.date(2025, 6, 15)


def test_daily_log_response_default_no_warnings() -> None:
    data = DailyLogOut(date=dt.date(2025, 6, 15))
    resp = DailyLogResponse(data=data)
    assert resp.warnings == []


def test_daily_log_summary() -> None:
    summary = DailyLogSummary(
        date=dt.date(2025, 6, 15),
        is_sick=True,
        has_entries=True,
    )
    assert summary.date == dt.date(2025, 6, 15)
    assert summary.is_sick is True
    assert summary.has_entries is True
    assert summary.copied_from_date is None


def test_export_data_empty() -> None:
    export = ExportData()
    assert export.daily_logs == []
    assert export.sleep_records == []


def test_export_data_with_logs() -> None:
    log = DailyLogOut(date=dt.date(2025, 6, 15))
    export = ExportData(daily_logs=[log])
    assert len(export.daily_logs) == 1


def test_daily_log_create_all_optional() -> None:
    log = DailyLogCreate()
    assert log.is_sick is None
    assert log.caffeine_entries == []


# --- section_absences mapping (#161 Lane 3a) ---


class _FakeAbsence:
    """Stand-in for an ORM SectionAbsence row (has a section_key attribute)."""

    def __init__(self, section_key: str) -> None:
        self.section_key = section_key


def test_daily_log_out_maps_orm_absences_to_keys() -> None:
    """model_validate feeds ORM rows; the before-validator emits their keys."""
    out = DailyLogOut(
        date=dt.date(2025, 6, 15),
        section_absences=[_FakeAbsence("caffeine"), _FakeAbsence("sauna")],  # type: ignore[list-item]
    )
    assert out.section_absences == ["caffeine", "sauna"]


def test_daily_log_out_accepts_plain_string_keys() -> None:
    out = DailyLogOut(date=dt.date(2025, 6, 15), section_absences=["nsdr"])
    assert out.section_absences == ["nsdr"]


def test_daily_log_out_non_list_absences_defaults_empty() -> None:
    out = DailyLogOut(date=dt.date(2025, 6, 15), section_absences=None)  # type: ignore[arg-type]
    assert out.section_absences == []
