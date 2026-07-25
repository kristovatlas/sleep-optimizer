import { useEffect, useRef, useState } from "react";
import { useDateNavigation } from "../../hooks/useDateNavigation";
import { useDailyLog, outToCreate } from "../../hooks/useDailyLog";
import { useCaffeineDecay } from "../../hooks/useCaffeineDecay";
import { getSettings } from "../../api/settings";
import { getDailyLog } from "../../api/dailyLog";
import {
  listSupplementProducts,
  createSupplementProduct,
} from "../../api/supplements";
import { addDays } from "../../utils/date";
import { ApiError } from "../../types/api";
import type {
  UserSettingsOut,
  DailyLogCreate,
  DailyLogOut,
  HabitEntryCreate,
  SupplementProduct,
  SupplementProductCreate,
} from "../../types";
import { HabitType } from "../../types/enums";
import { DateNavigator } from "./DateNavigator";
import { CopyDayButton } from "./CopyDayButton";
import { WarningBanner } from "./WarningBanner";
import { CaffeineSection } from "./sections/CaffeineSection";
import { MealSection } from "./sections/MealSection";
import { SupplementSection } from "./sections/SupplementSection";
import { rowForProduct } from "./sections/supplementRow";
import { HabitSection } from "./sections/HabitSection";
import { StimulatingSection } from "./sections/StimulatingSection";
import { SexualActivitySection } from "./sections/SexualActivitySection";
import { PreBedRitualSection } from "./sections/PreBedRitualSection";
import { NapSection } from "./sections/NapSection";
import { SunlightSection } from "./sections/SunlightSection";
import { RedLightSection } from "./sections/RedLightSection";
import { NSDRSection } from "./sections/NSDRSection";
import type { SectionAbsenceControl } from "./sections/SectionWrapper";
import { CaffeineChart } from "../CaffeineChart/CaffeineChart";
import { readTrackedSections } from "../../trackedSections";
import type { SectionKey } from "../../trackedSections";
import "./DailyLogPage.css";

/** Habit types that carry their own absence key (#159) — adding an entry of
 * the type clears its key (real data always supersedes an absence). */
const HABIT_ABSENCE_KEYS: Partial<Record<HabitType, string>> = {
  [HabitType.EXERCISE]: "exercise",
  [HabitType.ALCOHOL]: "alcohol",
  [HabitType.BLUE_BLOCKERS_ON]: "blue_blockers",
  [HabitType.SCREENS_OFF]: "screens_off",
  [HabitType.SAUNA]: "sauna",
  [HabitType.WARM_SHOWER]: "warm_shower",
};

/** Absence keys that count as a section's data for visibility: a recorded
 * "none today" on an untracked section must render like entries do — hidden,
 * it could be neither seen nor undone. Habits carries one key per habit
 * type; supplements records none-today as 0-dose entry rows (never absence
 * keys) and sexual activity has no absence control, so neither is listed. */
const SECTION_ABSENCE_KEYS: Partial<Record<SectionKey, readonly string[]>> = {
  caffeine: ["caffeine"],
  meals: ["meal"],
  habits: Object.values(HABIT_ABSENCE_KEYS).filter((k): k is string =>
    Boolean(k),
  ),
  stimulating: ["stimulating"],
  rituals: ["ritual"],
  naps: ["nap"],
  sunlight: ["sunlight"],
  redLight: ["red_light"],
  nsdr: ["nsdr"],
};

