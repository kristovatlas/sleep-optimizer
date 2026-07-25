import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { getDailyLog, saveDailyLog } from "../api/dailyLog";
import type { DailyLogCreate, DailyLogOut } from "../types";
import { ApiError } from "../types/api";

export type SaveStatus = "idle" | "saved" | "error";

/** Human-readable message for a failed request. FastAPI 422s carry an array
 * in `detail` at runtime despite the string typing — never render raw JSON —
 * and HTTP/2 has no statusText, so an empty detail also gets the fallback. */
function errorMessage(e: unknown, action: string): string {
  if (e instanceof ApiError) {
    return typeof e.detail === "string" && e.detail !== ""
      ? `${action} failed: ${e.detail}`
      : `${action} failed (HTTP ${e.status})`;
  }
  if (e instanceof TypeError) {
    return `${action} failed: could not reach the backend`;
  }
  return `${action} failed: unexpected error`;
}

function emptyLog(): DailyLogCreate {
  return {
    is_sick: null,
    notes: null,
    caffeine_entries: [],
    meal_entries: [],
    supplement_entries: [],
    habit_entries: [],
    stimulating_activity_entries: [],
    sexual_activity_entry: null,
    pre_bed_ritual_entries: [],
    nap_entries: [],
    sunlight_entries: [],
    red_light_entries: [],
    nsdr_entries: [],
    section_absences: [],
  };
}

/** Strip `id` and `date` from Out entries to produce Create form state.
 *
 * ROUND-TRIP CONTRACT (#161 Lane 3a/3b): `section_absences` MUST be carried
 * from every GET into the form state — the PUT replaces the day's absences
 * with whatever the payload holds, so dropping them here would make any
 * unrelated save silently wipe the day's explicit "none today" records.
 */
export function outToCreate(out: DailyLogOut): DailyLogCreate {
  return {
    is_sick: out.is_sick,
    notes: out.notes,
    caffeine_entries: out.caffeine_entries.map(
      ({ time, amount_mg, source }) => ({
        time,
        amount_mg,
        source,
      }),
    ),
    meal_entries: out.meal_entries.map(({ time, is_last_meal, notes }) => ({
      time,
      is_last_meal,
      notes,
    })),
    supplement_entries: out.supplement_entries.map(
      ({ time, name, dose_mg, product_id }) => ({
        time,
        name,
        dose_mg,
        product_id,
      }),
    ),
    habit_entries: out.habit_entries.map(
      ({ habit_type, time, value, duration_minutes, notes }) => ({
        habit_type,
        time,
        value,
        duration_minutes,
        notes,
      }),
    ),
    stimulating_activity_entries: out.stimulating_activity_entries.map(
      ({ end_time, activity_type, duration_minutes }) => ({
        end_time,
        activity_type,
        duration_minutes,
      }),
    ),
    sexual_activity_entry: out.sexual_activity_entry
      ? {
          time: out.sexual_activity_entry.time,
          activity_type: out.sexual_activity_entry.activity_type,
        }
      : null,
    pre_bed_ritual_entries: out.pre_bed_ritual_entries.map(
      ({ time, ritual_type, duration_minutes }) => ({
        time,
        ritual_type,
        duration_minutes,
      }),
    ),
    nap_entries: out.nap_entries.map(
      ({ start_time, end_time, duration_minutes }) => ({
        start_time,
        end_time,
        duration_minutes,
      }),
    ),
    sunlight_entries: out.sunlight_entries.map(
      ({ start_time, duration_minutes, estimated_lux, notes }) => ({
        start_time,
        duration_minutes,
        estimated_lux,
        notes,
      }),
    ),
    red_light_entries: out.red_light_entries.map(
      ({ panel_id, start_time, duration_minutes, distance_inches }) => ({
        panel_id,
        start_time,
        duration_minutes,
        distance_inches,
      }),
    ),
    nsdr_entries: out.nsdr_entries.map(
      ({ time, duration_minutes, nsdr_type }) => ({
        time,
        duration_minutes,
        nsdr_type,
      }),
    ),
    section_absences: [...(out.section_absences ?? [])],
  };
}

export function useDailyLog(date: string) {
  const [formData, rawSetFormData] = useState<DailyLogCreate>(emptyLog);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [exists, setExists] = useState(false);
  const dateRef = useRef(date);
  dateRef.current = date;

  useEffect(() => {
    // Cancellation guard: a slow response for a day the user has already
    // navigated away from must not stomp the current day's form or error.
    let cancelled = false;
    setLoading(true);
    setWarnings([]);
    setLoadError(null);
    setSaveStatus("idle");
    setSaveError(null);
    getDailyLog(date)
      .then((out) => {
        if (cancelled) return;
        rawSetFormData(outToCreate(out));
        setExists(true);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          rawSetFormData(emptyLog());
          setExists(false);
        } else {
          // Anything else must NOT fall through to an empty editable form:
          // saving that form would overwrite a day that may hold data.
          setLoadError(errorMessage(e, "Loading this day"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [date, reloadNonce]);

  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

  /** Any edit invalidates the "Saved ✓" state and clears a stale error. */
  const setFormData: Dispatch<SetStateAction<DailyLogCreate>> = useCallback(
    (value) => {
      setSaveStatus("idle");
      setSaveError(null);
      rawSetFormData(value);
    },
    [],
  );

  const save = useCallback(async () => {
    setSaving(true);
    setSaveStatus("idle");
    setSaveError(null);
    // Stale warnings from a previous save must not sit next to this
    // attempt's outcome and read as if they belong to it.
    setWarnings([]);
    try {
      const res = await saveDailyLog(date, formData);
      // Navigated away mid-save? The result belongs to the old day —
      // don't overwrite the new day's form or claim "Saved ✓" on it.
      if (dateRef.current !== date) return res;
      rawSetFormData(outToCreate(res.data));
      setWarnings(res.warnings);
      setExists(true);
      setSaveStatus("saved");
      return res;
    } catch (e: unknown) {
      if (dateRef.current !== date) return null;
      setSaveStatus("error");
      setSaveError(errorMessage(e, "Save"));
      return null;
    } finally {
      setSaving(false);
    }
  }, [date, formData]);

  return {
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
  };
}
