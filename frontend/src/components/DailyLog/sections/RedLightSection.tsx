import { useEffect, useState } from "react";
import { SectionWrapper } from "./SectionWrapper";
import type { SectionAbsenceControl } from "./SectionWrapper";
import { TimePicker } from "../../shared/TimePicker";
import { NumberInput } from "../../shared/NumberInput";
import { listPanels, type RedLightPanelOut } from "../../../api/redLightPanels";
import type { RedLightEntryCreate } from "../../../types";

interface RedLightSectionProps {
  entries: RedLightEntryCreate[];
  onChange: (entries: RedLightEntryCreate[]) => void;
  absence?: SectionAbsenceControl;
}

/** A panel's rated distance is only a usable session default when positive
 * (the entry field is gt=0 server-side; the panel field still allows 0). */
function ratedDistance(inches: number | null | undefined): number | null {
  return inches != null && inches > 0 ? inches : null;
}

export function RedLightSection({
  entries,
  onChange,
  absence,
}: RedLightSectionProps) {
  const [panels, setPanels] = useState<RedLightPanelOut[]>([]);

  useEffect(() => {
    listPanels()
      .then(setPanels)
      .catch(() => {});
  }, []);

  const addEntry = () => {
    const panel = panels[0];
    onChange([
      ...entries,
      {
        panel_id: panel?.id ?? null,
        start_time: null,
        duration_minutes: null,
        // pre-fill the session distance with the panel's rated distance
        distance_inches: ratedDistance(panel?.default_distance_inches),
      },
    ]);
  };
  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: RedLightEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  const getDose = (entry: RedLightEntryCreate): string | null => {
    if (!entry.panel_id || !entry.duration_minutes) return null;
    const panel = panels.find((p) => p.id === entry.panel_id);
    if (!panel?.irradiance_mw_cm2) return null;
    // Mirror the backend inverse-square adjustment (models.py): irradiance
    // is rated at the panel's default distance; a different session distance
    // scales by (reference / actual)^2. Kept in sync so the shown dose
    // matches the persisted dose_joules_cm2.
    let factor = 1;
    const ref = panel.default_distance_inches;
    const actual = entry.distance_inches;
    if (ref != null && actual != null && ref > 0 && actual > 0) {
      factor = (ref / actual) ** 2;
    }
    const joules =
      (panel.irradiance_mw_cm2 * factor * entry.duration_minutes * 60) / 1000;
    return `${joules.toFixed(2)} J/cm²`;
  };

  return (
    <SectionWrapper
      title="Red Light Therapy"
      count={entries.length}
      storageKey="redLight"
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
          {panels.length > 0 && (
            <div>
              <label
                style={{
                  fontSize: "0.85rem",
                  color: "var(--color-text-secondary)",
                }}
              >
                Panel
              </label>
              <select
                value={entry.panel_id ?? ""}
                onChange={(e) => {
                  const newId = e.target.value ? Number(e.target.value) : null;
                  const newPanel = panels.find((p) => p.id === newId);
                  updateEntry(i, {
                    ...entry,
                    panel_id: newId,
                    // Re-fill distance from the new panel's rated distance —
                    // otherwise the old distance would be measured against the
                    // new panel's reference, silently skewing the dose.
                    distance_inches: ratedDistance(
                      newPanel?.default_distance_inches,
                    ),
                  });
                }}
                style={{ width: "100%" }}
              >
                <option value="">No panel</option>
                {panels.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}
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
            max={60}
          />
          <NumberInput
            label="Distance"
            value={entry.distance_inches}
            onChange={(v) =>
              updateEntry(i, {
                ...entry,
                // gt=0 server-side; 0/negative means "unspecified" → null
                distance_inches: v !== null && v > 0 ? v : null,
              })
            }
            unit="in"
            min={0.5}
            step={0.5}
          />
          {getDose(entry) && (
            <p
              style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}
            >
              Dose: {getDose(entry)}
            </p>
          )}
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
        + Add session
      </button>
    </SectionWrapper>
  );
}
