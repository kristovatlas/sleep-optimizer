import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import { SelectInput } from "../../shared/SelectInput";
import {
  StimulatingActivityType,
  STIMULATING_ACTIVITY_LABELS,
} from "../../../types/enums";
import type { StimulatingActivityCreate } from "../../../types";

interface StimulatingSectionProps {
  entries: StimulatingActivityCreate[];
  onChange: (entries: StimulatingActivityCreate[]) => void;
  absence?: SectionAbsenceControl;
}

export function StimulatingSection({
  entries,
  onChange,
  absence,
}: StimulatingSectionProps) {
  const addEntry = () =>
    onChange([
      ...entries,
      {
        end_time: null,
        activity_type: StimulatingActivityType.TV_MOVIES,
        duration_minutes: null,
      },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: StimulatingActivityCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="Stimulating Activities"
      count={entries.length}
      storageKey="stimulating"
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
          <SelectInput
            label="Type"
            value={entry.activity_type}
            onChange={(v) => updateEntry(i, { ...entry, activity_type: v })}
            options={Object.values(StimulatingActivityType)}
            labels={STIMULATING_ACTIVITY_LABELS}
          />
          <TimePicker
            label="End Time"
            value={entry.end_time}
            onChange={(v) => updateEntry(i, { ...entry, end_time: v })}
          />
          <NumberInput
            label="Duration"
            value={entry.duration_minutes}
            onChange={(v) => updateEntry(i, { ...entry, duration_minutes: v })}
            unit="min"
            min={1}
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
          padding: "8px 16px",
          borderRadius: "6px",
          cursor: "pointer",
        }}
      >
        + Add activity
      </button>
    </SectionWrapper>
  );
}
