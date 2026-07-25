"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

import datetime as dt
import functools
import zoneinfo

from pydantic import BaseModel, Field, field_validator

from backend.models import (
    CaffeineSensitivity,
    CaffeineSource,
    Chronotype,
    DisplayMode,
    ExperimentStatus,
    HabitType,
    NSDRType,
    PreBedRitualType,
    SexualActivityType,
    StimulatingActivityType,
)

# --- Health Check ---


class HealthResponse(BaseModel):
    status: str
    version: str


# --- Sleep Record (from Oura) ---


class SleepRecordOut(BaseModel):
    date: dt.date
    total_sleep_minutes: int | None = None
    rem_minutes: int | None = None
    deep_minutes: int | None = None
    light_minutes: int | None = None
    rem_pct: float | None = None
    deep_pct: float | None = None
    light_pct: float | None = None
    sleep_efficiency: float | None = None
    onset_latency_minutes: int | None = None
    avg_hrv: float | None = None
    lowest_hr: int | None = None
    avg_hr: float | None = None
    avg_breath_rate: float | None = None
    readiness_score: int | None = None
    sleep_score: int | None = None
    bedtime: dt.datetime | None = None
    wake_time: dt.datetime | None = None

    model_config = {"from_attributes": True}


# --- Caffeine ---


class CaffeineEntryCreate(BaseModel):
    time: dt.time | None = None
    amount_mg: int = Field(ge=1, le=600)
    source: CaffeineSource = CaffeineSource.OTHER


class CaffeineEntryOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    amount_mg: int
    source: CaffeineSource

    model_config = {"from_attributes": True}


# --- Meal ---


class MealEntryCreate(BaseModel):
    time: dt.time | None = None
    is_last_meal: bool | None = None
    notes: str | None = None


class MealEntryOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    is_last_meal: bool | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


# --- Supplement ---


class SupplementEntryCreate(BaseModel):
    time: dt.time | None = None
    name: str = Field(max_length=100)
    dose_mg: float | None = None
    # #161 Lane 3a: optional link to a library product. NULL = legacy free-text
    # entry (un-analyzed). The value is in the product's unit (see the model).
    product_id: int | None = None


class SupplementEntryOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    name: str
    dose_mg: float | None = None
    product_id: int | None = None

    model_config = {"from_attributes": True}


# --- Supplement Product (library, #161 Lane 3a) ---


class SupplementProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    form: str | None = Field(default=None, max_length=50)
    default_dose: float | None = Field(default=None, ge=0)
    unit: str = Field(default="mg", min_length=1, max_length=10)
    step: float = Field(default=0.5, gt=0)
    is_sticky: bool = False


