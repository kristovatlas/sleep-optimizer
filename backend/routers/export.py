"""Data export API route — JSON, CSV (zip), and SQLite formats."""

from __future__ import annotations

import csv
import datetime as dt
import io
import sqlite3
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import settings as app_settings
from backend.database import get_db
from backend.models import SleepRecord, SupplementProduct
from backend.schemas import DailyLogOut, ExportData, SleepRecordOut, SupplementProductOut
from backend.services.daily_log_service import list_daily_logs

router = APIRouter(prefix="/api", tags=["export"])


class _AbsenceRow(NamedTuple):
    """A flat (date, section_key) pair for the section_absences CSV (#161)."""

    date: dt.date
    section_key: str


@router.get("/export", response_model=None)
def export_data(
    format: str = "json",
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
    db: Session = Depends(get_db),
) -> ExportData | StreamingResponse:
    """Export data as JSON or CSV zip."""
    if format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")

    logs = list_daily_logs(db, start_date=start_date, end_date=end_date)
    daily_logs_out = [DailyLogOut.model_validate(log) for log in logs]

    sleep_query = db.query(SleepRecord)
    if start_date is not None:
        sleep_query = sleep_query.filter(SleepRecord.date >= start_date)
    if end_date is not None:
        sleep_query = sleep_query.filter(SleepRecord.date <= end_date)
    sleep_records = [SleepRecordOut.model_validate(r) for r in sleep_query.all()]

    # #161 Lane 3a: the supplement library is date-independent, so it is exported
    # whole (not date-filtered) — logged entries reference products by id, and a
    # partial-range export must still resolve those ids.
    products = [
        SupplementProductOut.model_validate(p)
        for p in db.query(SupplementProduct).order_by(SupplementProduct.id).all()
    ]

    if format == "json":
        return ExportData(
            daily_logs=daily_logs_out,
            sleep_records=sleep_records,
            supplement_products=products,
        )

    # CSV zip
    return _build_csv_zip(daily_logs_out, sleep_records, products)


def _build_csv_zip(
    daily_logs: list[DailyLogOut],
    sleep_records: list[SleepRecordOut],
    supplement_products: list[SupplementProductOut],
) -> StreamingResponse:
    """Build a zip file containing one CSV per table."""
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Daily logs summary
        zf.writestr(
            "daily_logs.csv",
            _to_csv(
                daily_logs,
                [
                    "date",
                    "copied_from_date",
                    "is_sick",
                    "notes",
                ],
            ),
        )

        # Sleep records
        zf.writestr(
            "sleep_records.csv",
            _to_csv(
                sleep_records,
                [
                    "date",
                    "total_sleep_minutes",
                    "rem_minutes",
                    "deep_minutes",
                    "light_minutes",
                    "rem_pct",
                    "deep_pct",
                    "light_pct",
                    "sleep_efficiency",
                    "onset_latency_minutes",
                    "avg_hrv",
                    "lowest_hr",
                    "avg_hr",
                    "avg_breath_rate",
                    "readiness_score",
                    "sleep_score",
                    "bedtime",
                    "wake_time",
                ],
            ),
        )

        # Sub-entry CSVs
        _entry_types = [
            (
                "caffeine_entries",
                [
                    "id",
                    "date",
                    "time",
                    "amount_mg",
                    "source",
                ],
            ),
            (
                "meal_entries",
                [
                    "id",
                    "date",
                    "time",
                    "is_last_meal",
                    "notes",
                ],
            ),
            (
                "supplement_entries",
                [
                    "id",
                    "date",
                    "time",
                    "name",
                    "dose_mg",
                    "product_id",
                ],
            ),
            (
                "habit_entries",
                [
                    "id",
                    "date",
                    "habit_type",
                    "time",
                    "value",
                    "duration_minutes",
                    "notes",
                ],
            ),
            (
                "stimulating_activity_entries",
                [
                    "id",
                    "date",
                    "end_time",
                    "activity_type",
                    "duration_minutes",
                ],
            ),
            (
                "pre_bed_ritual_entries",
                [
                    "id",
                    "date",
                    "time",
                    "ritual_type",
                    "duration_minutes",
                ],
            ),
            (
                "nap_entries",
                [
                    "id",
                    "date",
                    "start_time",
                    "end_time",
                    "duration_minutes",
                ],
            ),
            (
                "sunlight_entries",
                [
                    "id",
                    "date",
                    "start_time",
                    "duration_minutes",
                    "estimated_lux",
                    "notes",
                ],
            ),
            (
                "red_light_entries",
                [
                    "id",
                    "date",
                    "panel_id",
                    "start_time",
                    "duration_minutes",
                    "dose_joules_cm2",
                ],
            ),
            (
                "nsdr_entries",
                [
                    "id",
                    "date",
                    "time",
                    "duration_minutes",
                    "nsdr_type",
                ],
            ),
        ]

        for attr_name, fields in _entry_types:
            all_entries = []
            for log in daily_logs:
                entries = getattr(log, attr_name)
                if isinstance(entries, list):
                    all_entries.extend(entries)
            zf.writestr(f"{attr_name}.csv", _to_csv(all_entries, fields))

        # Sexual activity (singular relationship)
        sexual_entries = [
            log.sexual_activity_entry for log in daily_logs if log.sexual_activity_entry is not None
        ]
        zf.writestr(
            "sexual_activity_entries.csv",
            _to_csv(
                sexual_entries,
                ["id", "date", "time", "activity_type"],
            ),
        )

        # Supplement library (#161 Lane 3a): product identity that entries
        # reference by product_id — without it a re-import loses which product
        # each entry is.
        zf.writestr(
            "supplement_products.csv",
            _to_csv(
                supplement_products,
                ["id", "name", "brand", "form", "default_dose", "unit", "step", "is_sticky"],
            ),
        )

        # Section absences (#161 Lane 3a): explicit "did not do X" negatives.
        # DailyLogOut.section_absences is the bare key strings, so pair each with
        # its log's date. Omitting these would silently convert every explicit
        # negative back to "unknown" on re-import and change correlations.
        absence_rows = [
            _AbsenceRow(date=log.date, section_key=key)
            for log in daily_logs
            for key in log.section_absences
        ]
        zf.writestr(
            "section_absences.csv",
            _to_csv(absence_rows, ["date", "section_key"]),
        )

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=somnus_export.zip"},
    )


