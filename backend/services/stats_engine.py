"""Statistical analysis engine — DataFrame prep, correlations, regression, outliers."""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session, joinedload

from backend.models import DailyLog, HabitType, SleepRecord, SupplementEntry
from backend.services.dashboard_service import _normalize_bedtime_hour

# --- Variable labels ---

VARIABLE_LABELS: dict[str, str] = {
    # Outcomes
    "sleep_score": "Sleep Score",
    "deep_minutes": "Deep Sleep (min)",
    "rem_minutes": "REM Sleep (min)",
    "avg_hrv": "HRV (ms)",
    "onset_latency_minutes": "Onset Latency (min)",
    "sleep_efficiency": "Sleep Efficiency",
    "total_sleep_minutes": "Total Sleep (min)",
    # Predictors
    "total_caffeine_mg": "Total Caffeine (mg)",
    "last_caffeine_hour": "Last Caffeine (hour)",
    "last_meal_hour": "Last Meal (hour)",
    "exercise_done": "Exercise",
    "exercise_duration_minutes": "Exercise Duration (min)",
    "alcohol": "Alcohol",
    "stress_level": "Stress Level",
    "room_temp_f": "Room Temp (F)",
    "blue_blockers": "Blue Blockers",
    "screens_off": "Screens Off",
    "sauna": "Sauna",
    "warm_shower": "Warm Shower",
    "stimulating_minutes": "Stimulating Activity (min)",
    "stimulating_last_hour": "Last Stimulating Activity (hour)",
    "nap_total_minutes": "Nap Duration (min)",
    "nap_count": "Nap Count",
    "sunlight_morning_minutes": "Morning Sunlight (min)",
    "sunlight_first_hour": "First Sunlight (hour)",
    "red_light_done": "Red Light Therapy",
    "red_light_dose_j_cm2": "Red Light Dose (J/cm²)",
    "nsdr_done": "NSDR",
    "nsdr_total_minutes": "NSDR Duration (min)",
    "ritual_done": "Pre-Bed Ritual",
    "ritual_total_minutes": "Ritual Duration (min)",
    "sexual_activity": "Sexual Activity",
    "sigma_7d": "Bedtime Variability (7d)",
    "delta_7d": "Bedtime Offset (7d avg)",
    "bedtime_hour": "Bedtime (hour)",
    # Derived timing factor emitted by the recommender, not a data column
    "social_jet_lag": "Social Jet Lag",
}

OUTCOME_COLUMNS = [
    "sleep_score",
    "deep_minutes",
    "rem_minutes",
    "avg_hrv",
    "onset_latency_minutes",
    "sleep_efficiency",
    "total_sleep_minutes",
]

PRIMARY_OUTCOMES = ["sleep_score", "deep_minutes", "rem_minutes", "avg_hrv"]

PREDICTOR_COLUMNS = [
    "total_caffeine_mg",
    "last_caffeine_hour",
    "last_meal_hour",
    "exercise_done",
    "exercise_duration_minutes",
    "alcohol",
    "stress_level",
    "room_temp_f",
    "blue_blockers",
    "screens_off",
    "sauna",
    "warm_shower",
    "stimulating_minutes",
    "stimulating_last_hour",
    "nap_total_minutes",
    "nap_count",
    "sunlight_morning_minutes",
    "sunlight_first_hour",
    "red_light_done",
    "red_light_dose_j_cm2",
    "nsdr_done",
    "nsdr_total_minutes",
    "ritual_done",
    "ritual_total_minutes",
    "sexual_activity",
    "sigma_7d",
    "delta_7d",
    "bedtime_hour",
]


def _time_to_hour(t: dt.time | None) -> float | None:
    """Convert a time object to decimal hours, or None."""
    if t is None:
        return None
    return t.hour + t.minute / 60


def _bedtime_clock_hour(t: dt.time | None) -> float | None:
    """Time on the BEDTIME clock (wrap < 6 → 24+), matching
    _normalize_bedtime_hour. Used only for supplement timing-before-bed, which
    is subtracted from bedtime_hour, so both sides must share the < 6 cutoff.
    Distinct from _evening_time_to_hour (< 4, for caffeine/meal consumption).
    """
    h = _time_to_hour(t)
    if h is not None and h < 6:
        h += 24
    return h


def _evening_time_to_hour(t: dt.time | None) -> float | None:
    """Convert an event time to the continuous 24+ evening clock.

    Same idea as _normalize_bedtime_hour (dashboard_service): early-morning
    hours shift to 24+, so 00:30 → 24.5 (later than 23:00), not 0.5 (which
    would sort as the earliest event of the day and corrupt correlations —
    see #134). The cutoff here is deliberately NARROWER than bedtime's:
    consumption events before 4 AM wrap (post-midnight caffeine/meals
    cluster 00:00–03:00), while 4–6 AM reads as a genuine early-riser
    morning event and stays raw; bedtime keeps its < 6 cutoff (nobody's
    evening bedtime is 5 AM). Owner-decided 2026-07-22 (#142). Still a
    heuristic — a real 3:30 AM breakfast wraps, a 4:30 AM post-all-nighter
    espresso doesn't; the travel/timezone-robust replacement is tracked in
    #144. Used for last_caffeine_hour, last_meal_hour, and
    stimulating_last_hour; NOT for sunlight_first_hour, which is a genuine
    morning clock time.
    """
    h = _time_to_hour(t)
    if h is not None and h < 4:
        h += 24
    return h