class SupplementProductUpdate(BaseModel):
    """Partial update — only supplied fields change (PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    form: str | None = Field(default=None, max_length=50)
    default_dose: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=10)
    step: float | None = Field(default=None, gt=0)
    is_sticky: bool | None = None


class SupplementProductOut(BaseModel):
    id: int
    name: str
    brand: str | None = None
    form: str | None = None
    default_dose: float | None = None
    unit: str
    step: float
    is_sticky: bool

    model_config = {"from_attributes": True}


# --- Habit ---


class HabitEntryCreate(BaseModel):
    habit_type: HabitType
    time: dt.time | None = None
    value: str | None = Field(default=None, max_length=100)
    duration_minutes: int | None = Field(default=None, ge=1, le=300)
    notes: str | None = None


class HabitEntryOut(BaseModel):
    id: int
    date: dt.date
    habit_type: HabitType
    time: dt.time | None = None
    value: str | None = None
    duration_minutes: int | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


# --- Stimulating Activity ---


class StimulatingActivityCreate(BaseModel):
    end_time: dt.time | None = None
    activity_type: StimulatingActivityType
    duration_minutes: int | None = Field(default=None, ge=1)


class StimulatingActivityOut(BaseModel):
    id: int
    date: dt.date
    end_time: dt.time | None = None
    activity_type: StimulatingActivityType
    duration_minutes: int | None = None

    model_config = {"from_attributes": True}


# --- Sexual Activity ---


class SexualActivityCreate(BaseModel):
    time: dt.time | None = None
    activity_type: SexualActivityType


class SexualActivityOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    activity_type: SexualActivityType

    model_config = {"from_attributes": True}


# --- Pre-Bed Ritual ---


class PreBedRitualCreate(BaseModel):
    time: dt.time | None = None
    ritual_type: PreBedRitualType
    duration_minutes: int | None = Field(default=None, ge=1)


class PreBedRitualOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    ritual_type: PreBedRitualType
    duration_minutes: int | None = None

    model_config = {"from_attributes": True}


# --- Nap ---


class NapEntryCreate(BaseModel):
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=240)


class NapEntryOut(BaseModel):
    id: int
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    duration_minutes: int | None = None

    model_config = {"from_attributes": True}


# --- Sunlight ---


class SunlightEntryCreate(BaseModel):
    start_time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    estimated_lux: int | None = None
    notes: str | None = None


class SunlightEntryOut(BaseModel):
    id: int
    date: dt.date
    start_time: dt.time | None = None
    duration_minutes: int | None = None
    estimated_lux: int | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


# --- Red Light Panel ---


class RedLightPanelCreate(BaseModel):
    name: str = Field(max_length=100)
    wavelength_nm: int | None = Field(default=None, ge=600, le=900)
    irradiance_mw_cm2: float | None = Field(default=None, ge=0)
    default_distance_inches: float | None = Field(default=None, ge=0, le=240)
    notes: str | None = None


class RedLightPanelOut(BaseModel):
    id: int
    name: str
    wavelength_nm: int | None = None
    irradiance_mw_cm2: float | None = None
    default_distance_inches: float | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


# --- Red Light Entry ---


class RedLightEntryCreate(BaseModel):
    panel_id: int | None = None
    start_time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=60)
    distance_inches: float | None = Field(default=None, gt=0, le=240)


class RedLightEntryOut(BaseModel):
    id: int
    date: dt.date
    panel_id: int | None = None
    start_time: dt.time | None = None
    duration_minutes: int | None = None
    distance_inches: float | None = None
    dose_joules_cm2: float | None = None

    model_config = {"from_attributes": True}


# --- NSDR ---


class NSDREntryCreate(BaseModel):
    time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    nsdr_type: NSDRType = NSDRType.OTHER


class NSDREntryOut(BaseModel):
    id: int
    date: dt.date
    time: dt.time | None = None
    duration_minutes: int | None = None
    nsdr_type: NSDRType

    model_config = {"from_attributes": True}


# --- Daily Log (composite) ---


class DailyLogCreate(BaseModel):
    is_sick: bool | None = None
    notes: str | None = None
    caffeine_entries: list[CaffeineEntryCreate] = []
    meal_entries: list[MealEntryCreate] = []
    supplement_entries: list[SupplementEntryCreate] = []
    habit_entries: list[HabitEntryCreate] = []
    stimulating_activity_entries: list[StimulatingActivityCreate] = []
    sexual_activity_entry: SexualActivityCreate | None = None
    pre_bed_ritual_entries: list[PreBedRitualCreate] = []
    nap_entries: list[NapEntryCreate] = []
    sunlight_entries: list[SunlightEntryCreate] = []
    red_light_entries: list[RedLightEntryCreate] = []
    nsdr_entries: list[NSDREntryCreate] = []
    # #161 Lane 3a: explicit "did not do X" section keys for the day (e.g.
    # "caffeine", "sauna", "supplement:<product_id>"). A save replaces the day's
    # absences with this list (same lifecycle as sub-entries). See ADR 003.
    section_absences: list[str] = []


class DailyLogOut(BaseModel):
    date: dt.date
    copied_from_date: dt.date | None = None
    is_sick: bool | None = None
    notes: str | None = None
    caffeine_entries: list[CaffeineEntryOut] = []
    meal_entries: list[MealEntryOut] = []
    supplement_entries: list[SupplementEntryOut] = []
    habit_entries: list[HabitEntryOut] = []
    stimulating_activity_entries: list[StimulatingActivityOut] = []
    sexual_activity_entry: SexualActivityOut | None = None
    pre_bed_ritual_entries: list[PreBedRitualOut] = []
    nap_entries: list[NapEntryOut] = []
    sunlight_entries: list[SunlightEntryOut] = []
    red_light_entries: list[RedLightEntryOut] = []
    nsdr_entries: list[NSDREntryOut] = []
    # Serialized as the bare section_key strings — the before-validator maps the
    # ORM SectionAbsence rows (from model_validate) down to their keys.
    section_absences: list[str] = []

    model_config = {"from_attributes": True}

    @field_validator("section_absences", mode="before")
    @classmethod
    def _absence_keys(cls, value: object) -> list[str]:
        """Accept ORM SectionAbsence rows or plain strings, emit key strings."""
        if not isinstance(value, (list, tuple)):
            return []
        return [item if isinstance(item, str) else item.section_key for item in value]


# --- User Settings ---


# --- Daily Log Response Wrappers ---


class DailyLogResponse(BaseModel):
    """Wraps DailyLogOut with soft validation warnings."""

    data: DailyLogOut
    warnings: list[str] = []


class DailyLogSummary(BaseModel):
    """Lightweight schema for list endpoints — no nested entries."""

    date: dt.date
    copied_from_date: dt.date | None = None
    is_sick: bool | None = None
    has_entries: bool = False

    model_config = {"from_attributes": True}


# --- Export ---


class ExportData(BaseModel):
    """JSON export structure."""

    daily_logs: list[DailyLogOut] = []
    sleep_records: list[SleepRecordOut] = []
    # #161 Lane 3a: the supplement library, so an export carries product
    # identity (name/brand/form/dose unit) that logged entries reference by
    # product_id — otherwise a re-import would lose which product each entry is.
    supplement_products: list[SupplementProductOut] = []


# --- User Settings ---


@functools.lru_cache(maxsize=1)
def _iana_timezones() -> frozenset[str]:
    """zoneinfo scans tzdata on every available_timezones() call — cache it."""
    return frozenset(zoneinfo.available_timezones())


class UserSettingsUpdate(BaseModel):
    oura_token: str | None = None
    typical_bedtime: dt.time | None = None
    target_wake_time: dt.time | None = None
    caffeine_sensitivity: CaffeineSensitivity | None = None
    timezone: str | None = None
    chronotype: Chronotype | None = None
    zip_code: str | None = Field(default=None, max_length=10)
    age: int | None = Field(default=None, ge=1, le=120)
    display_mode: DisplayMode | None = None
    circadian_mode_start: dt.time | None = None
    onboarding_completed: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """#50: a typo'd zone stored silently corrupts everything downstream.

        The message itself doesn't repeat the input (pydantic's structured
        422 carries it in the `input` field, as for every validator here).
        """
        if value is not None and value not in _iana_timezones():
            raise ValueError("not a valid IANA timezone name (e.g. 'America/New_York')")
        return value


class UserSettingsOut(BaseModel):
    oura_token_set: bool = False
    typical_bedtime: dt.time | None = None
    target_wake_time: dt.time | None = None
    caffeine_sensitivity: CaffeineSensitivity
    timezone: str
    chronotype: Chronotype | None = None
    zip_code: str | None = None
    age: int | None = None
    display_mode: DisplayMode
    circadian_mode_start: dt.time
    onboarding_completed: bool
    last_oura_sync: dt.datetime | None = None

    model_config = {"from_attributes": True}


# --- Oura Sync ---


class OuraSyncResponse(BaseModel):
    synced_count: int
    start_date: dt.date
    end_date: dt.date
    errors: list[str] = []


# --- Dashboard ---


class StageTargets(BaseModel):
    age_group: str
    deep_min_minutes: int
    deep_max_minutes: int
    rem_min_minutes: int
    rem_max_minutes: int


class TrendDay(BaseModel):
    date: dt.date
    sleep_score: int | None = None
    avg_hrv: float | None = None
    deep_minutes: int | None = None
    rem_minutes: int | None = None


class StageAverages(BaseModel):
    avg_deep_minutes: float
    avg_rem_minutes: float
    avg_light_minutes: float
    avg_total_minutes: float
    deep_vs_target: str
    rem_vs_target: str
    days_counted: int


class BedtimeDot(BaseModel):
    date: dt.date
    bedtime_hour: float
    is_weekend: bool


class ConsistencyMetrics(BaseModel):
    sigma_minutes: float
    sigma_rating: str
    delta_minutes: float | None = None
    delta_rating: str | None = None
    weekend_drift_minutes: float | None = None
    drift_rating: str | None = None
    bedtime_dots: list[BedtimeDot] = []
    days_counted: int


class RedLightWeeklySummary(BaseModel):
    session_count: int
    total_dose_joules_cm2: float
    days_with_sessions: int
    meets_minimum: bool


class TopRecommendation(BaseModel):
    id: str
    title: str
    category: str


class DashboardResponse(BaseModel):
    sleep_record: SleepRecordOut | None = None
    stage_targets: StageTargets | None = None
    trends: list[TrendDay] = []
    stage_averages: StageAverages | None = None
    consistency: ConsistencyMetrics | None = None
    logging_streak: int = 0
    red_light_summary: RedLightWeeklySummary
    today_caffeine_entries: list[CaffeineEntryOut] = []
    caffeine_sensitivity: CaffeineSensitivity = CaffeineSensitivity.NORMAL
    typical_bedtime: dt.time | None = None
    top_recommendations: list[TopRecommendation] = []


# --- Analysis Engine ---


class VariableStatus(BaseModel):
    name: str
    label: str
    n_days: int
    has_correlations: bool
    has_regression: bool


class AnalysisStatusResponse(BaseModel):
    total_sleep_days: int
    phase_a_unlocked: bool
    phase_b_unlocked: bool
    phase_c_unlocked: bool
    variables: list[VariableStatus]


class EffectSize(BaseModel):
    """#17: slope in natural units — '≈{value} {outcome_unit} per {increment_label}'."""

    value: float
    increment_label: str
    outcome_unit: str


