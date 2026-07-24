"""Tests for the statistical analysis engine."""

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from backend.models import (
    CaffeineEntry,
    DailyLog,
    HabitEntry,
    HabitType,
    MealEntry,
    NapEntry,
    SectionAbsence,
    SleepRecord,
    StimulatingActivityEntry,
    StimulatingActivityType,
    SunlightEntry,
    SupplementEntry,
    SupplementProduct,
)
from backend.services.stats_engine import (
    OUTCOME_COLUMNS,
    PREDICTOR_COLUMNS,
    VARIABLE_LABELS,
    compute_correlations,
    compute_regression,
    detect_outliers,
    get_data_status,
    prepare_analysis_dataframe,
)

# --- Helpers ---


def _make_sleep_record(db: Session, date: dt.date, **kwargs: Any) -> SleepRecord:
    defaults = {
        "sleep_score": 80,
        "deep_minutes": 70,
        "rem_minutes": 90,
        "light_minutes": 250,
        "total_sleep_minutes": 410,
        "sleep_efficiency": 0.92,
        "onset_latency_minutes": 10,
        "avg_hrv": 45.0,
        "bedtime": dt.datetime.combine(date - dt.timedelta(days=1), dt.time(22, 30)),
        "wake_time": dt.datetime.combine(date, dt.time(6, 20)),
    }
    defaults.update(kwargs)
    rec = SleepRecord(date=date, **defaults)
    db.add(rec)
    return rec


def _make_daily_log(db: Session, date: dt.date, **kwargs: Any) -> DailyLog:
    log = DailyLog(date=date, **kwargs)
    db.add(log)
    return log


def _seed_correlated_data(db: Session, n: int = 30, positive: bool = True) -> None:
    """Seed n days of perfectly correlated caffeine → sleep_score data."""
    base_date = dt.date(2025, 1, 1)
    for i in range(n):
        d = base_date + dt.timedelta(days=i)
        caffeine_mg = 100 + i * 10
        score = 60 + i if positive else 90 - i

        _make_sleep_record(db, d, sleep_score=score)
        _make_daily_log(db, d)
        db.add(
            CaffeineEntry(
                date=d,
                time=dt.time(8, 0),
                amount_mg=caffeine_mg,
                source="drip_coffee",
            )
        )
    db.commit()


# --- prepare_analysis_dataframe tests ---