def _consistent_sqlite_snapshot(db_path: Path) -> bytes:
    """Return a consistent SQLite snapshot via the online backup API (T-17).

    A raw byte-copy of the live file can capture a torn page set or miss
    ``-wal``/``-journal`` state if a write (e.g. an Oura sync) is in flight,
    yielding a ``.db`` that fails ``PRAGMA integrity_check``. The backup API
    copies pages under a read transaction, so the snapshot is internally
    consistent even under concurrent writes. The user relies on this export
    as their backup of otherwise-unrecoverable data.
    """
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(":memory:")
        try:
            src.backup(dst)
            return dst.serialize()
        finally:
            dst.close()
    finally:
        src.close()


@router.get("/export/sqlite", response_model=None)
def export_sqlite() -> StreamingResponse:
    """Export the SQLite database as a consistent snapshot."""
    db_path = app_settings.db_path
    if str(db_path) == ":memory:" or not db_path.exists():
        raise HTTPException(status_code=409, detail="SQLite export unavailable in this environment")
    return StreamingResponse(
        io.BytesIO(_consistent_sqlite_snapshot(db_path)),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=somnus.db"},
    )


# T-12 (docs/THREAT_MODEL.md): characters that make a spreadsheet treat a
# cell as a formula when the CSV is opened in Excel / Google Sheets. The full
# OWASP CSV-injection trigger set, including both line terminators.
_CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def _neutralize_csv_cell(value: str) -> str:
    """Prefix a leading formula trigger with a single quote (T-12).

    Reachable via free text (`notes`, supplement `name`, habit `value`) that
    may have arrived via T-01/T-02 or from Oura (AD4). Prefixing renders the
    cell as literal text in spreadsheet apps. The export has no negative-number
    fields, so guarding the ``-`` trigger mangles no legitimate value.
    """
    if value and value[0] in _CSV_FORMULA_TRIGGERS:
        return "'" + value
    return value


def _to_csv(items: Sequence[object], fields: list[str]) -> str:
    """Convert a list of Pydantic models to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(fields)
    for item in items:
        row = []
        for f in fields:
            val = getattr(item, f, None)
            row.append("" if val is None else _neutralize_csv_cell(str(val)))
        writer.writerow(row)
    return output.getvalue()