class BinnedContrast(BaseModel):
    """#17: median-split evidence — outcome means below vs above the cutoff."""

    low_label: str
    high_label: str
    low_mean: float
    high_mean: float
    n_low: int
    n_high: int


class CorrelationResult(BaseModel):
    predictor: str
    predictor_label: str
    outcome: str
    outcome_label: str
    pearson_r: float
    spearman_r: float
    p_value: float
    n_days: int
    confidence: str
    effect: EffectSize | None = None
    contrast: BinnedContrast | None = None


class CorrelationResponse(BaseModel):
    results: list[CorrelationResult]
    total_days: int
    excluded_sick_days: int


class RegressionCoefficient(BaseModel):
    predictor: str
    predictor_label: str
    coefficient: float
    ci_lower: float | None = None
    ci_upper: float | None = None
    p_value: float
    is_significant: bool
    vif: float | None = None


class RegressionResult(BaseModel):
    outcome: str
    outcome_label: str
    n_days: int
    r_squared: float
    adj_r_squared: float
    coefficients: list[RegressionCoefficient]
    has_autocorrelation: bool
    is_stationary: bool
    multicollinearity_warning: bool
    excluded_predictors: list[str]


class RegressionResponse(BaseModel):
    results: list[RegressionResult]
    total_days: int


