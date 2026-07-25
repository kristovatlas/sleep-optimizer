import { useState } from "react";
import { AbsenceToggle } from "../AbsenceToggle";
import "./SectionWrapper.css";

/** Wiring for a section's explicit "none today" state (#159, ADR 003).
 * Supplied only when the section is absence-capable AND has no entries —
 * real entries and an absence are mutually exclusive in the UI. */
export interface SectionAbsenceControl {
  active: boolean;
  onToggle: () => void;
  /** Lowercase noun for accessible names, e.g. "caffeine". */
  subject: string;
}

interface SectionWrapperProps {
  title: string;
  count?: number;
  storageKey: string;
  defaultOpen?: boolean;
  absence?: SectionAbsenceControl;
  children: React.ReactNode;
}

export function SectionWrapper({
  title,
  count,
  storageKey,
  defaultOpen = false,
  absence,
  children,
}: SectionWrapperProps) {
  const [open, setOpen] = useState(() => {
    const stored = localStorage.getItem(`somnus-section-${storageKey}`);
    if (stored !== null) return stored === "true";
    return defaultOpen;
  });

  const toggle = () => {
    const next = !open;
    setOpen(next);
    localStorage.setItem(`somnus-section-${storageKey}`, String(next));
  };

  return (
    <section className="section-wrapper">
      <button
        type="button"
        className="section-header"
        onClick={toggle}
        aria-expanded={open}
      >
        <span className="section-arrow">{open ? "▾" : "▸"}</span>
        <span className="section-title">{title}</span>
        {absence?.active && (
          <span className="section-none-badge">None today</span>
        )}
        {count != null && count > 0 && (
          <span className="section-count">{count}</span>
        )}
      </button>
      {open && (
        <div className="section-content">
          {absence && (
            <AbsenceToggle
              active={absence.active}
              onToggle={absence.onToggle}
              subject={absence.subject}
            />
          )}
          <div
            className={`section-body${absence?.active ? " section-body--absent" : ""}`}
          >
            {children}
          </div>
        </div>
      )}
    </section>
  );
}