# ---------------------------------------------------------------------------
# #159: explicit section absence — the third data state.
#
# A SectionAbsence row means the user explicitly marked a log section as "did
# NOT do it" for a date (recorded negative data), distinct from a blank
# (NULL = not recorded, excluded from analysis — see ADR 003). Aggregation
# maps an absent section to its explicit zero: binary habit columns → 0.0,
# continuous total/count/minutes columns → 0. This gives the 8 all-1.0-or-NULL
# binary habits the variance they need to become correlatable.
#
# Clock / "last-hour" / "first-hour" columns (last_caffeine_hour,
# last_meal_hour, stimulating_last_hour, sunlight_first_hour) are DELIBERATELY
# omitted from these maps: there is no clock time for an event that did not
# happen, and forcing 0 would corrupt the evening-clock analysis (see
# _evening_time_to_hour / #134). They stay NULL.
_ABSENCE_BINARY_COLUMNS: dict[str, tuple[str, ...]] = {
    "alcohol": ("alcohol",),
    "exercise": ("exercise_done",),
    "blue_blockers": ("blue_blockers",),
    "screens_off": ("screens_off",),
    "sauna": ("sauna",),
    "warm_shower": ("warm_shower",),
    "red_light": ("red_light_done",),
    "nsdr": ("nsdr_done",),
    "ritual": ("ritual_done",),
}

_ABSENCE_CONTINUOUS_COLUMNS: dict[str, tuple[str, ...]] = {
    "caffeine": ("total_caffeine_mg",),
    "exercise": ("exercise_duration_minutes",),
    "red_light": ("red_light_dose_j_cm2",),
    "nsdr": ("nsdr_total_minutes",),
    "ritual": ("ritual_total_minutes",),
    "nap": ("nap_total_minutes", "nap_count"),
    "stimulating": ("stimulating_minutes",),
    "sunlight": ("sunlight_morning_minutes",),
    # "meal" has only a clock column (last_meal_hour), which stays NULL — a
    # meal-absent day therefore contributes no numeric zero, by design.
}

# Section key → predicate for "this section has real entries this day". Real
# entries always win over an absence row: if a day somehow has both, the
# entries stand and the absence is ignored (no assert/log — just prefer data).
_ABSENCE_PRESENCE: dict[str, Any] = {
    "caffeine": lambda log: bool(log.caffeine_entries),
    "meal": lambda log: bool(log.meal_entries),
    "exercise": lambda log: any(e.habit_type == HabitType.EXERCISE for e in log.habit_entries),
    "alcohol": lambda log: any(e.habit_type == HabitType.ALCOHOL for e in log.habit_entries),
    "blue_blockers": lambda log: any(
        e.habit_type == HabitType.BLUE_BLOCKERS_ON for e in log.habit_entries
    ),
    "screens_off": lambda log: any(
        e.habit_type == HabitType.SCREENS_OFF for e in log.habit_entries
    ),
    "sauna": lambda log: any(e.habit_type == HabitType.SAUNA for e in log.habit_entries),
    "warm_shower": lambda log: any(
        e.habit_type == HabitType.WARM_SHOWER for e in log.habit_entries
    ),
    "stimulating": lambda log: bool(log.stimulating_activity_entries),
    "nap": lambda log: bool(log.nap_entries),
    "sunlight": lambda log: bool(log.sunlight_entries),
    "red_light": lambda log: bool(log.red_light_entries),
    "nsdr": lambda log: bool(log.nsdr_entries),
    "ritual": lambda log: bool(log.pre_bed_ritual_entries),
}


def _section_has_entries(log: DailyLog, section_key: str) -> bool:
    """True if the section has any real logged entries for the day.

    Unknown section keys (e.g. Lane 2's ``supplement:<name>``) return False —
    they have no entry relationship here, so an absence for them simply has no
    column to zero in this lane.
    """
    predicate = _ABSENCE_PRESENCE.get(section_key)
    return bool(predicate(log)) if predicate is not None else False


# #161 Lane 2: per-supplement predictor column prefixes. Product columns are
# dynamic (one pair per library product observed with entries in the window),
# so they can't be pre-listed in PREDICTOR_COLUMNS/VARIABLE_LABELS — they are
# discovered by prefix. ``supplement_dose_<pid>`` = summed per-day dose in the
# product's unit; ``supplement_taken_hour_<pid>`` = the latest evening-clock
# hour the product was taken (a temporary column converted to hours-before-bed
# in prepare_analysis_dataframe, then dropped).
_SUPP_DOSE_PREFIX = "supplement_dose_"
_SUPP_TAKEN_HOUR_PREFIX = "supplement_taken_hour_"
_SUPP_HBB_PREFIX = "supplement_hbb_"
_SUPP_ABSENCE_PREFIX = "supplement:"