class SleepTimingResponse(BaseModel):
    chronotype: str | None = None
    chronotype_confidence: str | None = None
    sleep_midpoint_avg_hour: float | None = None
    social_jet_lag_minutes: float | None = None
    social_jet_lag_rating: str | None = None
    optimal_bedtime_start: float | None = None
    optimal_bedtime_end: float | None = None
    n_days: int = 0


class NapSegment(BaseModel):
    timing_label: str
    duration_label: str
    n_days: int
    avg_onset_latency: float | None = None
    avg_efficiency: float | None = None
    avg_total_sleep: float | None = None
    vs_no_nap_onset: float | None = None


class NapResponse(BaseModel):
    no_nap_baseline: dict[str, float | None]
    segments: list[NapSegment]
    total_nap_days: int
    total_no_nap_days: int


# --- Recommendations Engine ---


class Recommendation(BaseModel):
    id: str
    category: str  # data_driven | science_threshold | untried | timing
    priority: int
    title: str
    body: str
    factor: str
    factor_label: str
    outcome: str | None = None
    outcome_label: str | None = None
    evidence_level: str | None = None
    suggested_experiment: str | None = None
    n_days: int | None = None


class ExperimentOut(BaseModel):
    id: int
    factor: str
    factor_label: str
    hypothesis: str
    start_date: dt.date
    end_date: dt.date
    status: ExperimentStatus
    notes: str | None = None
    baseline_sleep_score: float | None = None
    baseline_deep_minutes: float | None = None
    baseline_rem_minutes: float | None = None
    baseline_hrv: float | None = None
    result_sleep_score: float | None = None
    result_deep_minutes: float | None = None
    result_rem_minutes: float | None = None
    result_hrv: float | None = None
    days_completed: int = 0