class TestPrepareAnalysisDataframe:
    def test_empty_db(self, db: Session) -> None:
        df = prepare_analysis_dataframe(db)
        assert df.empty

    def test_sleep_records_only(self, db: Session) -> None:
        _make_sleep_record(db, dt.date(2025, 1, 1))
        _make_sleep_record(db, dt.date(2025, 1, 2))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert len(df) == 2
        assert "sleep_score" in df.columns
        assert "bedtime_hour" in df.columns

    def test_daily_logs_only(self, db: Session) -> None:
        """Daily logs without sleep records → empty DataFrame (no outcomes)."""
        _make_daily_log(db, dt.date(2025, 1, 1))
        db.add(
            CaffeineEntry(
                date=dt.date(2025, 1, 1),
                time=dt.time(8, 0),
                amount_mg=200,
                source="espresso",
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        # No sleep records means nothing to analyze
        assert df.empty

    def test_joined_data(self, db: Session) -> None:
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(
            CaffeineEntry(
                date=d,
                time=dt.time(8, 0),
                amount_mg=150,
                source="drip_coffee",
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert len(df) == 1
        assert df.iloc[0]["total_caffeine_mg"] == 150
        assert df.iloc[0]["sleep_score"] == 80

    def test_null_handling_nan_not_zero(self, db: Session) -> None:
        """Missing data should be NaN, never zero (ADR 003)."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)  # No caffeine entries
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert pd.isna(df.iloc[0]["total_caffeine_mg"])

    def test_bedtime_hour_normalization(self, db: Session) -> None:
        """Bedtime after midnight should be 24+ hours."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(
            db,
            d,
            bedtime=dt.datetime(2024, 12, 31, 0, 30),  # 12:30 AM
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["bedtime_hour"] == pytest.approx(24.5)

    def test_sigma_7d_is_in_minutes(self, db: Session) -> None:
        """sigma_7d is bedtime stddev in MINUTES — pins the ×60 in
        prepare_analysis_dataframe. A 22:00/23:00 alternation over 7 days is
        ~32 min of spread; without the ×60 it would read ~0.53."""
        base = dt.date(2025, 1, 1)
        for i in range(7):
            d = base + dt.timedelta(days=i)
            hour = 22 if i % 2 == 0 else 23
            _make_sleep_record(
                db,
                d,
                bedtime=dt.datetime.combine(d - dt.timedelta(days=1), dt.time(hour, 0)),
            )
        db.commit()

        df = prepare_analysis_dataframe(db)
        sigma = float(df.iloc[-1]["sigma_7d"])
        # hours [22,23,22,23,22,23,22]: sample std ≈ 0.5345 h → 32.07 min
        assert sigma == pytest.approx(0.5345 * 60, abs=0.1)

    def test_sleep_midpoint_computed(self, db: Session) -> None:
        """Bedtime 10 PM, wake 6 AM → midpoint should be ~2 AM (26.0 in 24+ space)."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(
            db,
            d,
            bedtime=dt.datetime(2024, 12, 31, 22, 0),  # 10 PM
            wake_time=dt.datetime(2025, 1, 1, 6, 0),  # 6 AM
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        # bed_h = 22.0, wake_h = 6.0, since 6.0 < 22.0 → wake_h = 30.0
        # midpoint = (22.0 + 30.0) / 2 = 26.0 (= 2:00 AM)
        assert df.iloc[0]["sleep_midpoint_hour"] == pytest.approx(26.0)

    def test_sleep_midpoint_wake_before_6am(self, db: Session) -> None:
        """Bedtime 11 PM, wake 5 AM → midpoint ~2 AM (26.0)."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(
            db,
            d,
            bedtime=dt.datetime(2024, 12, 31, 23, 0),
            wake_time=dt.datetime(2025, 1, 1, 5, 0),
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        # bed_h = 23.0, wake_h = 5.0, since 5.0 < 23.0 → wake_h = 29.0
        # midpoint = (23.0 + 29.0) / 2 = 26.0
        assert df.iloc[0]["sleep_midpoint_hour"] == pytest.approx(26.0)

    def test_sleep_midpoint_late_bedtime_late_wake(self, db: Session) -> None:
        """Bedtime 1 AM, wake 9 AM → midpoint 5 AM (29.0)."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(
            db,
            d,
            bedtime=dt.datetime(2025, 1, 1, 1, 0),
            wake_time=dt.datetime(2025, 1, 1, 9, 0),
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        # bed_h = 1.0 → normalized to 25.0 (< 6 shift)
        # wake_h = 9.0, since 9.0 < 25.0 → wake_h = 33.0
        # midpoint = (25.0 + 33.0) / 2 = 29.0 (= 5:00 AM)
        assert df.iloc[0]["sleep_midpoint_hour"] == pytest.approx(29.0)

    def test_sleep_midpoint_typical_scenario(self, db: Session) -> None:
        """Bedtime 10:30 PM, wake 6:30 AM → midpoint 2:30 AM (26.5)."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(
            db,
            d,
            bedtime=dt.datetime(2024, 12, 31, 22, 30),
            wake_time=dt.datetime(2025, 1, 1, 6, 30),
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        # bed_h = 22.5, wake_h = 6.5, since 6.5 < 22.5 → wake_h = 30.5
        # midpoint = (22.5 + 30.5) / 2 = 26.5 (= 2:30 AM)
        assert df.iloc[0]["sleep_midpoint_hour"] == pytest.approx(26.5)

    def test_is_weekend_flag(self, db: Session) -> None:
        # 2025-01-04 is a Saturday
        _make_sleep_record(db, dt.date(2025, 1, 4))
        # 2025-01-06 is a Monday
        _make_sleep_record(db, dt.date(2025, 1, 6))
        db.commit()

        df = prepare_analysis_dataframe(db)
        saturday_row = df.loc[dt.date(2025, 1, 4)]
        monday_row = df.loc[dt.date(2025, 1, 6)]
        assert saturday_row["is_weekend"] == True  # noqa: E712
        assert monday_row["is_weekend"] == False  # noqa: E712

    def test_habit_aggregation(self, db: Session) -> None:
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(HabitEntry(date=d, habit_type=HabitType.ALCOHOL, time=dt.time(19, 0)))
        db.add(HabitEntry(date=d, habit_type=HabitType.EXERCISE, duration_minutes=45))
        db.add(HabitEntry(date=d, habit_type=HabitType.STRESS_LEVEL, value="7"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["alcohol"] == 1.0
        assert df.iloc[0]["exercise_done"] == 1.0
        assert df.iloc[0]["exercise_duration_minutes"] == 45
        assert df.iloc[0]["stress_level"] == 7.0

    def test_rolling_consistency(self, db: Session) -> None:
        """sigma_7d and delta_7d are computed from bedtime_hour rolling window."""
        base = dt.date(2025, 1, 1)
        for i in range(7):
            d = base + dt.timedelta(days=i)
            # Vary bedtime between 22:00 and 22:55
            minute = (i * 8) % 60
            bt = dt.datetime.combine(d - dt.timedelta(days=1), dt.time(22, minute))
            _make_sleep_record(db, d, bedtime=bt)
        db.commit()

        df = prepare_analysis_dataframe(db)
        # After 7 days, rolling window should have values
        assert not pd.isna(df.iloc[-1]["sigma_7d"])

    def test_sunlight_aggregation(self, db: Session) -> None:
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(SunlightEntry(date=d, start_time=dt.time(7, 30), duration_minutes=20))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["sunlight_morning_minutes"] == 20
        assert df.iloc[0]["sunlight_first_hour"] == pytest.approx(7.5)

    def test_last_caffeine_hour_after_midnight_evening_clock(self, db: Session) -> None:
        """#134: an after-midnight caffeine entry is on the 24+ evening clock
        (00:30 → 24.5) and beats an 11 PM entry as the day's last."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(CaffeineEntry(date=d, time=dt.time(23, 0), amount_mg=50, source="tea"))
        db.add(CaffeineEntry(date=d, time=dt.time(0, 30), amount_mg=50, source="tea"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["last_caffeine_hour"] == pytest.approx(24.5)

    def test_last_caffeine_hour_daytime_unwrapped(self, db: Session) -> None:
        """Daytime times (>= 4 AM, the #142 cutoff) stay on the plain clock."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(CaffeineEntry(date=d, time=dt.time(8, 0), amount_mg=100, source="drip_coffee"))
        db.add(CaffeineEntry(date=d, time=dt.time(14, 30), amount_mg=50, source="tea"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["last_caffeine_hour"] == pytest.approx(14.5)

    def test_last_meal_hour_after_midnight_evening_clock(self, db: Session) -> None:
        """#134: a flagged is_last_meal at 00:30 → 24.5, not 0.5."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(MealEntry(date=d, time=dt.time(19, 0)))
        db.add(MealEntry(date=d, time=dt.time(0, 30), is_last_meal=True))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["last_meal_hour"] == pytest.approx(24.5)

    def test_last_meal_hour_max_after_wrap(self, db: Session) -> None:
        """#134: without an is_last_meal flag, the max is taken AFTER the
        evening-clock wrap — 00:15 (24.25) beats 20:00."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(MealEntry(date=d, time=dt.time(20, 0)))
        db.add(MealEntry(date=d, time=dt.time(0, 15)))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["last_meal_hour"] == pytest.approx(24.25)

    def test_stimulating_last_hour_after_midnight_evening_clock(self, db: Session) -> None:
        """#134: a stimulating activity ending at 01:00 → 25.0, later than
        one ending at 10 PM."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(
            StimulatingActivityEntry(
                date=d,
                end_time=dt.time(22, 0),
                activity_type=StimulatingActivityType.TV_MOVIES,
                duration_minutes=60,
            )
        )
        db.add(
            StimulatingActivityEntry(
                date=d,
                end_time=dt.time(1, 0),
                activity_type=StimulatingActivityType.VIDEO_GAMES,
                duration_minutes=30,
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["stimulating_last_hour"] == pytest.approx(25.0)

    def test_evening_clock_4am_cutoff_boundary(self) -> None:
        """#142 (owner-decided): consumption events wrap below exactly 4 AM —
        3:59 wraps to 27.983…, 4:00 stays at 4.0. Bedtime's cutoff stays 6 AM
        (see _normalize_bedtime_hour); a 5:30 AM coffee is morning, not
        post-midnight."""
        from backend.services.stats_engine import _evening_time_to_hour

        assert _evening_time_to_hour(dt.time(3, 59)) == pytest.approx(27.983, abs=0.001)
        assert _evening_time_to_hour(dt.time(4, 0)) == pytest.approx(4.0)
        assert _evening_time_to_hour(dt.time(5, 30)) == pytest.approx(5.5)

    def test_early_riser_coffee_loses_to_afternoon(self, db: Session) -> None:
        """#142 aggregation-level pin: a raw 5:00 AM entry stays morning and
        loses the per-day max to a 14:00 entry (pre-#142 it wrapped to 29.0
        and spuriously won as the day's 'last')."""
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(CaffeineEntry(date=d, time=dt.time(5, 0), amount_mg=100, source="drip_coffee"))
        db.add(CaffeineEntry(date=d, time=dt.time(14, 0), amount_mg=50, source="tea"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["last_caffeine_hour"] == pytest.approx(14.0)

    def test_nap_aggregation(self, db: Session) -> None:
        d = dt.date(2025, 1, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(NapEntry(date=d, start_time=dt.time(14, 0), duration_minutes=25))
        db.add(NapEntry(date=d, start_time=dt.time(16, 0), duration_minutes=15))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.iloc[0]["nap_total_minutes"] == 40
        assert df.iloc[0]["nap_count"] == 2.0


# --- get_data_status tests ---


class TestGetDataStatus:
    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        status = get_data_status(df)
        assert status["total_sleep_days"] == 0
        assert status["phase_a_unlocked"] is False
        assert status["phase_b_unlocked"] is False
        assert status["phase_c_unlocked"] is False

    def test_insufficient_data(self, db: Session) -> None:
        for i in range(10):
            _make_sleep_record(db, dt.date(2025, 1, 1) + dt.timedelta(days=i))
        db.commit()

        df = prepare_analysis_dataframe(db)
        status = get_data_status(df)
        assert status["total_sleep_days"] == 10
        assert status["phase_a_unlocked"] is False

    def test_phase_a_unlocked(self, db: Session) -> None:
        for i in range(15):
            d = dt.date(2025, 1, 1) + dt.timedelta(days=i)
            _make_sleep_record(db, d)
            _make_daily_log(db, d)
            db.add(CaffeineEntry(date=d, amount_mg=100, source="drip_coffee"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        status = get_data_status(df)
        assert status["phase_a_unlocked"] is True
        assert any(
            v["name"] == "total_caffeine_mg" and v["has_correlations"] for v in status["variables"]
        )

    def test_phase_c_requires_30_bedtime_days(self, db: Session) -> None:
        for i in range(30):
            d = dt.date(2025, 1, 1) + dt.timedelta(days=i)
            _make_sleep_record(db, d)
        db.commit()

        df = prepare_analysis_dataframe(db)
        status = get_data_status(df)
        assert status["phase_c_unlocked"] is True


# --- compute_correlations tests ---


class TestComputeCorrelations:
    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        results, sick = compute_correlations(df)
        assert results == []
        assert sick == 0

    def test_positive_correlation(self, db: Session) -> None:
        _seed_correlated_data(db, n=30, positive=True)
        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df)

        # Find caffeine → sleep_score correlation
        caff_score = [
            r
            for r in results
            if r["predictor"] == "total_caffeine_mg" and r["outcome"] == "sleep_score"
        ]
        assert len(caff_score) == 1
        assert caff_score[0]["pearson_r"] > 0.9  # Near-perfect positive

    def test_negative_correlation(self, db: Session) -> None:
        _seed_correlated_data(db, n=30, positive=False)
        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df)

        caff_score = [
            r
            for r in results
            if r["predictor"] == "total_caffeine_mg" and r["outcome"] == "sleep_score"
        ]
        assert len(caff_score) == 1
        assert caff_score[0]["pearson_r"] < -0.9  # Near-perfect negative

    def test_r_values_in_range(self, db: Session) -> None:
        _seed_correlated_data(db, n=30)
        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df)

        for r in results:
            assert -1.0 <= r["pearson_r"] <= 1.0
            assert -1.0 <= r["spearman_r"] <= 1.0

    def test_insufficient_data_skipped(self, db: Session) -> None:
        """Less than min_days pairs → no results."""
        for i in range(5):
            d = dt.date(2025, 1, 1) + dt.timedelta(days=i)
            _make_sleep_record(db, d)
            _make_daily_log(db, d)
            db.add(CaffeineEntry(date=d, amount_mg=100 + i * 10, source="drip_coffee"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df, min_days=14)
        # Not enough days for any correlation
        caff_results = [r for r in results if r["predictor"] == "total_caffeine_mg"]
        assert len(caff_results) == 0

    def test_sick_days_excluded(self, db: Session) -> None:
        _seed_correlated_data(db, n=20)
        # Add sick days
        for i in range(20, 25):
            d = dt.date(2025, 1, 1) + dt.timedelta(days=i)
            _make_sleep_record(db, d, sleep_score=30)
            _make_daily_log(db, d, is_sick=True)
            db.add(CaffeineEntry(date=d, amount_mg=0, source="other"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        _, sick_count = compute_correlations(df)
        assert sick_count == 5

    def test_sorted_by_abs_r(self, db: Session) -> None:
        _seed_correlated_data(db, n=30)
        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df)

        if len(results) > 1:
            for i in range(len(results) - 1):
                assert abs(results[i]["pearson_r"]) >= abs(results[i + 1]["pearson_r"])

    def test_confidence_levels(self, db: Session) -> None:
        _seed_correlated_data(db, n=20)
        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df, min_days=14)

        for r in results:
            if r["n_days"] < 30:
                assert r["confidence"] == "low"
            elif r["n_days"] < 50:
                assert r["confidence"] == "moderate"
            else:
                assert r["confidence"] == "high"


# --- detect_outliers tests ---


class TestDetectOutliers:
    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        assert detect_outliers(df) == {}

    def test_no_outliers(self) -> None:
        # Normal-looking data
        data = {"sleep_score": [80, 82, 78, 81, 79, 83, 80, 82, 78, 81]}
        df = pd.DataFrame(data, index=pd.date_range("2025-01-01", periods=10))
        outliers = detect_outliers(df, columns=["sleep_score"])
        assert "sleep_score" not in outliers

    def test_detects_outlier(self) -> None:
        # One extreme value
        scores = [80] * 20 + [200]  # z > 3 for the outlier
        dates = pd.date_range("2025-01-01", periods=21)
        df = pd.DataFrame({"sleep_score": scores}, index=dates)
        outliers = detect_outliers(df, columns=["sleep_score"])
        assert "sleep_score" in outliers
        assert len(outliers["sleep_score"]) == 1

    def test_z_score_math(self) -> None:
        """Manually verify z-score calculation."""
        vals = [10.0] * 50 + [100.0]
        dates = pd.date_range("2025-01-01", periods=51)
        df = pd.DataFrame({"test_col": vals}, index=dates)

        mean = np.mean(vals)
        std = np.std(vals, ddof=1)
        expected_z = (100.0 - mean) / std

        outliers = detect_outliers(df, columns=["test_col"], z_threshold=3.0)
        if expected_z > 3.0:
            assert "test_col" in outliers


# --- compute_regression tests ---


class TestComputeRegression:
    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        assert compute_regression(df, "sleep_score") is None

    def test_insufficient_data(self, db: Session) -> None:
        for i in range(10):
            d = dt.date(2025, 1, 1) + dt.timedelta(days=i)
            _make_sleep_record(db, d)
            _make_daily_log(db, d)
            db.add(CaffeineEntry(date=d, amount_mg=100, source="drip_coffee"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert compute_regression(df, "sleep_score", min_days=50) is None

    def test_basic_regression(self, db: Session) -> None:
        """With enough correlated data, regression should return a result."""
        _seed_correlated_data(db, n=60, positive=False)
        df = prepare_analysis_dataframe(db)
        result = compute_regression(df, "sleep_score", min_days=14)

        assert result is not None
        assert result["outcome"] == "sleep_score"
        assert 0 <= result["r_squared"] <= 1.0
        assert len(result["coefficients"]) > 0

    def test_regression_coefficients_have_ci(self, db: Session) -> None:
        _seed_correlated_data(db, n=60)
        df = prepare_analysis_dataframe(db)
        result = compute_regression(df, "sleep_score", min_days=14)

        assert result is not None
        for coef in result["coefficients"]:
            assert "ci_lower" in coef
            assert "ci_upper" in coef
            assert coef["ci_lower"] <= coef["ci_upper"]

    def test_regression_stationarity_check(self, db: Session) -> None:
        _seed_correlated_data(db, n=60)
        df = prepare_analysis_dataframe(db)
        result = compute_regression(df, "sleep_score", min_days=14)

        assert result is not None
        assert isinstance(result["is_stationary"], bool)
        assert isinstance(result["has_autocorrelation"], bool)


# --- Variable labels coverage ---


class TestVariableLabels:
    def test_all_columns_have_labels(self) -> None:
        for col in OUTCOME_COLUMNS + PREDICTOR_COLUMNS:
            assert col in VARIABLE_LABELS, f"Missing label for {col}"


# ---------------------------------------------------------------------------
# #17: effect sizes — slope headline + binned contrast + clock labels
# ---------------------------------------------------------------------------


class TestEffectSizes:
    def test_fmt_clock_evening_and_after_midnight(self) -> None:
        from backend.services.stats_engine import _fmt_clock

        assert _fmt_clock(23.5) == "11:30 PM"
        assert _fmt_clock(24.5) == "12:30 AM"  # 00:30 on the 24+ evening scale
        assert _fmt_clock(23.25) == "11:15 PM"
        assert _fmt_clock(12.0) == "12:00 PM"
        assert _fmt_clock(0.0) == "12:00 AM"

    def test_cutoff_label_hour_vs_plain(self) -> None:
        from backend.services.stats_engine import _cutoff_label

        assert _cutoff_label("bedtime_hour", 24.5) == "12:30 AM"  # hour predictor
        assert _cutoff_label("total_caffeine_mg", 150.0) == "150"  # plain number

    def test_effect_size_slope_natural_units(self) -> None:
        from backend.services.stats_engine import _effect_size

        # Construct data with a known slope: score drops ~3 pts per bedtime hour.
        hours = [23.0, 23.5, 24.0, 24.5, 25.0, 25.5]
        scores = [90.0, 88.5, 87.0, 85.5, 84.0, 82.5]  # exactly -3/hour
        df = pd.DataFrame({"bedtime_hour": hours, "sleep_score": scores})
        r = float(df["bedtime_hour"].corr(df["sleep_score"]))  # -1.0 here
        eff = _effect_size("bedtime_hour", "sleep_score", df, r)
        assert eff is not None
        assert eff["increment_label"] == "hour later"
        assert eff["outcome_unit"] == "points"
        assert eff["value"] == pytest.approx(-3.0, abs=0.05)

    def test_effect_size_per_100mg_increment(self) -> None:
        from backend.services.stats_engine import _effect_size

        mg = [0.0, 100.0, 200.0, 300.0, 400.0]
        score = [88.0, 86.0, 84.0, 82.0, 80.0]  # -2 pts per 100mg
        df = pd.DataFrame({"total_caffeine_mg": mg, "sleep_score": score})
        r = float(df["total_caffeine_mg"].corr(df["sleep_score"]))
        eff = _effect_size("total_caffeine_mg", "sleep_score", df, r)
        assert eff is not None
        assert eff["increment_label"] == "100 mg"
        assert eff["value"] == pytest.approx(-2.0, abs=0.05)

    def test_effect_size_efficiency_scaled_to_pct_points(self) -> None:
        from backend.services.stats_engine import _effect_size

        mg = [0.0, 100.0, 200.0, 300.0]
        eff_frac = [0.95, 0.93, 0.91, 0.89]  # -0.02/100mg = -2 pct pts
        df = pd.DataFrame({"total_caffeine_mg": mg, "sleep_efficiency": eff_frac})
        r = float(df["total_caffeine_mg"].corr(df["sleep_efficiency"]))
        result = _effect_size("total_caffeine_mg", "sleep_efficiency", df, r)
        assert result is not None
        assert result["outcome_unit"] == "% pts"
        assert result["value"] == pytest.approx(-2.0, abs=0.05)

    def test_effect_size_none_for_unmapped_or_binary(self) -> None:
        from backend.services.stats_engine import _effect_size

        df = pd.DataFrame({"alcohol": [1.0, 1.0, 0.0], "sleep_score": [80.0, 82.0, 88.0]})
        # alcohol is not in _EFFECT_INCREMENTS (binary) → no per-unit slope
        assert _effect_size("alcohol", "sleep_score", df, -0.5) is None

    def test_effect_size_none_on_zero_variance(self) -> None:
        from backend.services.stats_engine import _effect_size

        df = pd.DataFrame({"bedtime_hour": [24.0, 24.0, 24.0], "sleep_score": [80.0, 85.0, 90.0]})
        assert _effect_size("bedtime_hour", "sleep_score", df, 0.0) is None

    def test_binned_contrast_hour_labels_and_means(self) -> None:
        from backend.services.stats_engine import _binned_contrast

        # 6 early (before midnight, good) + 6 late (after, worse); median splits them
        hours = [23.0, 23.2, 23.4, 23.6, 23.8, 23.9, 24.2, 24.4, 24.6, 24.8, 25.0, 25.2]
        scores = [88, 89, 90, 87, 88, 89, 82, 81, 80, 83, 79, 82]
        df = pd.DataFrame({"bedtime_hour": hours, "sleep_score": [float(s) for s in scores]})
        c = _binned_contrast("bedtime_hour", "sleep_score", df)
        assert c is not None
        # The low bin is <= cutoff, so the label says "or earlier", not "before".
        assert c["low_label"].endswith(" or earlier")
        assert c["high_label"].startswith("after ")
        assert c["low_mean"] > c["high_mean"]  # earlier bedtime, better score
        assert c["n_low"] >= 5 and c["n_high"] >= 5

    def test_binned_contrast_none_when_a_bin_too_small(self) -> None:
        from backend.services.stats_engine import _binned_contrast

        # zero-heavy: median is 0, so the high bin (>0) has too few rows
        vals = [0.0] * 10 + [50.0, 60.0]
        score = [85.0] * 12
        df = pd.DataFrame({"total_caffeine_mg": vals, "sleep_score": score})
        assert _binned_contrast("total_caffeine_mg", "sleep_score", df) is None

    def test_evening_clock_predictors_render_effects(self) -> None:
        """#134: last_caffeine_hour / last_meal_hour / stimulating_last_hour
        are now aggregated onto the 24+ evening clock (00:30 → 24.5), so the
        #132 display suppression is lifted: slopes render in "hour later"
        units and bins get clock-formatted cutoff labels straddling midnight
        (e.g. "12:15 AM or earlier")."""
        from backend.services.stats_engine import _binned_contrast, _effect_size

        # Evening-clock hours crossing midnight; median = (24.0+24.5)/2 = 24.25
        hours = [22.0, 22.5, 23.0, 23.25, 23.5, 24.0, 24.5, 24.75, 25.0, 25.25, 25.5, 26.0]
        scores = [90.0 - 2.0 * (h - 22.0) for h in hours]  # exactly -2 pts/hour
        for pred in ("last_caffeine_hour", "last_meal_hour", "stimulating_last_hour"):
            df = pd.DataFrame({pred: hours, "sleep_score": scores})
            r = float(df[pred].corr(df["sleep_score"]))  # -1.0
            eff = _effect_size(pred, "sleep_score", df, r)
            assert eff is not None
            assert eff["increment_label"] == "hour later"
            assert eff["value"] == pytest.approx(-2.0, abs=0.05)
            c = _binned_contrast(pred, "sleep_score", df)
            assert c is not None
            assert c["low_label"] == "12:15 AM or earlier"
            assert c["high_label"] == "after 12:15 AM"
            assert c["low_mean"] > c["high_mean"]
            assert c["n_low"] >= 5 and c["n_high"] >= 5

    def test_after_midnight_events_correlate_sanely_end_to_end(self, db: Session) -> None:
        """#134 regression: seed days whose last caffeine drifts from 10 PM
        past midnight while scores fall. On the raw 0-24 clock the
        after-midnight days would sort as the EARLIEST and flip the sign;
        on the evening clock the correlation is strongly negative with a
        sane slope and clock-labeled bins."""
        base_date = dt.date(2025, 1, 1)
        n = 20
        for i in range(n):
            d = base_date + dt.timedelta(days=i)
            hour = 22.0 + 0.25 * i  # 22.0 → 26.75, crossing midnight at i=8
            minutes = round((hour % 24) * 60)
            t = dt.time(minutes // 60, minutes % 60)
            _make_sleep_record(db, d, sleep_score=round(90 - 2 * (hour - 22.0)))
            _make_daily_log(db, d)
            db.add(CaffeineEntry(date=d, time=t, amount_mg=80, source="tea"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        results, _ = compute_correlations(df, min_days=14)
        row = next(
            r
            for r in results
            if r["predictor"] == "last_caffeine_hour" and r["outcome"] == "sleep_score"
        )
        assert row["pearson_r"] < -0.9  # raw clock would have flipped this
        assert row["effect"] is not None
        assert row["effect"]["increment_label"] == "hour later"
        assert row["effect"]["value"] == pytest.approx(-2.0, abs=0.1)
        assert row["contrast"] is not None
        # cutoff label is a clock time, not a bare number
        assert "AM" in row["contrast"]["low_label"] or "PM" in row["contrast"]["low_label"]

    def test_compute_correlations_attaches_effect_and_contrast(self) -> None:
        from backend.services.stats_engine import compute_correlations

        n = 30
        hours = [23.0 + 0.1 * i for i in range(n)]
        scores = [90.0 - 0.6 * i for i in range(n)]
        df = pd.DataFrame({"bedtime_hour": hours, "sleep_score": scores})
        results, _ = compute_correlations(df, min_days=14)
        row = next(r for r in results if r["predictor"] == "bedtime_hour")
        assert row["effect"] is not None
        assert row["effect"]["increment_label"] == "hour later"
        assert row["contrast"] is not None


# --- #159: explicit section absence (the third data state) ---


def _agg_row(db: Session, date: dt.date) -> dict[str, Any]:
    """Aggregate a single day's log through the real aggregation path."""
    from backend.services.stats_engine import _aggregate_daily_log

    log = db.query(DailyLog).filter(DailyLog.date == date).one()
    return _aggregate_daily_log(log)


class TestSectionAbsenceAggregation:
    def test_binary_habit_absence_records_explicit_zero(self, db: Session) -> None:
        """alcohol marked absent, no alcohol entry → 0.0 (not None)."""
        d = dt.date(2025, 3, 1)
        _make_daily_log(db, d)
        db.add(SectionAbsence(date=d, section_key="alcohol"))
        db.commit()

        row = _agg_row(db, d)
        assert row["alcohol"] == 0.0

    def test_blank_day_stays_null(self, db: Session) -> None:
        """No entry and no absence → still None (unknown), unchanged."""
        d = dt.date(2025, 3, 2)
        _make_daily_log(db, d)
        db.commit()

        row = _agg_row(db, d)
        assert row["alcohol"] is None

    def test_caffeine_absence_zeroes_total_but_keeps_clock_null(self, db: Session) -> None:
        """Caffeine absent → total_caffeine_mg == 0, but last_caffeine_hour
        stays NULL — there is no clock time for a caffeine event that never
        happened."""
        d = dt.date(2025, 3, 3)
        _make_daily_log(db, d)
        db.add(SectionAbsence(date=d, section_key="caffeine"))
        db.commit()

        row = _agg_row(db, d)
        assert row["total_caffeine_mg"] == 0
        assert row["last_caffeine_hour"] is None

    def test_nap_absence_zeroes_minutes_and_count(self, db: Session) -> None:
        d = dt.date(2025, 3, 4)
        _make_daily_log(db, d)
        db.add(SectionAbsence(date=d, section_key="nap"))
        db.commit()

        row = _agg_row(db, d)
        assert row["nap_total_minutes"] == 0
        assert row["nap_count"] == 0

    def test_exercise_absence_zeroes_done_and_duration(self, db: Session) -> None:
        d = dt.date(2025, 3, 5)
        _make_daily_log(db, d)
        db.add(SectionAbsence(date=d, section_key="exercise"))
        db.commit()

        row = _agg_row(db, d)
        assert row["exercise_done"] == 0.0
        assert row["exercise_duration_minutes"] == 0

    def test_real_entry_wins_over_absence(self, db: Session) -> None:
        """If a day carries both a real entry and an absence for the same
        section, the entry stands and the absence is ignored."""
        d = dt.date(2025, 3, 6)
        _make_daily_log(db, d)
        db.add(HabitEntry(date=d, habit_type=HabitType.SAUNA))
        db.add(SectionAbsence(date=d, section_key="sauna"))
        db.commit()

        row = _agg_row(db, d)
        assert row["sauna"] == 1.0

    def test_absence_unlocks_binary_habit_correlation_end_to_end(self, db: Session) -> None:
        """The whole point of #159: a binary habit with ~8 "did it" days and
        ~8 "explicitly did not" days becomes correlatable. Without the absence
        rows those 8 off-days are NULL, the column is all-1.0, std==0, and the
        predictor is silently skipped — the mutation at the end proves it."""
        base = dt.date(2025, 4, 1)
        # 8 "did it" days (sauna entry) with high sleep scores.
        for i in range(8):
            d = base + dt.timedelta(days=i)
            _make_sleep_record(db, d, sleep_score=88 + i)
            _make_daily_log(db, d)
            db.add(HabitEntry(date=d, habit_type=HabitType.SAUNA))
        # 8 "explicitly did not" days (SectionAbsence) with low sleep scores.
        for i in range(8):
            d = base + dt.timedelta(days=8 + i)
            _make_sleep_record(db, d, sleep_score=60 + i)
            _make_daily_log(db, d)
            db.add(SectionAbsence(date=d, section_key="sauna"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        # Off-days recorded as explicit 0.0, on-days as 1.0 → real variance.
        assert set(df["sauna"].dropna().unique()) == {0.0, 1.0}

        results, _ = compute_correlations(df, min_days=14)
        sauna_rows = [r for r in results if r["predictor"] == "sauna"]
        assert sauna_rows, "sauna correlation should now be produced"
        assert sauna_rows[0]["n_days"] == 16

        # Mutation: drop the absence rows. The off-days revert to NULL, the
        # column is all-1.0 (zero variance), and the predictor disappears.
        for absence in db.query(SectionAbsence).all():
            db.delete(absence)
        db.commit()

        df2 = prepare_analysis_dataframe(db)
        assert set(df2["sauna"].dropna().unique()) == {1.0}
        results2, _ = compute_correlations(df2, min_days=14)
        assert not any(r["predictor"] == "sauna" for r in results2)


# --- #161 Lane 2: per-product supplement predictors (dose + timing) ---


def _make_product(db: Session, name: str, **kwargs: Any) -> SupplementProduct:
    product = SupplementProduct(name=name, **kwargs)
    db.add(product)
    db.flush()  # assign product.id
    return product


class TestSupplementPredictors:
    def test_dose_predictor_appears_and_absence_unlocks(self, db: Session) -> None:
        """A product-linked supplement becomes a dose predictor: ~8 days
        melatonin@3mg (high scores) + ~8 days marked none-today via a
        supplement:<pid> absence (0mg, low scores) → the dose column carries
        {0.0, 3.0} and correlates, labeled "Melatonin (dose)". Mutation: drop
        the absence rows → column is all-3.0 (zero variance) and the predictor
        disappears — proving the absence-key wiring is what unlocks it."""
        melatonin = _make_product(db, "Melatonin", unit="mg", default_dose=3.0)
        pid = melatonin.id
        dose_col = f"supplement_dose_{pid}"
        base = dt.date(2025, 5, 1)
        # 8 "took 3mg" days, higher sleep scores.
        for i in range(8):
            d = base + dt.timedelta(days=i)
            _make_sleep_record(db, d, sleep_score=88 + i)
            _make_daily_log(db, d)
            db.add(SupplementEntry(date=d, name="Melatonin", dose_mg=3.0, product_id=pid))
        # 8 "none today" days (absence), lower sleep scores.
        for i in range(8):
            d = base + dt.timedelta(days=8 + i)
            _make_sleep_record(db, d, sleep_score=60 + i)
            _make_daily_log(db, d)
            db.add(SectionAbsence(date=d, section_key=f"supplement:{pid}"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert set(df[dose_col].dropna().unique()) == {0.0, 3.0}

        results, _ = compute_correlations(df, min_days=14)
        dose_rows = [r for r in results if r["predictor"] == dose_col]
        assert dose_rows, "melatonin dose correlation should be produced"
        assert dose_rows[0]["predictor_label"] == "Melatonin (dose)"
        assert dose_rows[0]["n_days"] == 16

        # Mutation: drop the absence rows → off-days revert to NULL (not
        # recorded), the column is all-3.0, std==0, predictor disappears.
        for absence in db.query(SectionAbsence).all():
            db.delete(absence)
        db.commit()

        df2 = prepare_analysis_dataframe(db)
        assert set(df2[dose_col].dropna().unique()) == {3.0}
        results2, _ = compute_correlations(df2, min_days=14)
        assert not any(r["predictor"] == dose_col for r in results2)

    def test_two_products_stay_distinct(self, db: Session) -> None:
        """Two library products produce separate columns/predictors — never
        merged into one 'magnesium' bucket."""
        glycinate = _make_product(db, "Magnesium Glycinate", form="capsule")
        threonate = _make_product(db, "Magnesium L-Threonate", form="capsule")
        col_a = f"supplement_dose_{glycinate.id}"
        col_b = f"supplement_dose_{threonate.id}"
        base = dt.date(2025, 6, 1)
        for i in range(16):
            d = base + dt.timedelta(days=i)
            _make_sleep_record(db, d, sleep_score=70 + (i % 5))
            _make_daily_log(db, d)
            # Distinct doses so each column has its own variance.
            db.add(
                SupplementEntry(
                    date=d, name="Magnesium Glycinate", dose_mg=200.0 + i, product_id=glycinate.id
                )
            )
            db.add(
                SupplementEntry(
                    date=d,
                    name="Magnesium L-Threonate",
                    dose_mg=2000.0 - i * 10,
                    product_id=threonate.id,
                )
            )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert col_a in df.columns
        assert col_b in df.columns
        # Distinct values, never merged.
        assert df[col_a].iloc[0] == 200.0
        assert df[col_b].iloc[0] == 2000.0

        results, _ = compute_correlations(df, min_days=14)
        labels = {r["predictor"]: r["predictor_label"] for r in results}
        # Labels include form (· capsule) — brand/form are appended for
        # product-level distinctness (Codex P2, Lane 2 review).
        assert labels.get(col_a) == "Magnesium Glycinate · capsule (dose)"
        assert labels.get(col_b) == "Magnesium L-Threonate · capsule (dose)"

    def test_same_name_products_get_distinct_labels(self, db: Session) -> None:
        """Two products sharing a name but differing by brand get DISTINCT
        labels (Codex P2) — otherwise a correlation can't say which one."""
        a = _make_product(db, "Melatonin", brand="Nature Made", unit="mg")
        b = _make_product(db, "Melatonin", brand="Life Extension", unit="mg")
        col_a = f"supplement_dose_{a.id}"
        col_b = f"supplement_dose_{b.id}"
        base = dt.date(2025, 6, 1)
        for i in range(16):
            d = base + dt.timedelta(days=i)
            _make_sleep_record(db, d, sleep_score=70 + (i % 5))
            _make_daily_log(db, d)
            db.add(SupplementEntry(date=d, name="Melatonin", dose_mg=3.0 + i, product_id=a.id))
            db.add(SupplementEntry(date=d, name="Melatonin", dose_mg=1.0 + i, product_id=b.id))
        db.commit()

        results, _ = compute_correlations(prepare_analysis_dataframe(db), min_days=14)
        labels = {r["predictor"]: r["predictor_label"] for r in results}
        assert labels.get(col_a) == "Melatonin · Nature Made (dose)"
        assert labels.get(col_b) == "Melatonin · Life Extension (dose)"
        assert labels[col_a] != labels[col_b]

    def test_dose_unrecorded_is_null_not_zero(self, db: Session) -> None:
        """A product logged with NO dose (dose_mg=None) → NULL, never 0.0.
        Zero is reserved for an explicit none-today absence, so an unrecorded
        dose must NOT masquerade as a skip (Codex P2 / ADR 003)."""
        from backend.models import SectionAbsence

        mel = _make_product(db, "Melatonin", unit="mg")
        dose_col = f"supplement_dose_{mel.id}"

        # Day 1: took it, dose unknown (dose_mg=None) → column NULL.
        d1 = dt.date(2025, 6, 1)
        _make_sleep_record(db, d1)
        _make_daily_log(db, d1)
        db.add(SupplementEntry(date=d1, name="Melatonin", dose_mg=None, product_id=mel.id))
        # Day 2: explicit none-today via absence key → column 0.0.
        d2 = dt.date(2025, 6, 2)
        _make_sleep_record(db, d2)
        _make_daily_log(db, d2)
        db.add(SectionAbsence(date=d2, section_key=f"supplement:{mel.id}"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert pd.isna(df.loc[d1][dose_col])  # unknown dose → NULL, excluded
        assert df.loc[d2][dose_col] == 0.0  # explicit skip → 0, the two differ

    def test_timing_predictor_hours_before_bed(self, db: Session) -> None:
        """supplement_hbb_<pid> = bedtime_hour - evening_hour(taken). Melatonin
        at 9:15 PM with an 11 PM bedtime → 1.75 h before bed. A none-today
        (0-dose) day → timing NULL (no time for something not taken), not 0."""
        melatonin = _make_product(db, "Melatonin", unit="mg")
        pid = melatonin.id
        hbb_col = f"supplement_hbb_{pid}"
        dose_col = f"supplement_dose_{pid}"

        taken_day = dt.date(2025, 7, 1)
        _make_sleep_record(
            db,
            taken_day,
            bedtime=dt.datetime.combine(taken_day - dt.timedelta(days=1), dt.time(23, 0)),
        )
        _make_daily_log(db, taken_day)
        db.add(
            SupplementEntry(
                date=taken_day,
                name="Melatonin",
                dose_mg=3.0,
                time=dt.time(21, 15),
                product_id=pid,
            )
        )

        # A none-today day: dose 0.0 via absence, but no timing.
        absent_day = dt.date(2025, 7, 2)
        _make_sleep_record(db, absent_day)
        _make_daily_log(db, absent_day)
        db.add(SectionAbsence(date=absent_day, section_key=f"supplement:{pid}"))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.loc[taken_day][hbb_col] == pytest.approx(1.75)
        # Absent day: explicit 0 dose, NULL timing.
        assert df.loc[absent_day][dose_col] == 0.0
        assert pd.isna(df.loc[absent_day][hbb_col])

    def test_timing_predictor_evening_clock_after_midnight(self, db: Session) -> None:
        """Both taken-time and bedtime use the evening clock, so a post-midnight
        dose stays consistent: 12:30 AM (24.5) with a 1 AM bedtime (25.0) →
        0.5 h before bed, not a negative wrap."""
        melatonin = _make_product(db, "Melatonin")
        pid = melatonin.id
        hbb_col = f"supplement_hbb_{pid}"
        d = dt.date(2025, 8, 1)
        _make_sleep_record(db, d, bedtime=dt.datetime.combine(d, dt.time(1, 0)))
        _make_daily_log(db, d)
        db.add(
            SupplementEntry(
                date=d, name="Melatonin", dose_mg=3.0, time=dt.time(0, 30), product_id=pid
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.loc[d][hbb_col] == pytest.approx(0.5)

    def test_timing_predictor_late_sleeper_4_to_6am(self, db: Session) -> None:
        """Late-sleeper clock alignment (Codex P2, Lane 2 re-run): bedtime wraps
        at < 6 but supplement consumption times use a < 4 cutoff, so a 4:30 AM
        dose (in the 4–6 AM no-wrap gap) before a 5 AM bedtime must still use
        the BEDTIME clock for timing: hbb = 29.0 - 28.5 = 0.5, NOT 24.5."""
        melatonin = _make_product(db, "Melatonin")
        pid = melatonin.id
        hbb_col = f"supplement_hbb_{pid}"
        d = dt.date(2025, 9, 1)
        _make_sleep_record(db, d, bedtime=dt.datetime.combine(d, dt.time(5, 0)))
        _make_daily_log(db, d)
        db.add(
            SupplementEntry(
                date=d, name="Melatonin", dose_mg=3.0, time=dt.time(4, 30), product_id=pid
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.loc[d][hbb_col] == pytest.approx(0.5)

    def test_decimal_dose_round_trips_with_unit_on_product(self, db: Session) -> None:
        """Decimal doses (0.5 mg melatonin) survive aggregation; the unit lives
        on the product, the value on the entry's dose_mg."""
        melatonin = _make_product(db, "Melatonin", unit="mcg", step=0.5, default_dose=0.5)
        pid = melatonin.id
        dose_col = f"supplement_dose_{pid}"
        d = dt.date(2025, 9, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(SupplementEntry(date=d, name="Melatonin", dose_mg=0.5, product_id=pid))
        db.commit()

        assert melatonin.unit == "mcg"
        df = prepare_analysis_dataframe(db)
        assert df.loc[d][dose_col] == pytest.approx(0.5)

    def test_summed_dose_and_latest_timing_for_multiple_same_day_entries(self, db: Session) -> None:
        """Multiple entries of the same product on one day: dose SUMS, timing
        uses the LATEST (closest to bed)."""
        product = _make_product(db, "Magnesium")
        pid = product.id
        dose_col = f"supplement_dose_{pid}"
        hbb_col = f"supplement_hbb_{pid}"
        d = dt.date(2025, 10, 1)
        _make_sleep_record(
            db, d, bedtime=dt.datetime.combine(d - dt.timedelta(days=1), dt.time(23, 0))
        )
        _make_daily_log(db, d)
        db.add(
            SupplementEntry(
                date=d, name="Magnesium", dose_mg=100.0, time=dt.time(8, 0), product_id=pid
            )
        )
        db.add(
            SupplementEntry(
                date=d, name="Magnesium", dose_mg=50.0, time=dt.time(21, 0), product_id=pid
            )
        )
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert df.loc[d][dose_col] == pytest.approx(150.0)  # summed
        # Latest entry 21:00 → 2h before an 11 PM bedtime.
        assert df.loc[d][hbb_col] == pytest.approx(2.0)

    def test_malformed_supplement_absence_key_is_ignored(self, db: Session) -> None:
        """A non-numeric supplement:<pid> key can't map to a product column —
        it is skipped without crashing (defensive; the write path only ever
        emits integer pids)."""
        d = dt.date(2025, 12, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(SectionAbsence(date=d, section_key="supplement:not-a-number"))
        db.commit()

        df = prepare_analysis_dataframe(db)  # must not raise
        assert not any(c.startswith("supplement_") for c in df.columns)

    def test_free_text_entry_is_not_a_predictor(self, db: Session) -> None:
        """A legacy free-text SupplementEntry (product_id NULL) spawns no
        supplement_* column and does not crash aggregation."""
        d = dt.date(2025, 11, 1)
        _make_sleep_record(db, d)
        _make_daily_log(db, d)
        db.add(SupplementEntry(date=d, name="Random Herb", dose_mg=500.0, product_id=None))
        db.commit()

        df = prepare_analysis_dataframe(db)
        assert not any(c.startswith("supplement_") for c in df.columns)
