import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import { SelectInput } from "../../shared/SelectInput";
import { CaffeineSource, CAFFEINE_SOURCE_LABELS } from "../../../types/enums";
import type { CaffeineEntryCreate } from "../../../types";
import "./CaffeineSection.css";

interface CaffeineSectionProps {
  entries: CaffeineEntryCreate[];
  onChange: (entries: CaffeineEntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

const QUICK_ADD: { label: string; mg: number; source: CaffeineSource }[] = [
  { label: "Espresso (63mg)", mg: 63, source: CaffeineSource.ESPRESSO },
  { label: "Coffee (95mg)", mg: 95, source: CaffeineSource.DRIP_COFFEE },
  { label: "Tea (47mg)", mg: 47, source: CaffeineSource.TEA },
];

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

export function CaffeineSection({
  entries,
  onChange,
  absence,
}: CaffeineSectionProps) {
  const totalMg = entries.reduce((sum, e) => sum + e.amount_mg, 0);

  const addEntry = (entry: CaffeineEntryCreate) =>
    onChange([...entries, entry]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: CaffeineEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  return (
    <SectionWrapper
      title="Caffeine"
      count={entries.length}
      storageKey="caffeine"
      absence={absence}
      defaultOpen
    >
      <div className="caffeine-quick-add">
        {QUICK_ADD.map((qa) => (
          <button
            key={qa.source}
            type="button"
            className="quick-add-btn"
            onClick={() =>
              addEntry({
                time: nowTimeStr(),
                amount_mg: qa.mg,
                source: qa.source,
              })
            }
          >
            + {qa.label}
          </button>
        ))}
      </div>

      {entries.map((entry, i) => (
        <div key={i} className="caffeine-entry">
          <TimePicker
            label="Time"
            value={entry.time}
            onChange={(v) => updateEntry(i, { ...entry, time: v })}
          />
          <NumberInput
            label="Amount"
            value={entry.amount_mg}
            onChange={(v) => updateEntry(i, { ...entry, amount_mg: v ?? 0 })}
            unit="mg"
            min={1}
            max={600}
          />
          <SelectInput
            label="Source"
            value={entry.source}
            onChange={(v) => updateEntry(i, { ...entry, source: v })}
            options={Object.values(CaffeineSource)}
            labels={CAFFEINE_SOURCE_LABELS}
          />
          <button
            type="button"
            className="caffeine-remove"
            onClick={() => removeEntry(i)}
          >
            Remove
          </button>
        </div>
      ))}

      {totalMg > 0 && (
        <p className="caffeine-total">
          Total: <strong>{totalMg}mg</strong>
        </p>
      )}

      <button
        type="button"
        className="caffeine-add-custom"
        onClick={() =>
          addEntry({
            time: nowTimeStr(),
            amount_mg: 95,
            source: CaffeineSource.OTHER,
          })
        }
      >
        + Add entry
      </button>
    </SectionWrapper>
  );
}