class RecommendationsResponse(BaseModel):
    recommendations: list[Recommendation]
    total_days: int
    has_sufficient_data: bool
    active_experiment: ExperimentOut | None = None


class ExperimentCreate(BaseModel):
    # Semantically an enum of analyzable variables, not free text (T-04):
    # an unknown factor would become the single active experiment and its
    # raw key would be the report label. Validated against VARIABLE_LABELS.
    factor: str = Field(max_length=100)
    # Length-bounded per T-04: rendered into the monthly HTML report
    hypothesis: str = Field(max_length=500)
    start_date: dt.date
    end_date: dt.date | None = None
    notes: str | None = None

    @field_validator("factor")
    @classmethod
    def _factor_is_known_variable(cls, v: str) -> str:
        # Imported here: services import schemas, so a module-level import
        # of a service from schemas would risk an import cycle
        from backend.services.stats_engine import VARIABLE_LABELS

        if v not in VARIABLE_LABELS:
            raise ValueError(f"unknown factor {v!r}; must be a known analyzable variable")
        return v


class ExperimentUpdate(BaseModel):
    status: ExperimentStatus | None = None
    notes: str | None = None


# --- Reports ---


class MetricAverages(BaseModel):
    avg_sleep_score: float | None = None
    avg_hrv: float | None = None
    avg_deep_minutes: float | None = None
    avg_rem_minutes: float | None = None


class TrendArrows(BaseModel):
    sleep_score: str | None = None  # "up" | "down" | "flat"
    avg_hrv: str | None = None
    deep_minutes: str | None = None
    rem_minutes: str | None = None


class TopFactor(BaseModel):
    label: str
    pearson_r: float
    n_days: int
    effect: EffectSize | None = None


class WeeklyReportResponse(BaseModel):
    period_start: dt.date
    period_end: dt.date
    iso_year: int
    iso_week: int
    days_with_data: int
    days_in_period: int  # always 7
    logging_completeness: str  # "5/7 days"
    current: MetricAverages
    prior: MetricAverages
    trends: TrendArrows
    consistency: ConsistencyMetrics | None = None
    # #102: top-3 per direction from FULL-dataset correlations (per-week
    # windows at n≤7 are statistically meaningless) — factors_total_days
    # feeds the "across all N days" caption so the card can say so.
    top_positive_factors: list[TopFactor] = []
    top_negative_factors: list[TopFactor] = []
    factors_total_days: int | None = None
    has_insufficient_data: bool


class NightSummary(BaseModel):
    date: dt.date
    sleep_score: int
    # #113: context so a best/worst night is interpretable at a glance.
    # All additive and optional (NULL = not recorded, ADR 003). weekday and
    # bedtime are formatted backend-side ("Tuesday", "11:42 PM") so the SPA
    # and the HTML export render identically.
    weekday: str | None = None
    bedtime: str | None = None
    total_sleep_minutes: int | None = None
    deep_minutes: int | None = None
    rem_minutes: int | None = None
    avg_hrv: float | None = None
    contributing_factors: list[str] = []


class StageComplianceReport(BaseModel):
    deep_target_nights: int
    deep_total_nights: int
    rem_target_nights: int
    rem_total_nights: int


class MonthlyReportResponse(BaseModel):
    period_start: dt.date
    period_end: dt.date
    year: int
    month: int
    month_name: str
    days_with_data: int
    days_in_period: int
    logging_completeness: str
    current: MetricAverages
    prior: MetricAverages
    trends: TrendArrows
    best_night: NightSummary | None = None
    worst_night: NightSummary | None = None
    stage_compliance: StageComplianceReport | None = None
    active_experiment: ExperimentOut | None = None
    weekly_summaries: list[WeeklyReportResponse] = []
    has_insufficient_data: bool
