import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import { SelectInput } from "../../shared/SelectInput";
import { PreBedRitualType, PRE_BED_RITUAL_LABELS } from "../../../types/enums";
import type { PreBedRitualCreate } from "../../../types";

interface PreBedRitualSectionProps {
  entries: PreBedRitualCreate[];
  onChange: (entries: PreBedRitualCreate[]) => void;
  absence?: SectionAbsenceControl;
}

export function PreBedRitualSection({
  entries,
  onChange,
  absence,
}: PreBedRitualSectionProps) {
  const addEntry = () =>
    onChange([
      ...entries,
      {
        time: null,
        ritual_type: PreBedRitualType.DEEP_BREATHING,
        duration_minutes: null,
      },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: PreBedRitualCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="Pre-Bed Rituals"
      count={entries.length}
      storageKey="rituals"
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
            value={entry.ritual_type}
            onChange={(v) => updateEntry(i, { ...entry, ritual_type: v })}
            options={Object.values(PreBedRitualType)}
            labels={PRE_BED_RITUAL_LABELS}
          />
          <TimePicker
            label="Time"
            value={entry.time}
            onChange={(v) => updateEntry(i, { ...entry, time: v })}
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
        + Add ritual
      </button>
    </SectionWrapper>
  );
}
