import { useEffect, useState } from "react";
import { useDateNavigation } from "../../hooks/useDateNavigation";
import { useDailyLog, outToCreate } from "../../hooks/useDailyLog";
import { useCaffeineDecay } from "../../hooks/useCaffeineDecay";
import { getSettings } from "../../api/settings";
import {
  listSupplementProducts,
  createSupplementProduct,
} from "../../api/supplements";
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
    save,
  } = useDailyLog(currentDate);
  const [settings, setSettings] = useState<UserSettingsOut | null>(null);
  // Supplement library; null = unavailable (still loading or fetch failed).
  const [products, setProducts] = useState<SupplementProduct[] | null>(null);
  // #47: read once per mount — Settings edits land on the next visit here.
  const [tracked] = useState(readTrackedSections);

  // An untracked section still renders when the viewed day holds data in
  // it: hiding recorded entries would be worse than showing an extra
  // section (and the form still submits the full payload either way).
  const visible = (key: SectionKey, hasData: boolean) =>
    tracked.has(key) || hasData;

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
    setFormData(outToCreate(log));
  };

  const handleCreateProduct = async (
    data: SupplementProductCreate,
  ): Promise<SupplementProduct> => {
    const created = await createSupplementProduct(data);
    setProducts((prev) => (prev === null ? [created] : [...prev, created]));
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
