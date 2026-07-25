import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { SelectInput } from "../../shared/SelectInput";
import { NumberInput } from "../../shared/NumberInput";
import { NSDRType, NSDR_TYPE_LABELS } from "../../../types/enums";
import type { NSDREntryCreate } from "../../../types";

interface NSDRSectionProps {
  entries: NSDREntryCreate[];
  onChange: (entries: NSDREntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

export function NSDRSection({ entries, onChange, absence }: NSDRSectionProps) {
  const addQuick = (minutes: number | null, type: NSDRType) =>
    onChange([
      ...entries,
      {
        time: nowTimeStr(),
        duration_minutes: minutes,
        nsdr_type: type,
      },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: NSDREntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="NSDR"
      count={entries.length}
      storageKey="nsdr"
      absence={absence}
    >
      <div style={{ display: "flex", gap: "0.5rem" }}>
        {[10, 20, 30].map((min) => (
          <button
            key={min}
            type="button"
            onClick={() => addQuick(min, NSDRType.YOGA_NIDRA)}
            className="quick-add-btn"
          >
            + {min} min
          </button>
        ))}
        <button
          type="button"
          onClick={() => addQuick(null, NSDRType.OTHER)}
          className="quick-add-btn"
        >
          + Custom
        </button>
      </div>

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
            value={entry.nsdr_type}
            onChange={(v) => updateEntry(i, { ...entry, nsdr_type: v })}
            options={Object.values(NSDRType)}
            labels={NSDR_TYPE_LABELS}
          />
          <TimePicker
            label="Time"
            value={entry.time}
            onChange={(v) => updateEntry(i, { ...entry, time: v })}
          />
          <NumberInput
            label="Duration"
            value={entry.duration_minutes}
            onChange={(v) =>
              updateEntry(i, {
                ...entry,
                // integerize typed values (29.7 → 30): backend requires int
                duration_minutes:
                  v === null ? null : Math.max(1, Math.round(v)),
              })
            }
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
    </SectionWrapper>
  );
}
