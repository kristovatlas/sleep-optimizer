"""SQLAlchemy ORM models for all Somnus data."""

import datetime as dt
import enum
import math

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

# --- Enums ---


class CaffeineSource(enum.StrEnum):
    ESPRESSO = "espresso"
    DRIP_COFFEE = "drip_coffee"
    COLD_BREW = "cold_brew"
    TEA = "tea"
    ENERGY_DRINK = "energy_drink"
    SODA = "soda"
    SUPPLEMENT = "supplement"
    OTHER = "other"


class HabitType(enum.StrEnum):
    BLUE_BLOCKERS_ON = "blue_blockers_on"
    SCREENS_OFF = "screens_off"
    EXERCISE = "exercise"
    ALCOHOL = "alcohol"
    ROOM_TEMP_F = "room_temp_f"
    STRESS_LEVEL = "stress_level"
    SAUNA = "sauna"
    WARM_SHOWER = "warm_shower"


class ExerciseIntensity(enum.StrEnum):
    LIGHT = "light"
    MODERATE = "moderate"
    INTENSE = "intense"


class StimulatingActivityType(enum.StrEnum):
    TV_MOVIES = "tv_movies"
    VIDEO_GAMES = "video_games"
    GRIPPING_AUDIOBOOK = "gripping_audiobook"
    OTHER = "other"


class SexualActivityType(enum.StrEnum):
    PARTNERED = "partnered"
    SOLO_WITH_CONTENT = "solo_with_content"
    SOLO_WITHOUT_CONTENT = "solo_without_content"


class PreBedRitualType(enum.StrEnum):
    DEEP_BREATHING = "deep_breathing"
    LEGS_UP_WALL = "legs_up_wall"
    STRETCHING = "stretching"
    JOURNALING = "journaling"
    READING_FICTION = "reading_fiction"
    OTHER = "other"


class NSDRType(enum.StrEnum):
    YOGA_NIDRA = "yoga_nidra"
    BODY_SCAN = "body_scan"
    SLEEP_HYPNOSIS = "sleep_hypnosis"
    GUIDED_RELAXATION = "guided_relaxation"
    OTHER = "other"


class CaffeineSensitivity(enum.StrEnum):
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"


class Chronotype(enum.StrEnum):
    EARLY = "early"
    INTERMEDIATE = "intermediate"
    LATE = "late"


class DisplayMode(enum.StrEnum):
    CIRCADIAN = "circadian"
    LIGHT = "light"
    AUTO = "auto"


class ExperimentStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# --- Models ---


class SleepRecord(Base):
    """Sleep data imported from Oura Ring."""

    __tablename__ = "sleep_records"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    total_sleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rem_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    light_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    onset_latency_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_hrv: Mapped[float | None] = mapped_column(Float, nullable=True)
    lowest_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_breath_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    readiness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bedtime: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    wake_time: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def rem_pct(self) -> float | None:
        if self.rem_minutes is not None and self.total_sleep_minutes:
            return round(self.rem_minutes / self.total_sleep_minutes * 100, 1)
        return None

    @property
    def deep_pct(self) -> float | None:
        if self.deep_minutes is not None and self.total_sleep_minutes:
            return round(self.deep_minutes / self.total_sleep_minutes * 100, 1)
        return None

    @property
    def light_pct(self) -> float | None:
        if self.light_minutes is not None and self.total_sleep_minutes:
            return round(self.light_minutes / self.total_sleep_minutes * 100, 1)
        return None