def _aggregate_supplements(log: DailyLog, row: dict[str, Any]) -> None:
    """Emit per-product dose + timing columns for product-linked entries (#161).

    Only entries with a ``product_id`` are analyzed; legacy free-text rows
    (product_id NULL) are ignored and never spawn a predictor column. For each
    product observed on the day: dose is the SUM of that product's doses, and
    the timing column is the LATEST evening-clock hour it was taken (closest to
    bed) — later converted to hours-before-bedtime once the SleepRecord bedtime
    is joined. No timed entry → timing stays NULL.
    """
    by_product: dict[int, list[Any]] = {}
    for entry in log.supplement_entries:
        if entry.product_id is None:
            continue
        by_product.setdefault(entry.product_id, []).append(entry)

    for pid, entries in by_product.items():
        doses = [e.dose_mg for e in entries if e.dose_mg is not None]
        # Entries present but NO recorded dose → NULL (took it, dose unknown),
        # NOT 0.0. Zero is reserved for an explicit `supplement:<pid>` absence
        # ("none today", set in _apply_section_absences) — conflating the two
        # would let a dose-less log masquerade as a skip and corrupt the dose
        # correlation (ADR 003: unknown ≠ zero). Codex P2, Lane 2 review.
        row[f"{_SUPP_DOSE_PREFIX}{pid}"] = float(sum(doses)) if doses else None
        # Timing is measured against bedtime (hbb = bedtime_hour - taken_hour),
        # so the taken-hour MUST use bedtime's clock (wrap < 6, matching
        # _normalize_bedtime_hour) — NOT _evening_time_to_hour's < 4 consumption
        # cutoff. Otherwise a 4:30 AM dose before a 5 AM (wrapped 29.0) bedtime
        # would read 29.0 - 4.5 = 24.5 h instead of 0.5 (Codex P2, Lane 2 re-run).
        taken_hours = [h for e in entries if (h := _bedtime_clock_hour(e.time)) is not None]
        row[f"{_SUPP_TAKEN_HOUR_PREFIX}{pid}"] = max(taken_hours) if taken_hours else None


def _supplement_has_entries(log: DailyLog, pid: int) -> bool:
    """True if the day has a real logged entry for the given product."""
    return any(e.product_id == pid for e in log.supplement_entries)


def _apply_section_absences(log: DailyLog, row: dict[str, Any]) -> None:
    """Map each explicit SectionAbsence to its zero column(s) (#159, #161).

    Only applies the zero when the section has NO real entries that day (real
    entries win). Clock columns are left untouched (NULL) by construction —
    they are absent from the column maps above. A ``supplement:<pid>`` key
    (Lane 2) maps a product's dose column to explicit 0.0 (none today), leaving
    its timing column NULL — there is no time for something not taken, mirroring
    the caffeine last-hour rule.
    """
    for absence in log.section_absences:
        section_key = absence.section_key
        if section_key.startswith(_SUPP_ABSENCE_PREFIX):
            raw_pid = section_key[len(_SUPP_ABSENCE_PREFIX) :]
            try:
                pid = int(raw_pid)
            except ValueError:
                continue
            if not _supplement_has_entries(log, pid):
                row[f"{_SUPP_DOSE_PREFIX}{pid}"] = 0.0
            continue
        if _section_has_entries(log, section_key):
            continue
        for col in _ABSENCE_BINARY_COLUMNS.get(section_key, ()):
            row[col] = 0.0
        for col in _ABSENCE_CONTINUOUS_COLUMNS.get(section_key, ()):
            row[col] = 0


