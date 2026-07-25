import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import type { NapEntryCreate } from "../../../types";

interface NapSectionProps {
  entries: NapEntryCreate[];
  onChange: (entries: NapEntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

// Mirrors the backend NapEntryCreate constraint (schemas.py: ge=1, le=240).
// Deriving values outside it would make the whole day's save fail.
const MIN_DURATION = 1;
const MAX_DURATION = 240;

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

/** "HH:MM[:SS]" → minutes since midnight, or null. */
function timeToMinutes(t: string | null): number | null {
  if (!t) return null;
  const [hh, mm] = t.split(":").map(Number);
  if (Number.isNaN(hh) || Number.isNaN(mm)) return null;
  return hh * 60 + mm;
}

function minutesToTimeStr(total: number): string {
  // Round once up front — rounding only the minutes remainder can produce
  // ":60" (e.g. 899.7 → "14:60:00", which the time input rejects)
  const rounded = Math.round(total);
  const wrapped = ((rounded % 1440) + 1440) % 1440;
  const hh = Math.floor(wrapped / 60);
  const mm = wrapped % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00`;
}

function isValidDuration(d: number | null): d is number {
  return (
    d != null && Number.isInteger(d) && d >= MIN_DURATION && d <= MAX_DURATION
  );
}

type NapField = "start_time" | "end_time" | "duration_minutes";

/**
 * Derive whichever of start/end/duration follows from the other two, so the
 * user only ever has to provide two of the three.
 *
 * Anchoring rules: editing duration (or start, when a duration exists) moves
 * the end time; editing the end time recomputes the duration.
 *
 * Derivation only happens from values the backend will accept; invalid input
 * stays quarantined in the field it was typed into instead of being written
 * across fields. A nap that would end past midnight (or start before it)
 * keeps that boundary "not recorded" rather than storing a same-day time
 * that factually belongs to tomorrow/yesterday.
 */
function reconcile(entry: NapEntryCreate, changed: NapField): NapEntryCreate {
  const start = timeToMinutes(entry.start_time);
  const end = timeToMinutes(entry.end_time);

  if (changed === "duration_minutes") {
    if (!isValidDuration(entry.duration_minutes)) return entry;
    if (start != null) {
      const endTotal = start + entry.duration_minutes;
      return endTotal >= 1440
        ? { ...entry, end_time: null }
        : { ...entry, end_time: minutesToTimeStr(endTotal) };
    }
    if (end != null) {
      const startTotal = end - entry.duration_minutes;
      return startTotal < 0
        ? { ...entry, start_time: null }
        : { ...entry, start_time: minutesToTimeStr(startTotal) };
    }
    return entry;
  }

  if (
    changed === "start_time" &&
    start != null &&
    isValidDuration(entry.duration_minutes)
  ) {
    const endTotal = start + entry.duration_minutes;
    return endTotal >= 1440
      ? { ...entry, end_time: null }
      : { ...entry, end_time: minutesToTimeStr(endTotal) };
  }

  if (start != null && end != null) {
    const diff = end - start;
    // diff <= 0 wraps past midnight; a same-time pair (diff 0 → 1440) or a
    // wrap beyond the cap is not a nap — clear the stale duration instead
    // of deriving a value that fails the whole day's save
    const wrapped = diff > 0 ? diff : diff + 1440;
    return {
      ...entry,
      duration_minutes:
        wrapped >= MIN_DURATION && wrapped <= MAX_DURATION ? wrapped : null,
    };
  }

  if (
    changed === "end_time" &&
    end != null &&
    isValidDuration(entry.duration_minutes)
  ) {
    const startTotal = end - entry.duration_minutes;
    return startTotal < 0
      ? { ...entry, start_time: null }
      : { ...entry, start_time: minutesToTimeStr(startTotal) };
  }

  return entry;
}

export function NapSection({ entries, onChange, absence }: NapSectionProps) {
  const addQuickNap = (minutes: number) =>
    onChange([
      ...entries,
      reconcile(
        {
          start_time: nowTimeStr(),
          end_time: null,
          duration_minutes: minutes,
        },
        "duration_minutes",
      ),
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateField = <K extends NapField>(
    index: number,
    field: K,
    value: NapEntryCreate[K],
  ) => {
    // Integerize typed durations (29.7 → 30): fractional minutes would both
    // render ":60" end times and fail the backend's integer field
    const clean =
      field === "duration_minutes" && typeof value === "number"
        ? (Math.round(value) as NapEntryCreate[K])
        : value;
    onChange(
      entries.map((e, i) =>
        i === index ? reconcile({ ...e, [field]: clean }, field) : e,
      ),
    );
  };

  return (
    <SectionWrapper
      title="Naps"
      count={entries.length}
      storageKey="naps"
      absence={absence}
    >
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          onClick={() => addQuickNap(20)}
          className="quick-add-btn"
        >
          + 20 min nap
        </button>
        <button
          type="button"
          onClick={() => addQuickNap(90)}
          className="quick-add-btn"
        >
          + 90 min nap
        </button>
      </div>

      {entries.map((entry, i) => (
        <div
          key={i}
          data-testid="nap-entry"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            padding: "0.75rem",
            border: "1px solid var(--color-border)",
            borderRadius: "6px",
          }}
        >
          <TimePicker
            label="Start Time"
            value={entry.start_time}
            onChange={(v) => updateField(i, "start_time", v)}
          />
          <TimePicker
            label="End Time"
            value={entry.end_time}
            onChange={(v) => updateField(i, "end_time", v)}
          />
          <NumberInput
            label="Duration"
            value={entry.duration_minutes}
            onChange={(v) => updateField(i, "duration_minutes", v)}
            unit="min"
            min={1}
            max={240}
          />
          <button
            type="button"
            onClick={() => removeEntry(i)}
            style={{
              alignSelf: "flex-end",
              background: "transparent",
              color: "var(--color-error)",
              border: "none",
              fontSize: "0.8rem",
            }}
          >
            Remove
          </button>
        </div>
      ))}
    </SectionWrapper>
  );
}