export function DailyLogPage() {
  const { currentDate, isToday, prev, next, today } = useDateNavigation();
  const {
    formData,
    setFormData,
    warnings,
    setWarnings,
    loading,
    loadError,
    reload,
    saving,
    saveStatus,
    saveError,
    exists,
    save,
  } = useDailyLog(currentDate);
  const [settings, setSettings] = useState<UserSettingsOut | null>(null);
  // Supplement library; null = unavailable (still loading or fetch failed).
  const [products, setProducts] = useState<SupplementProduct[] | null>(null);
  // #47: read once per mount — Settings edits land on the next visit here.
  const [tracked] = useState(readTrackedSections);

  // An untracked section still renders when the viewed day holds data in
  // it — entries OR a recorded absence key: hiding recorded state would be
  // worse than showing an extra section (and the form still submits the
  // full payload either way).
  const visible = (key: SectionKey, hasData: boolean) =>
    tracked.has(key) ||
    hasData ||
    (SECTION_ABSENCE_KEYS[key] ?? []).some((k) =>
      formData.section_absences.includes(k),
    );

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(() => {});
    listSupplementProducts()
      // Array guard: a misbehaving response must degrade to "library
      // unavailable", not crash the render.
      .then((p) => setProducts(Array.isArray(p) ? p : null))
      .catch(() => {});
  }, []);

  // #161 sticky products: on a not-yet-saved log for TODAY, sticky library
  // products auto-appear as prefilled rows (default dose, no time). Being
  // listed = took@default (owner decision, v3); the user types 0 for a skip
  // or removes the row if unsure. Scoped to today only — auto-filling a
  // blank PAST day the user merely browses would fabricate history.
  const stickyAppliedFor = useRef<string | null>(null);
  useEffect(() => {
    // Re-arm whenever a load is in flight: every completed load replaces the
    // form (a 404 resets it to empty), so a marker from before the load is
    // stale — without this, navigating away and back to a still-unsaved
    // today would skip re-applying rows the refetch just wiped. Between
    // loads the marker blocks double-apply, and a saved/existing day never
    // applies (exists guard below).
    if (loading) {
      stickyAppliedFor.current = null;
      return;
    }
    if (exists || loadError || !isToday || products === null) return;
    if (stickyAppliedFor.current === currentDate) return;
    stickyAppliedFor.current = currentDate;
    const sticky = products.filter((p) => p.is_sticky);
    if (sticky.length === 0) return;
    setFormData((prevData) => {
      const present = new Set(
        prevData.supplement_entries
          .map((e) => e.product_id)
          .filter((id): id is number => id != null),
      );
      const rows = sticky
        .filter((p) => !present.has(p.id))
        .map((p) => ({
          time: null,
          name: p.name,
          dose_mg: p.default_dose ?? null,
          product_id: p.id,
        }));
      return rows.length === 0
        ? prevData
        : {
            ...prevData,
            supplement_entries: [...prevData.supplement_entries, ...rows],
          };
    });
  }, [loading, exists, loadError, isToday, products, currentDate, setFormData]);

  const bedtimeHour = settings?.typical_bedtime
    ? Number(settings.typical_bedtime.split(":")[0]) +
      Number(settings.typical_bedtime.split(":")[1]) / 60
    : null;

  const caffeinePoints = useCaffeineDecay(
    formData.caffeine_entries,
    settings?.caffeine_sensitivity ?? "normal",
    bedtimeHour,
  );

  const update = <K extends keyof DailyLogCreate>(
    key: K,
    value: DailyLogCreate[K],
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  /** Set a section's entries and — when it now holds real data — clear the
   * given absence keys (entries and an absence are mutually exclusive). */
  const updateEntries = <K extends keyof DailyLogCreate>(
    key: K,
    value: DailyLogCreate[K] & unknown[],
    clearKeys: string[],
  ) => {
    setFormData((prev) => ({
      ...prev,
      [key]: value,
      section_absences:
        value.length > 0
          ? prev.section_absences.filter((k) => !clearKeys.includes(k))
          : prev.section_absences,
    }));
  };

  const updateHabits = (value: HabitEntryCreate[]) => {
    const presentKeys = value
      .map((e) => HABIT_ABSENCE_KEYS[e.habit_type])
      .filter((k): k is string => k != null);
    setFormData((prev) => ({
      ...prev,
      habit_entries: value,
      section_absences: prev.section_absences.filter(
        (k) => !presentKeys.includes(k),
      ),
    }));
  };

  const toggleAbsence = (key: string) => {
    setFormData((prev) => ({
      ...prev,
      section_absences: prev.section_absences.includes(key)
        ? prev.section_absences.filter((k) => k !== key)
        : [...prev.section_absences, key],
    }));
  };

  /** Absence control for a single-key section — only while it has no
   * entries (adding one clears the key via updateEntries). */
  const absenceFor = (
    key: string,
    subject: string,
    hasEntries: boolean,
  ): SectionAbsenceControl | undefined =>
    hasEntries
      ? undefined
      : {
          active: formData.section_absences.includes(key),
          onToggle: () => toggleAbsence(key),
          subject,
        };

  const handleCopied = (log: DailyLogOut) => {
    // Same stale-date guard as copy-yesterday/create-product: the copy POST
    // commits server-side to the day it was started on; if the user has
    // navigated since, the late response must not replace the CURRENT day's
    // form (Save would then PUT day A's data onto day B). The server copy
    // itself is correct and shows up when navigating back to day A.
    if (log.date !== viewedDateRef.current) return;
    setFormData(outToCreate(log));
  };

  // Stale-response guard (mirrors useDailyLog's cancellation idiom): an
  // async callback started while viewing one day must not write into the
  // form after the user navigates to a different day — the ref tracks the
  // currently viewed date, and each callback compares it against the date
  // captured when the request started.
  const viewedDateRef = useRef(currentDate);
  useEffect(() => {
    viewedDateRef.current = currentDate;
  }, [currentDate]);

  /** #110: pull yesterday's supplement rows (products, doses, times) into
   * today's unsaved state. Each source row claims a DISTINCT pre-existing
   * row (split dosing — two rows of one product — must copy as two rows,
   * never collapse into one); unmatched source rows are appended. Resolves
   * the number of source entries, or null when the response is stale (the
   * user navigated to another day mid-request): a stale response must
   * neither merge yesterday-of-A's rows into day B's form nor surface a
   * success/failure status that reads as belonging to day B. */
  const copyYesterdaySupplements = async (): Promise<number | null> => {
    const forDate = currentDate;
    let out: DailyLogOut;
    try {
      out = await getDailyLog(addDays(forDate, -1));
    } catch (e) {
      if (viewedDateRef.current !== forDate) return null;
      if (e instanceof ApiError && e.status === 404) return 0;
      throw e;
    }
    if (viewedDateRef.current !== forDate) return null;
    const rows = out.supplement_entries.map(
      ({ time, name, dose_mg, product_id }) => ({
        // A 0-dose row is "none today" and must never carry a time (it would
        // feed the timing predictor a phantom sample) — strip times that
        // pre-fix saves may have left alongside a 0 dose.
        time: dose_mg === 0 ? null : time,
        name,
        dose_mg,
        product_id,
      }),
    );
    if (rows.length === 0) return 0;
    setFormData((prev) => {
      const next = [...prev.supplement_entries];
      const claimed = new Set<number>();
      for (const row of rows) {
        const idx = next.findIndex(
          (e, j) =>
            !claimed.has(j) &&
            (row.product_id != null
              ? e.product_id === row.product_id
              : e.product_id == null && e.name === row.name),
        );
        if (idx >= 0) {
          next[idx] = { ...next[idx], dose_mg: row.dose_mg, time: row.time };
          claimed.add(idx);
        } else {
          // Appended rows are claimed too: a second source row of the same
          // product must append its own row, not overwrite the first.
          claimed.add(next.length);
          next.push(row);
        }
      }
      return { ...prev, supplement_entries: next };
    });
    return rows.length;
  };

  /** Create a library product and append its prefilled row to the day the
   * create started on. The append is FUNCTIONAL — edits made while the POST
   * is in flight land on current state, not a snapshot — and date-guarded:
   * a slow response arriving after navigation must not push a row into a
   * different day's form. The library append has no date scope and always
   * applies. */
  const handleCreateProduct = async (
    data: SupplementProductCreate,
  ): Promise<SupplementProduct> => {
    const forDate = currentDate;
    const created = await createSupplementProduct(data);
    setProducts((prev) => (prev === null ? [created] : [...prev, created]));
    if (viewedDateRef.current === forDate) {
      setFormData((prev) => ({
        ...prev,
        supplement_entries: [
          ...prev.supplement_entries,
          rowForProduct(created),
        ],
      }));
    }
    return created;
  };

  if (loading) {
    return (
      <div
        style={{
          color: "var(--color-text-muted)",
          padding: "2rem",
          textAlign: "center",
        }}
      >
        Loading...
      </div>
    );
  }

  if (loadError) {
    // No editable form here: saving an empty form over a day whose load
    // failed would overwrite whatever that day already holds.
    return (
      <div className="daily-log-page">
        <DateNavigator
          date={currentDate}
          isToday={isToday}
          onPrev={prev}
          onNext={next}
          onToday={today}
        />
        <div className="daily-log-load-error" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={reload}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="daily-log-page">
      <DateNavigator
        date={currentDate}
        isToday={isToday}
        onPrev={prev}
        onNext={next}
        onToday={today}
      />

      <WarningBanner warnings={warnings} onDismiss={() => setWarnings([])} />

      <div className="daily-log-actions">
        <CopyDayButton targetDate={currentDate} onCopied={handleCopied} />
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              fontSize: "0.85rem",
              color: "var(--color-text-secondary)",
            }}
          >
            <input
              type="checkbox"
              checked={formData.is_sick ?? false}
              onChange={(e) => update("is_sick", e.target.checked || null)}
            />
            Sick day
          </label>
        </div>
      </div>

      <div className="daily-log-sections">
        {visible("caffeine", formData.caffeine_entries.length > 0) && (
          <CaffeineSection
            entries={formData.caffeine_entries}
            onChange={(v) => updateEntries("caffeine_entries", v, ["caffeine"])}
            absence={absenceFor(
              "caffeine",
              "caffeine",
              formData.caffeine_entries.length > 0,
            )}
          />
        )}

        {formData.caffeine_entries.length > 0 && (
          <CaffeineChart points={caffeinePoints} bedtimeHour={bedtimeHour} />
        )}

        {visible("meals", formData.meal_entries.length > 0) && (
          <MealSection
            entries={formData.meal_entries}
            onChange={(v) => updateEntries("meal_entries", v, ["meal"])}
            absence={absenceFor(
              "meal",
              "meals",
              formData.meal_entries.length > 0,
            )}
          />
        )}

        {visible("supplements", formData.supplement_entries.length > 0) && (
          <SupplementSection
            entries={formData.supplement_entries}
            onChange={(v) => update("supplement_entries", v)}
            products={products}
            onCreateProduct={handleCreateProduct}
            onCopyYesterday={copyYesterdaySupplements}
          />
        )}

        {visible("habits", formData.habit_entries.length > 0) && (
          <HabitSection
            entries={formData.habit_entries}
            onChange={updateHabits}
            absences={formData.section_absences}
            onToggleAbsence={toggleAbsence}
          />
        )}

        {visible(
          "stimulating",
          formData.stimulating_activity_entries.length > 0,
        ) && (
          <StimulatingSection
            entries={formData.stimulating_activity_entries}
            onChange={(v) =>
              updateEntries("stimulating_activity_entries", v, ["stimulating"])
            }
            absence={absenceFor(
              "stimulating",
              "stimulating activities",
              formData.stimulating_activity_entries.length > 0,
            )}
          />
        )}

        {visible("sexual", formData.sexual_activity_entry !== null) && (
          <SexualActivitySection
            entry={formData.sexual_activity_entry}
            onChange={(v) => update("sexual_activity_entry", v)}
          />
        )}

        {visible("rituals", formData.pre_bed_ritual_entries.length > 0) && (
          <PreBedRitualSection
            entries={formData.pre_bed_ritual_entries}
            onChange={(v) =>
              updateEntries("pre_bed_ritual_entries", v, ["ritual"])
            }
            absence={absenceFor(
              "ritual",
              "pre-bed rituals",
              formData.pre_bed_ritual_entries.length > 0,
            )}
          />
        )}

        {visible("naps", formData.nap_entries.length > 0) && (
          <NapSection
            entries={formData.nap_entries}
            onChange={(v) => updateEntries("nap_entries", v, ["nap"])}
            absence={absenceFor("nap", "naps", formData.nap_entries.length > 0)}
          />
        )}

        {visible("sunlight", formData.sunlight_entries.length > 0) && (
          <SunlightSection
            entries={formData.sunlight_entries}
            onChange={(v) => updateEntries("sunlight_entries", v, ["sunlight"])}
            absence={absenceFor(
              "sunlight",
              "sunlight",
              formData.sunlight_entries.length > 0,
            )}
          />
        )}

        {visible("redLight", formData.red_light_entries.length > 0) && (
          <RedLightSection
            entries={formData.red_light_entries}
            onChange={(v) =>
              updateEntries("red_light_entries", v, ["red_light"])
            }
            absence={absenceFor(
              "red_light",
              "red light",
              formData.red_light_entries.length > 0,
            )}
          />
        )}

        {visible("nsdr", formData.nsdr_entries.length > 0) && (
          <NSDRSection
            entries={formData.nsdr_entries}
            onChange={(v) => updateEntries("nsdr_entries", v, ["nsdr"])}
            absence={absenceFor(
              "nsdr",
              "NSDR",
              formData.nsdr_entries.length > 0,
            )}
          />
        )}
      </div>

      <div className="daily-log-notes">
        <label
          style={{ fontSize: "0.85rem", color: "var(--color-text-secondary)" }}
        >
          Notes
          <textarea
            value={formData.notes ?? ""}
            onChange={(e) => update("notes", e.target.value || null)}
            placeholder="Any other notes about today..."
            rows={3}
            style={{ width: "100%", resize: "vertical" }}
          />
        </label>
      </div>

      <div className="daily-log-save">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="daily-log-save-btn"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        {saveStatus === "saved" && (
          <span className="daily-log-save-ok" role="status">
            Saved ✓
          </span>
        )}
        {saveStatus === "error" && saveError && (
          <span className="daily-log-save-error" role="alert">
            {saveError}
          </span>
        )}
      </div>
    </div>
  );
}