def _aggregate_daily_log(log: DailyLog) -> dict[str, Any]:
    """Aggregate all sub-entries of a DailyLog into flat numeric features."""
    row: dict[str, Any] = {"is_sick": True if log.is_sick else None}

    # Caffeine
    if log.caffeine_entries:
        row["total_caffeine_mg"] = sum(e.amount_mg for e in log.caffeine_entries)
        times = [
            h for e in log.caffeine_entries if (h := _evening_time_to_hour(e.time)) is not None
        ]
        row["last_caffeine_hour"] = max(times) if times else None
    else:
        row["total_caffeine_mg"] = None
        row["last_caffeine_hour"] = None

    # Meals
    meal_times = [h for e in log.meal_entries if (h := _evening_time_to_hour(e.time)) is not None]
    last_meal_entries = [e for e in log.meal_entries if e.is_last_meal]
    if last_meal_entries and last_meal_entries[0].time is not None:
        row["last_meal_hour"] = _evening_time_to_hour(last_meal_entries[0].time)
    elif meal_times:
        row["last_meal_hour"] = max(meal_times)
    else:
        row["last_meal_hour"] = None

    # Exercise
    exercise_entries = [e for e in log.habit_entries if e.habit_type == HabitType.EXERCISE]
    if exercise_entries:
        row["exercise_done"] = 1.0
        durations = [e.duration_minutes for e in exercise_entries if e.duration_minutes is not None]
        row["exercise_duration_minutes"] = sum(durations) if durations else None
    else:
        row["exercise_done"] = None
        row["exercise_duration_minutes"] = None

    # Binary habits
    habit_map = {
        HabitType.ALCOHOL: "alcohol",
        HabitType.BLUE_BLOCKERS_ON: "blue_blockers",
        HabitType.SCREENS_OFF: "screens_off",
        HabitType.SAUNA: "sauna",
        HabitType.WARM_SHOWER: "warm_shower",
    }
    for habit_type, col_name in habit_map.items():
        entries = [e for e in log.habit_entries if e.habit_type == habit_type]
        row[col_name] = 1.0 if entries else None

    # Stress level
    stress_entries = [e for e in log.habit_entries if e.habit_type == HabitType.STRESS_LEVEL]
    if stress_entries and stress_entries[0].value is not None:
        try:
            row["stress_level"] = float(stress_entries[0].value)
        except (ValueError, TypeError):
            row["stress_level"] = None
    else:
        row["stress_level"] = None

    # Room temp
    temp_entries = [e for e in log.habit_entries if e.habit_type == HabitType.ROOM_TEMP_F]
    if temp_entries and temp_entries[0].value is not None:
        try:
            row["room_temp_f"] = float(temp_entries[0].value)
        except (ValueError, TypeError):
            row["room_temp_f"] = None
    else:
        row["room_temp_f"] = None

    # Stimulating activities
    if log.stimulating_activity_entries:
        durations = [
            e.duration_minutes
            for e in log.stimulating_activity_entries
            if e.duration_minutes is not None
        ]
        row["stimulating_minutes"] = sum(durations) if durations else None
        end_times = [
            h
            for e in log.stimulating_activity_entries
            if (h := _evening_time_to_hour(e.end_time)) is not None
        ]
        row["stimulating_last_hour"] = max(end_times) if end_times else None
    else:
        row["stimulating_minutes"] = None
        row["stimulating_last_hour"] = None

    # Naps
    if log.nap_entries:
        durations = [e.duration_minutes for e in log.nap_entries if e.duration_minutes is not None]
        row["nap_total_minutes"] = sum(durations) if durations else None
        row["nap_count"] = float(len(log.nap_entries))
    else:
        row["nap_total_minutes"] = None
        row["nap_count"] = None

    # Sunlight
    if log.sunlight_entries:
        morning_entries = [
            e for e in log.sunlight_entries if e.start_time is not None and e.start_time.hour < 12
        ]
        if morning_entries:
            durations = [
                e.duration_minutes for e in morning_entries if e.duration_minutes is not None
            ]
            row["sunlight_morning_minutes"] = sum(durations) if durations else None
            start_times = [
                h for e in morning_entries if (h := _time_to_hour(e.start_time)) is not None
            ]
            row["sunlight_first_hour"] = min(start_times) if start_times else None
        else:
            row["sunlight_morning_minutes"] = None
            row["sunlight_first_hour"] = None
    else:
        row["sunlight_morning_minutes"] = None
        row["sunlight_first_hour"] = None

    # Red light
    if log.red_light_entries:
        row["red_light_done"] = 1.0
        doses = [e.dose_joules_cm2 for e in log.red_light_entries if e.dose_joules_cm2 is not None]
        row["red_light_dose_j_cm2"] = sum(doses) if doses else None
    else:
        row["red_light_done"] = None
        row["red_light_dose_j_cm2"] = None

    # NSDR
    if log.nsdr_entries:
        row["nsdr_done"] = 1.0
        durations = [e.duration_minutes for e in log.nsdr_entries if e.duration_minutes is not None]
        row["nsdr_total_minutes"] = sum(durations) if durations else None
    else:
        row["nsdr_done"] = None
        row["nsdr_total_minutes"] = None

    # Pre-bed rituals
    if log.pre_bed_ritual_entries:
        row["ritual_done"] = 1.0
        durations = [
            e.duration_minutes for e in log.pre_bed_ritual_entries if e.duration_minutes is not None
        ]
        row["ritual_total_minutes"] = sum(durations) if durations else None
    else:
        row["ritual_done"] = None
        row["ritual_total_minutes"] = None

    # Sexual activity
    row["sexual_activity"] = 1.0 if log.sexual_activity_entry is not None else None

    # #161 Lane 2: per-product supplement dose + timing columns (dynamic).
    _aggregate_supplements(log, row)

    # #159: fold in explicitly-recorded section absences (recorded 0/False),
    # after all real entries are aggregated so real data wins over an absence.
    _apply_section_absences(log, row)

    return row