class DailyLog(Base):
    """User-entered daily log. One per date."""

    __tablename__ = "daily_logs"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    copied_from_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_sick: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    caffeine_entries: Mapped[list["CaffeineEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    meal_entries: Mapped[list["MealEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    supplement_entries: Mapped[list["SupplementEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    habit_entries: Mapped[list["HabitEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    stimulating_activity_entries: Mapped[list["StimulatingActivityEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    sexual_activity_entry: Mapped["SexualActivityEntry | None"] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan", uselist=False
    )
    pre_bed_ritual_entries: Mapped[list["PreBedRitualEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    nap_entries: Mapped[list["NapEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    sunlight_entries: Mapped[list["SunlightEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    red_light_entries: Mapped[list["RedLightEntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    nsdr_entries: Mapped[list["NSDREntry"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )
    section_absences: Mapped[list["SectionAbsence"]] = relationship(
        back_populates="daily_log", cascade="all, delete-orphan"
    )


class CaffeineEntry(Base):
    __tablename__ = "caffeine_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    amount_mg: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[CaffeineSource] = mapped_column(
        Enum(CaffeineSource), nullable=False, default=CaffeineSource.OTHER
    )

    daily_log: Mapped[DailyLog] = relationship(back_populates="caffeine_entries")


class MealEntry(Base):
    __tablename__ = "meal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    is_last_meal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="meal_entries")


class SupplementProduct(Base):
    """A distinct supplement product in the user's library (#161, Lane 2).

    Product-level granularity, owner-decided 2026-07-23: brand + form + dose
    make a product distinct (Nature Made Melatonin 3 mg ≠ a 300 mcg sublingual;
    Pure Encapsulations Magnesium Glycinate ≠ Magnesium L-Threonate / Magtein),
    and each product is its own analysis predictor — no form-level rollups. The
    library entry is the product (name + brand + form + a *default* dose used
    only to prefill); the actual per-day dose lives on ``SupplementEntry``.

    Purely additive: existing free-text ``SupplementEntry`` rows keep
    ``product_id`` NULL and their ``name``/``dose_mg``, and are never turned
    into predictors (Lane 2 only analyzes product-linked entries).
    """

    __tablename__ = "supplement_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    form: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Prefill only — the analyzed dose is the per-day value on SupplementEntry.
    default_dose: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Dose unit for this product: "mg" (default), "mcg", "IU", "g". The numeric
    # dose VALUE is stored on SupplementEntry.dose_mg, whose legacy name is kept
    # to avoid touching existing data — the value is in THIS product's unit, not
    # necessarily milligrams. See ADR 003 / the v0.1.2 supplement plan.
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="mg")
    # Stepper increment for the dose input (e.g. 0.5 mg melatonin).
    step: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # Sticky products auto-appear in each day's log, prefilled at default_dose.
    is_sticky: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    entries: Mapped[list["SupplementEntry"]] = relationship(back_populates="product")


class SupplementEntry(Base):
    __tablename__ = "supplement_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Numeric dose value in the product's unit (legacy column name — NOT always
    # milligrams; the unit lives on SupplementProduct.unit). See #161.
    dose_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # #161 Lane 2: link to a library product. NULL for legacy free-text rows,
    # which stay un-analyzed. Additive — no data migration.
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("supplement_products.id"), nullable=True
    )

    daily_log: Mapped[DailyLog] = relationship(back_populates="supplement_entries")
    product: Mapped["SupplementProduct | None"] = relationship(back_populates="entries")


class HabitEntry(Base):
    __tablename__ = "habit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    habit_type: Mapped[HabitType] = mapped_column(Enum(HabitType), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="habit_entries")


class StimulatingActivityEntry(Base):
    __tablename__ = "stimulating_activity_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    activity_type: Mapped[StimulatingActivityType] = mapped_column(
        Enum(StimulatingActivityType), nullable=False
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="stimulating_activity_entries")


class SexualActivityEntry(Base):
    __tablename__ = "sexual_activity_entries"
    __table_args__ = (UniqueConstraint("date", name="uq_sexual_activity_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    activity_type: Mapped[SexualActivityType] = mapped_column(
        Enum(SexualActivityType), nullable=False
    )

    daily_log: Mapped[DailyLog] = relationship(back_populates="sexual_activity_entry")


class PreBedRitualEntry(Base):
    __tablename__ = "pre_bed_ritual_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    ritual_type: Mapped[PreBedRitualType] = mapped_column(Enum(PreBedRitualType), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="pre_bed_ritual_entries")


class NapEntry(Base):
    __tablename__ = "nap_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    start_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="nap_entries")


class SunlightEntry(Base):
    __tablename__ = "sunlight_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    start_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_lux: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="sunlight_entries")


class RedLightPanel(Base):
    """User-configured red light therapy panel presets."""

    __tablename__ = "red_light_panels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    wavelength_nm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    irradiance_mw_cm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The distance the irradiance above is specified at (manufacturer spec),
    # AND the default session distance. Used as the inverse-square reference
    # for dose adjustment (#60).
    default_distance_inches: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    entries: Mapped[list["RedLightEntry"]] = relationship(back_populates="panel")


class RedLightEntry(Base):
    __tablename__ = "red_light_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    panel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("red_light_panels.id"), nullable=True
    )
    start_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # #60: actual distance for THIS session; None = use the panel default.
    distance_inches: Mapped[float | None] = mapped_column(Float, nullable=True)

    daily_log: Mapped[DailyLog] = relationship(back_populates="red_light_entries")
    panel: Mapped[RedLightPanel | None] = relationship(back_populates="entries")

    @property
    def dose_joules_cm2(self) -> float | None:
        """Session dose in J/cm^2, inverse-square-adjusted for distance (#60).

        Irradiance is specified at the panel's default_distance_inches
        (reference). If this session used a different distance, irradiance
        scales by (reference / actual)^2. When either distance is missing or
        non-positive, no adjustment is applied (factor 1.0) — the dose then
        matches the pre-#60 behavior.
        """
        if (
            self.panel is None
            or self.panel.irradiance_mw_cm2 is None
            or self.duration_minutes is None
        ):
            return None
        factor = 1.0
        reference = self.panel.default_distance_inches
        actual = self.distance_inches
        try:
            if reference is not None and actual is not None and reference > 0 and actual > 0:
                factor = (reference / actual) ** 2
            dose = self.panel.irradiance_mw_cm2 * factor * self.duration_minutes * 60 / 1000
        except OverflowError:
            # Schema bounds keep API input realistic; this guards a manually
            # crafted row from ever raising or persisting a bad dose.
            return None
        # A pathological ratio could also reach inf without raising.
        if not math.isfinite(dose):
            return None
        return round(dose, 2)


class NSDREntry(Base):
    __tablename__ = "nsdr_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nsdr_type: Mapped[NSDRType] = mapped_column(
        Enum(NSDRType), nullable=False, default=NSDRType.OTHER
    )

    daily_log: Mapped[DailyLog] = relationship(back_populates="nsdr_entries")


class SectionAbsence(Base):
    """An explicit "did NOT do X" record for a log section on a given day (#159).

    This is the third data state alongside a recorded value ("did it") and a
    blank/NULL ("not recorded"). A row here means the user explicitly marked a
    section as not done for the date — real negative data, distinct from a
    blank, which stays unknown/excluded from analysis. See ADR 003.

    ``section_key`` is a log-section id (e.g. ``caffeine``, ``alcohol``,
    ``nsdr``, ``sauna``) or a namespaced per-supplement key
    (``supplement:<canonical name>``, used by a later lane). It is stored as a
    free string — no enum — so new sections/supplements need no schema change.
    Purely additive: existing daily logs with no rows here keep their current
    semantics unchanged.
    """

    __tablename__ = "section_absences"
    __table_args__ = (UniqueConstraint("date", "section_key", name="uq_section_absence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, ForeignKey("daily_logs.date"), nullable=False)
    section_key: Mapped[str] = mapped_column(String(150), nullable=False)

    daily_log: Mapped[DailyLog] = relationship(back_populates="section_absences")


class Experiment(Base):
    """Tracked experiment — user tests one factor change for ~2 weeks."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    factor: Mapped[str] = mapped_column(String(100), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus), nullable=False, default=ExperimentStatus.ACTIVE
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)


class UserSettings(Base):
    """Singleton settings row. Always id=1."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    oura_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    typical_bedtime: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    target_wake_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    caffeine_sensitivity: Mapped[CaffeineSensitivity] = mapped_column(
        Enum(CaffeineSensitivity), nullable=False, default=CaffeineSensitivity.NORMAL
    )
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/New_York")
    chronotype: Mapped[Chronotype | None] = mapped_column(Enum(Chronotype), nullable=True)
    # Reserved for #54 (seasonal/solar, post-0.1) — no UI or consumer yet.
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_mode: Mapped[DisplayMode] = mapped_column(
        Enum(DisplayMode), nullable=False, default=DisplayMode.CIRCADIAN
    )
    circadian_mode_start: Mapped[dt.time] = mapped_column(
        Time, nullable=False, default=dt.time(20, 0)
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_oura_sync: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
