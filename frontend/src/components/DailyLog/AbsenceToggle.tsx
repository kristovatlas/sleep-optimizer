import "./AbsenceToggle.css";

/**
 * Explicit-absence controls (#159/#161, ADR 003 third data state).
 *
 * AbsenceToggle: per-section "Mark none today" / "Undo — restore today"
 * button for single-key sections. AbsenceChip: compact per-key toggle for
 * sections hosting several absence keys (the Habits section).
 */

interface AbsenceToggleProps {
  active: boolean;
  onToggle: () => void;
  /** Lowercase noun for the accessible name, e.g. "caffeine", "naps". */
  subject: string;
}

export function AbsenceToggle({
  active,
  onToggle,
  subject,
}: AbsenceToggleProps) {
  return (
    <div className={`absence-toggle${active ? " absence-toggle--active" : ""}`}>
      {active && <span className="absence-toggle-state">None today</span>}
      <button
        type="button"
        className="absence-toggle-btn"
        aria-label={
          active
            ? `Undo — restore ${subject} today`
            : `Mark ${subject} none today`
        }
        onClick={onToggle}
      >
        {active ? "Undo — restore today" : "Mark none today"}
      </button>
    </div>
  );
}

interface AbsenceChipProps {
  active: boolean;
  onToggle: () => void;
  /** Visible chip text, e.g. "Alcohol". */
  label: string;
  /** Full accessible name, e.g. "No alcohol today". */
  ariaLabel: string;
}

export function AbsenceChip({
  active,
  onToggle,
  label,
  ariaLabel,
}: AbsenceChipProps) {
  return (
    <button
      type="button"
      className={`absence-chip${active ? " absence-chip--active" : ""}`}
      aria-pressed={active}
      aria-label={ariaLabel}
      onClick={onToggle}
    >
      {label}
    </button>
  );
}