def prepare_analysis_dataframe(db: Session) -> pd.DataFrame:
    """Build a flat DataFrame joining SleepRecord + DailyLog sub-entries.

    One row per date. NaN for missing values (never zero). All analysis
    functions operate on this DataFrame.
    """
    # Query all sleep records
    sleep_records = db.query(SleepRecord).order_by(SleepRecord.date).all()

    if not sleep_records:
        return pd.DataFrame()

    sleep_rows = []
    for r in sleep_records:
        row: dict[str, Any] = {
            "date": r.date,
            "sleep_score": r.sleep_score,
            "deep_minutes": r.deep_minutes,
            "rem_minutes": r.rem_minutes,
            "avg_hrv": r.avg_hrv,
            "onset_latency_minutes": r.onset_latency_minutes,
            "sleep_efficiency": r.sleep_efficiency,
            "total_sleep_minutes": r.total_sleep_minutes,
        }

        # Derived time columns
        if r.bedtime is not None:
            row["bedtime_hour"] = _normalize_bedtime_hour(r.bedtime)
        else:
            row["bedtime_hour"] = None

        if r.wake_time is not None:
            row["wake_hour"] = r.wake_time.hour + r.wake_time.minute / 60
        else:
            row["wake_hour"] = None

        if r.bedtime is not None and r.wake_time is not None:
            bed_h = _normalize_bedtime_hour(r.bedtime)
            wake_h = r.wake_time.hour + r.wake_time.minute / 60
            # Ensure wake is always "after" bedtime in the 24+ hour space.
            # E.g. bedtime 22.5, wake 6.5 → 6.5 < 22.5 → wake becomes 30.5
            if wake_h < bed_h:
                wake_h += 24
            row["sleep_midpoint_hour"] = (bed_h + wake_h) / 2
        else:
            row["sleep_midpoint_hour"] = None

        row["is_weekend"] = r.date.weekday() >= 5

        sleep_rows.append(row)

    sleep_df = pd.DataFrame(sleep_rows)
    sleep_df.set_index("date", inplace=True)

    # Query all daily logs with eager-loaded sub-entries
    daily_logs = (
        db.query(DailyLog)
        .options(
            joinedload(DailyLog.caffeine_entries),
            joinedload(DailyLog.meal_entries),
            # #161 Lane 2: eager-load the library product with each supplement
            # entry so per-product columns/labels don't trigger an N+1.
            joinedload(DailyLog.supplement_entries).joinedload(SupplementEntry.product),
            joinedload(DailyLog.habit_entries),
            joinedload(DailyLog.stimulating_activity_entries),
            joinedload(DailyLog.sexual_activity_entry),
            joinedload(DailyLog.pre_bed_ritual_entries),
            joinedload(DailyLog.nap_entries),
            joinedload(DailyLog.sunlight_entries),
            joinedload(DailyLog.red_light_entries),
            joinedload(DailyLog.nsdr_entries),
            joinedload(DailyLog.section_absences),
        )
        .order_by(DailyLog.date)
        .all()
    )

    # #161 Lane 2: labels + effect increments for the dynamic per-product
    # supplement columns, keyed by the observed library products (product name
    # is not known to the module-level VARIABLE_LABELS/_EFFECT_INCREMENTS).
    supplement_labels: dict[str, str] = {}
    supplement_increments: dict[str, tuple[float, str]] = {}

    if daily_logs:
        log_rows = []
        for log in daily_logs:
            row = _aggregate_daily_log(log)
            row["date"] = log.date
            log_rows.append(row)
            for entry in log.supplement_entries:
                if entry.product is None:
                    continue
                product = entry.product
                pid = product.id
                dose_col = f"{_SUPP_DOSE_PREFIX}{pid}"
                hbb_col = f"{_SUPP_HBB_PREFIX}{pid}"
                # Product-level distinction is the point (#161): two products
                # sharing a name but differing by brand/form must get DISTINCT
                # labels, or a correlation can't tell the user which one it is
                # (Codex P2, Lane 2 review). Include brand + form when present.
                _parts = [product.name]
                if product.brand:
                    _parts.append(product.brand)
                if product.form:
                    _parts.append(product.form)
                _base = " · ".join(_parts)
                supplement_labels[dose_col] = f"{_base} (dose)"
                supplement_labels[hbb_col] = f"{_base} — timing before bed"
                supplement_increments[dose_col] = (1.0, f"1 {product.unit}")
                supplement_increments[hbb_col] = (1.0, "hour earlier")

        log_df = pd.DataFrame(log_rows)
        log_df.set_index("date", inplace=True)

        # Left join: keep all sleep dates, merge in daily log data
        df = sleep_df.join(log_df, how="outer")
    else:
        df = sleep_df

    df.index.name = "date"
    df.sort_index(inplace=True)

    # Rolling consistency columns on bedtime_hour
    if "bedtime_hour" in df.columns:
        df["sigma_7d"] = df["bedtime_hour"].rolling(window=7, min_periods=3).std() * 60
        mean_7d = df["bedtime_hour"].rolling(window=7, min_periods=3).mean()
        df["delta_7d"] = (df["bedtime_hour"] - mean_7d).abs() * 60
    else:
        df["sigma_7d"] = np.nan
        df["delta_7d"] = np.nan

    # #161 Lane 2: convert each per-product "taken hour" (evening clock) into
    # hours-before-bedtime now that bedtime_hour is joined in. Both use the
    # same evening-clock normalization, so the subtraction is well-defined
    # (e.g. taken 21.25 / bedtime 23.0 → 1.75h before bed). Rows without a
    # timed entry or without a bedtime yield NaN (not recorded). The temporary
    # taken-hour columns are dropped so only the hbb predictor is exposed.
    # bedtime_hour is always a column here (added for every sleep row above,
    # and we only reach this point when sleep records exist).
    taken_cols = [c for c in df.columns if c.startswith(_SUPP_TAKEN_HOUR_PREFIX)]
    for tcol in taken_cols:
        pid_str = tcol[len(_SUPP_TAKEN_HOUR_PREFIX) :]
        df[f"{_SUPP_HBB_PREFIX}{pid_str}"] = df["bedtime_hour"] - df[tcol]
    if taken_cols:
        df = df.drop(columns=taken_cols)

    df.attrs["supplement_labels"] = supplement_labels
    df.attrs["supplement_increments"] = supplement_increments

    return df


