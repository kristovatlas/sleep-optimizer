import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { Toggle } from "../../shared/Toggle";
import type { MealEntryCreate } from "../../../types";

interface MealSectionProps {
  entries: MealEntryCreate[];
  onChange: (entries: MealEntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

export function MealSection({ entries, onChange, absence }: MealSectionProps) {
  const addEntry = () =>
    onChange([
      ...entries,
      { time: nowTimeStr(), is_last_meal: null, notes: null },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: MealEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="Meals"
      count={entries.length}
      storageKey="meals"
      absence={absence}
    >
      {entries.map((entry, i) => (
        <div
          key={i}
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
            label="Time"
            value={entry.time}
            onChange={(v) => updateEntry(i, { ...entry, time: v })}
          />
          <Toggle
            label="Last meal of the day"
            checked={entry.is_last_meal}
            onChange={(v) => updateEntry(i, { ...entry, is_last_meal: v })}
          />
          <input
            placeholder="Notes (optional)"
            value={entry.notes ?? ""}
            onChange={(e) =>
              updateEntry(i, { ...entry, notes: e.target.value || null })
            }
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
      <button
        type="button"
        onClick={addEntry}
        style={{
          background: "transparent",
          color: "var(--color-text-accent)",
          border: "1px dashed var(--color-border-light)",
          fontSize: "0.85rem",
        }}
      >
        + Add meal
      </button>
    </SectionWrapper>
  );
}
