import { SectionWrapper } from "./SectionWrapper";
import { AbsenceChip } from "../AbsenceToggle";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import { SelectInput } from "../../shared/SelectInput";
import { SliderInput } from "../../shared/SliderInput";
import {
  HabitType,
  HABIT_TYPE_LABELS,
  ExerciseIntensity,
} from "../../../types/enums";
import type { HabitEntryCreate } from "../../../types";

interface HabitSectionProps {
  entries: HabitEntryCreate[];
  onChange: (entries: HabitEntryCreate[]) => void;
  /** Current section_absences keys (whole day; only habit keys are used). */
  absences: string[];
  onToggleAbsence: (key: string) => void;
}

/** The Habits section hosts several absence keys — one per absence-capable
 * habit type (#159) — so it gets per-key chips instead of the single
 * section-level AbsenceToggle. */
const HABIT_ABSENCE_ITEMS: {
  key: string;
  habitType: HabitType;
  label: string;
  ariaLabel: string;
}[] = [
  {
    key: "exercise",
    habitType: HabitType.EXERCISE,
    label: "Exercise",
    ariaLabel: "No exercise today",
  },
  {
    key: "alcohol",
    habitType: HabitType.ALCOHOL,
    label: "Alcohol",
    ariaLabel: "No alcohol today",
  },
  {
    key: "blue_blockers",
    habitType: HabitType.BLUE_BLOCKERS_ON,
    label: "Blue blockers",
    ariaLabel: "No blue blockers today",
  },
  {
    key: "screens_off",
    habitType: HabitType.SCREENS_OFF,
    label: "Screens off",
    ariaLabel: "No screens-off today",
  },
  {
    key: "sauna",
    habitType: HabitType.SAUNA,
    label: "Sauna",
    ariaLabel: "No sauna today",
  },
  {
    key: "warm_shower",
    habitType: HabitType.WARM_SHOWER,
    label: "Warm shower",
    ariaLabel: "No warm shower today",
  },
];

const EXERCISE_LABELS: Record<string, string> = {
  light: "Light",
  moderate: "Moderate",
  intense: "Intense",
};

export function HabitSection({
  entries,
  onChange,
  absences,
  onToggleAbsence,
}: HabitSectionProps) {
  const addEntry = (habitType: HabitType) =>
    onChange([
      ...entries,
      {
        habit_type: habitType,
        time: null,
        value: null,
        duration_minutes: null,
        notes: null,
      },
    ]);
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: HabitEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  const usedTypes = new Set(entries.map((e) => e.habit_type));

  const renderFields = (entry: HabitEntryCreate, i: number) => {
    switch (entry.habit_type) {
      case HabitType.EXERCISE:
        return (
          <>
            <SelectInput
              label="Intensity"
              value={(entry.value as string) ?? ExerciseIntensity.MODERATE}
              onChange={(v) => updateEntry(i, { ...entry, value: v })}
              options={Object.values(ExerciseIntensity)}
              labels={EXERCISE_LABELS}
            />
            <NumberInput
              label="Duration"
              value={entry.duration_minutes}
              onChange={(v) =>
                updateEntry(i, { ...entry, duration_minutes: v })
              }
              unit="min"
              min={1}
              max={300}
            />
            <TimePicker
              label="Time"
              value={entry.time}
              onChange={(v) => updateEntry(i, { ...entry, time: v })}
            />
          </>
        );
      case HabitType.ALCOHOL:
        return (
          <>
            <NumberInput
              label="Drinks"
              value={entry.value ? Number(entry.value) : null}
              onChange={(v) =>
                updateEntry(i, {
                  ...entry,
                  value: v != null ? String(v) : null,
                })
              }
              min={1}
              max={20}
            />
            <TimePicker
              label="Last drink time"
              value={entry.time}
              onChange={(v) => updateEntry(i, { ...entry, time: v })}
            />
          </>
        );
      case HabitType.ROOM_TEMP_F:
        return (
          <NumberInput
            label="Temperature"
            value={entry.value ? Number(entry.value) : null}
            onChange={(v) =>
              updateEntry(i, { ...entry, value: v != null ? String(v) : null })
            }
            unit="°F"
            min={55}
            max={85}
          />
        );
      case HabitType.STRESS_LEVEL:
        return (
          <SliderInput
            label="Stress Level"
            value={entry.value ? Number(entry.value) : null}
            onChange={(v) =>
              updateEntry(i, { ...entry, value: v != null ? String(v) : null })
            }
            min={1}
            max={5}
            labels={["Very Low", "Low", "Medium", "High", "Very High"]}
          />
        );
      case HabitType.SAUNA:
      case HabitType.WARM_SHOWER:
        return (
          <>
            <NumberInput
              label="Duration"
              value={entry.duration_minutes}
              onChange={(v) =>
                updateEntry(i, { ...entry, duration_minutes: v })
              }
              unit="min"
              min={1}
            />
            <TimePicker
              label="Time"
              value={entry.time}
              onChange={(v) => updateEntry(i, { ...entry, time: v })}
            />
          </>
        );
      default:
        return (
          <TimePicker
            label="Time"
            value={entry.time}
            onChange={(v) => updateEntry(i, { ...entry, time: v })}
          />
        );
    }
  };

  return (
    <SectionWrapper title="Habits" count={entries.length} storageKey="habits">
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {Object.values(HabitType)
          .filter((ht) => !usedTypes.has(ht) || ht === HabitType.EXERCISE)
          .map((ht) => (
            <button
              key={ht}
              type="button"
              onClick={() => addEntry(ht)}
              className="quick-add-btn"
            >
              + {HABIT_TYPE_LABELS[ht]}
            </button>
          ))}
      </div>

      <div className="absence-chip-row">
        <span className="absence-chip-row-label">None today:</span>
        {HABIT_ABSENCE_ITEMS.filter((it) => !usedTypes.has(it.habitType)).map(
          (it) => (
            <AbsenceChip
              key={it.key}
              active={absences.includes(it.key)}
              onToggle={() => onToggleAbsence(it.key)}
              label={it.label}
              ariaLabel={it.ariaLabel}
            />
          ),
        )}
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
          <strong
            style={{ color: "var(--color-text-secondary)", fontSize: "0.9rem" }}
          >
            {HABIT_TYPE_LABELS[entry.habit_type]}
          </strong>
          {renderFields(entry, i)}
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