def get_data_status(df: pd.DataFrame) -> dict[str, Any]:
    """Compute per-variable day counts and phase unlock status."""
    if df.empty:
        return {
            "total_sleep_days": 0,
            "phase_a_unlocked": False,
            "phase_b_unlocked": False,
            "phase_c_unlocked": False,
            "variables": [],
        }

    all_columns = [c for c in PREDICTOR_COLUMNS + OUTCOME_COLUMNS if c in df.columns]
    total_sleep = int(df["sleep_score"].notna().sum()) if "sleep_score" in df.columns else 0

    variables = []
    max_n = 0
    for col in all_columns:
        n = int(df[col].notna().sum())
        if n > max_n:
            max_n = n
        variables.append(
            {
                "name": col,
                "label": VARIABLE_LABELS.get(col, col),
                "n_days": n,
                "has_correlations": n >= 14,
                "has_regression": n >= 50,
            }
        )

    # Check bedtime data for phase C
    bedtime_days = int(df["bedtime_hour"].notna().sum()) if "bedtime_hour" in df.columns else 0

    return {
        "total_sleep_days": total_sleep,
        "phase_a_unlocked": any(v["has_correlations"] for v in variables),
        "phase_b_unlocked": any(v["has_regression"] for v in variables),
        "phase_c_unlocked": bedtime_days >= 30,
        "variables": variables,
    }


def _confidence_level(n: int) -> str:
    """Classify sample size confidence."""
    if n >= 50:
        return "high"
    if n >= 30:
        return "moderate"
    return "low"


# ---------------------------------------------------------------------------
# #17: effect sizes in natural units — slope headline + binned contrast.
# r stays in the payload but is demoted in the UI; these are what users read.
# ---------------------------------------------------------------------------

# Natural increment per predictor: (increment in column units, display label).
# The slope headline reads "≈X <outcome unit> per <label>".
_EFFECT_INCREMENTS: dict[str, tuple[float, str]] = {
    "total_caffeine_mg": (100, "100 mg"),
    "last_caffeine_hour": (1, "hour later"),
    "last_meal_hour": (1, "hour later"),
    "exercise_duration_minutes": (30, "30 min"),
    "stress_level": (1, "point"),
    "room_temp_f": (5, "5°F"),
    "stimulating_minutes": (30, "30 min"),
    "stimulating_last_hour": (1, "hour later"),
    "nap_total_minutes": (30, "30 min"),
    "nap_count": (1, "nap"),
    "sunlight_morning_minutes": (30, "30 min"),
    "sunlight_first_hour": (1, "hour later"),
    "red_light_dose_j_cm2": (10, "10 J/cm²"),
    "nsdr_total_minutes": (15, "15 min"),
    "ritual_total_minutes": (15, "15 min"),
    "sigma_7d": (15, "15 min"),
    "delta_7d": (15, "15 min"),
    "bedtime_hour": (1, "hour later"),
}

# Outcome display units for the slope headline. sleep_efficiency is stored
# as a 0-1 fraction — scaled to percentage points for display.
_OUTCOME_UNITS: dict[str, str] = {
    "sleep_score": "points",
    "deep_minutes": "min",
    "rem_minutes": "min",
    "avg_hrv": "ms",
    "onset_latency_minutes": "min",
    "sleep_efficiency": "% pts",
    "total_sleep_minutes": "min",
}

# Clock-time predictors whose scale supports "hour later" slopes and
# clock-labeled bin cutoffs: bedtime_hour, last_caffeine_hour,
# last_meal_hour, and stimulating_last_hour are all on the continuous 24+
# evening clock (see _normalize_bedtime_hour / _evening_time_to_hour: early
# hours shift to 24+ — before 6 AM for bedtime, before 4 AM for consumption
# events per #142 — fixed in #134), and sunlight_first_hour is a
# genuine morning clock time (0-12) — all are monotonic in "later", so
# slopes and cutoffs are meaningful and _fmt_clock renders them correctly.
_HOUR_PREDICTORS = {
    "bedtime_hour",
    "last_caffeine_hour",
    "last_meal_hour",
    "stimulating_last_hour",
    "sunlight_first_hour",
}

_CONTRAST_MIN_PER_BIN = 5


def _fmt_clock(hour: float) -> str:
    """24.5 → "12:30 AM"; 23.25 → "11:15 PM" (evening-clock aware)."""
    h = hour % 24
    minutes = round(h * 60)
    hh, mm = divmod(minutes, 60)
    hh %= 24
    suffix = "AM" if hh < 12 else "PM"
    display_h = hh % 12 or 12
    return f"{display_h}:{mm:02d} {suffix}"


def _cutoff_label(pred: str, cutoff: float) -> str:
    if pred in _HOUR_PREDICTORS:
        return _fmt_clock(cutoff)
    return f"{cutoff:g}"


def _effect_size(
    pred: str,
    outcome: str,
    subset: pd.DataFrame,
    pearson_r: float,
    extra_increments: dict[str, tuple[float, str]] | None = None,
) -> dict[str, Any] | None:
    """Slope in natural units per predictor increment, or None (binary /
    unmapped predictors have no meaningful per-unit slope).

    ``extra_increments`` supplies increments for dynamic columns not known at
    module level (#161: per-product supplement dose/timing); a column with no
    mapping in either source degrades gracefully to None."""
    inc = _EFFECT_INCREMENTS.get(pred)
    if inc is None and extra_increments is not None:
        inc = extra_increments.get(pred)
    if inc is None:
        return None
    increment, increment_label = inc
    sd_x = float(subset[pred].std())
    sd_y = float(subset[outcome].std())
    if sd_x == 0:
        return None
    slope = pearson_r * sd_y / sd_x
    value = slope * increment
    if outcome == "sleep_efficiency":
        value *= 100  # fraction → percentage points
    return {
        "value": round(value, 2),
        "increment_label": increment_label,
        "outcome_unit": _OUTCOME_UNITS.get(outcome, ""),
    }


