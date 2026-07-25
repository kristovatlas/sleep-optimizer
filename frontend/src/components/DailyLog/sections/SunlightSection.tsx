import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import type { SunlightEntryCreate } from "../../../types";

interface SunlightSectionProps {
  entries: SunlightEntryCreate[];
  onChange: (entries: SunlightEntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

// Typical illuminance values so users don't have to guess lux by hand
// (#108). Clicking a chip writes the value through the same onChange path
// as the manual input; the field stays fully editable afterwards.
const LUX_PRESETS: { label: string; lux: number }[] = [
  { label: "Heavy overcast (1,000 lux)", lux: 1000 },
  { label: "Overcast (5,000 lux)", lux: 5000 },
  { label: "Partly cloudy (20,000 lux)", lux: 20000 },
  { label: "Full sun (80,000 lux)", lux: 80000 },
  { label: "Indoor, by window (1,000 lux)", lux: 1000 },
];

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

export function SunlightSection({
  entries,
  onChange,
  absence,
}: SunlightSectionProps) {
  const addEntry = () =>
    onChange([
      ...entries,
      {
        start_time: nowTimeStr(),
        duration_minutes: null,
        estimated_lux: null,
        notes: null,
      },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: SunlightEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="Sunlight"
      count={entries.length}
      storageKey="sunlight"
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
            label="Start Time"
            value={entry.start_time}
            onChange={(v) => updateEntry(i, { ...entry, start_time: v })}
          />
          <NumberInput
            label="Duration"
            value={entry.duration_minutes}
            onChange={(v) => updateEntry(i, { ...entry, duration_minutes: v })}
            unit="min"
            min={1}
          />
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {LUX_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                className="quick-add-btn"
                onClick={() =>
                  updateEntry(i, { ...entry, estimated_lux: preset.lux })
                }
              >
                {preset.label}
              </button>
            ))}
          </div>
          <NumberInput
            label="Estimated Lux"
            value={entry.estimated_lux}
            onChange={(v) => updateEntry(i, { ...entry, estimated_lux: v })}
            min={0}
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
        + Add sunlight exposure
      </button>
    </SectionWrapper>
  );
}