def _binned_contrast(pred: str, outcome: str, subset: pd.DataFrame) -> dict[str, Any] | None:
    """Median-split evidence line: outcome means below vs above the cutoff.

    None when either bin is under _CONTRAST_MIN_PER_BIN (ties on the median
    can empty the high bin — e.g. zero-heavy predictors)."""
    cutoff = float(subset[pred].median())
    low = subset[subset[pred] <= cutoff]
    high = subset[subset[pred] > cutoff]
    if len(low) < _CONTRAST_MIN_PER_BIN or len(high) < _CONTRAST_MIN_PER_BIN:
        return None
    low_mean = float(low[outcome].mean())
    high_mean = float(high[outcome].mean())
    if outcome == "sleep_efficiency":
        low_mean *= 100
        high_mean *= 100
    label = _cutoff_label(pred, cutoff)
    if pred in _HOUR_PREDICTORS:
        # The low bin is <= cutoff, so "before X" would misstate cutoff-equal
        # rows — say "X or earlier" instead.
        low_label, high_label = f"{label} or earlier", f"after {label}"
    else:
        low_label, high_label = f"≤ {label}", f"> {label}"
    return {
        "low_label": low_label,
        "high_label": high_label,
        "low_mean": round(low_mean, 1),
        "high_mean": round(high_mean, 1),
        "n_low": len(low),
        "n_high": len(high),
    }


def compute_correlations(
    df: pd.DataFrame,
    min_days: int = 14,
) -> tuple[list[dict[str, Any]], int]:
    """Compute pairwise correlations between predictors and outcomes.

    Returns (results, excluded_sick_days).
    """
    if df.empty:
        return [], 0

    # #161 Lane 2: dynamic per-product supplement label/increment maps attached
    # by prepare_analysis_dataframe. Read before any df reassignment so a slice
    # that might not carry .attrs can't drop them.
    supplement_labels: dict[str, str] = df.attrs.get("supplement_labels", {})
    supplement_increments: dict[str, tuple[float, str]] = df.attrs.get("supplement_increments", {})

    # Filter sick days
    sick_count = 0
    if "is_sick" in df.columns:
        sick_mask = df["is_sick"] == True  # noqa: E712
        sick_count = int(sick_mask.sum())
        df = df[~sick_mask]

    results: list[dict[str, Any]] = []

    # Static predictors + dynamically-discovered per-product supplement columns
    # (#161). The min_days + variance + NaN gates below apply unchanged, so a
    # rarely-logged product (<14 days) or a zero-variance product is skipped.
    predictors = [c for c in PREDICTOR_COLUMNS if c in df.columns] + [
        c for c in df.columns if c.startswith("supplement_")
    ]
    outcomes = [c for c in OUTCOME_COLUMNS if c in df.columns]

    for pred in predictors:
        for outcome in outcomes:
            subset = df[[pred, outcome]].dropna()
            n = len(subset)
            if n < min_days:
                continue

            # Need variance in both columns
            if subset[pred].std() == 0 or subset[outcome].std() == 0:
                continue

            pearson_r, p_val = stats.pearsonr(subset[pred], subset[outcome])
            spearman_r, _ = stats.spearmanr(subset[pred], subset[outcome])

            # Skip if result is NaN (can happen with near-constant data)
            if np.isnan(pearson_r) or np.isnan(spearman_r):
                continue

            results.append(
                {
                    "predictor": pred,
                    "predictor_label": supplement_labels.get(pred)
                    or VARIABLE_LABELS.get(pred, pred),
                    "outcome": outcome,
                    "outcome_label": VARIABLE_LABELS.get(outcome, outcome),
                    "pearson_r": round(float(pearson_r), 4),
                    "spearman_r": round(float(spearman_r), 4),
                    "p_value": round(float(p_val), 6),
                    "n_days": n,
                    "confidence": _confidence_level(n),
                    "effect": _effect_size(
                        pred, outcome, subset, float(pearson_r), supplement_increments
                    ),
                    "contrast": _binned_contrast(pred, outcome, subset),
                }
            )

    # Sort by absolute pearson_r descending
    results.sort(key=lambda r: abs(r["pearson_r"]), reverse=True)

    return results, sick_count


def detect_outliers(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    z_threshold: float = 3.0,
) -> dict[str, list[Any]]:
    """Detect outliers using z-score method.

    Returns dict mapping column name to list of (date, value, z_score) tuples.
    """
    if df.empty:
        return {}

    if columns is None:
        columns = [c for c in OUTCOME_COLUMNS + PREDICTOR_COLUMNS if c in df.columns]

    outliers: dict[str, list[Any]] = {}

    for col in columns:
        if col not in df.columns:
            continue

        series = df[col].dropna()
        if len(series) < 3:
            continue

        mean = series.mean()
        std = series.std()
        if std == 0:
            continue

        z_scores = (series - mean) / std
        mask = z_scores.abs() > z_threshold

        if mask.any():
            outliers[col] = [
                {
                    "date": str(idx),
                    "value": round(float(series[idx]), 2),
                    "z_score": round(float(z_scores[idx]), 2),
                }
                for idx in z_scores[mask].index
            ]

    return outliers


def compute_regression(
    df: pd.DataFrame,
    outcome: str,
    min_days: int = 50,
) -> dict[str, Any] | None:
    """Fit OLS regression for a single outcome variable.

    Returns None if insufficient data.
    """
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tsa.stattools import acf, adfuller

    if df.empty or outcome not in df.columns:
        return None

    # Filter sick days
    work_df = df.copy()
    if "is_sick" in work_df.columns:
        work_df = work_df[work_df["is_sick"] != True]  # noqa: E712

    # Select predictors with enough non-NaN data
    available_predictors = []
    for col in PREDICTOR_COLUMNS:
        if col not in work_df.columns:
            continue
        n_valid = work_df[[col, outcome]].dropna().shape[0]
        if n_valid >= min_days:
            available_predictors.append(col)

    if not available_predictors:
        return None

    # Add lag-1 of outcome as autoregressive predictor
    work_df[f"{outcome}_lag1"] = work_df[outcome].shift(1)
    all_predictors = [*available_predictors, f"{outcome}_lag1"]

    # Drop rows with any NaN in selected columns
    cols_needed = [outcome, *all_predictors]
    cols_present = [c for c in cols_needed if c in work_df.columns]
    clean_df = work_df[cols_present].dropna()

    if len(clean_df) < min_days:
        return None

    y = clean_df[outcome]
    x = clean_df[[c for c in all_predictors if c in clean_df.columns]]

    # Standardize predictors for comparable coefficients
    x_means = x.mean()
    x_stds = x.std()
    # Avoid division by zero for constant columns
    x_stds = x_stds.replace(0, 1)
    x_scaled = (x - x_means) / x_stds

    x_const = sm.add_constant(x_scaled)

    try:
        model = sm.OLS(y, x_const).fit()
    except Exception:
        return None

    # Compute VIF for each predictor
    excluded_predictors: list[str] = []
    multicollinearity_warning = False
    vif_values: dict[str, float | None] = {}

    if x_scaled.shape[1] > 1:
        for i, col in enumerate(x_scaled.columns):
            try:
                vif = variance_inflation_factor(x_scaled.values, i)
                if np.isfinite(vif):
                    vif_values[col] = round(float(vif), 2)
                    if vif > 5.0:
                        multicollinearity_warning = True
                else:
                    vif_values[col] = None
            except Exception:
                vif_values[col] = None

    # ADF test on residuals; statsmodels can fail on degenerate residuals,
    # in which case we keep the optimistic default
    is_stationary = True
    with contextlib.suppress(Exception):
        adf_result = adfuller(model.resid, autolag="AIC")
        is_stationary = bool(adf_result[1] < 0.05)

    # ACF on residuals — check for autocorrelation (same degenerate-data fallback)
    has_autocorrelation = False
    with contextlib.suppress(Exception):
        acf_values = acf(model.resid, nlags=5, fft=False)
        # Significant if any lag 1-5 exceeds 2/sqrt(n) threshold
        threshold = 2 / np.sqrt(len(model.resid))
        has_autocorrelation = bool(
            any(abs(acf_values[i]) > threshold for i in range(1, min(6, len(acf_values))))
        )

    # Sanitize r_squared values
    r_sq = float(model.rsquared)
    adj_r_sq = float(model.rsquared_adj)
    if not np.isfinite(r_sq):
        r_sq = 0.0
    if not np.isfinite(adj_r_sq):
        adj_r_sq = 0.0

    # Build coefficient list (skip constant)
    coefficients = []
    predictor_cols = [c for c in all_predictors if c in clean_df.columns]
    for col in predictor_cols:
        if col not in model.params.index:
            continue
        coef = float(model.params[col])
        ci = model.conf_int().loc[col]
        p_val = float(model.pvalues[col])

        # Skip coefficients with non-finite values
        if not np.isfinite(coef) or not np.isfinite(p_val):
            continue

        coefficients.append(
            {
                "predictor": col,
                "predictor_label": VARIABLE_LABELS.get(col, col),
                "coefficient": round(coef, 4),
                "ci_lower": round(float(ci[0]), 4) if np.isfinite(ci[0]) else None,
                "ci_upper": round(float(ci[1]), 4) if np.isfinite(ci[1]) else None,
                "p_value": round(p_val, 6),
                "is_significant": p_val < 0.05,
                "vif": vif_values.get(col),
            }
        )

    return {
        "outcome": outcome,
        "outcome_label": VARIABLE_LABELS.get(outcome, outcome),
        "n_days": len(clean_df),
        "r_squared": round(r_sq, 4),
        "adj_r_squared": round(adj_r_sq, 4),
        "coefficients": coefficients,
        "has_autocorrelation": has_autocorrelation,
        "is_stationary": is_stationary,
        "multicollinearity_warning": multicollinearity_warning,
        "excluded_predictors": excluded_predictors,
    }
