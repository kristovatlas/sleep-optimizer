import { useMemo, useState } from "react";
import { SectionWrapper } from "./SectionWrapper";
import { blurOnWheel } from "../../../wheelGuard";
import { ApiError } from "../../../types/api";
import type {
  SupplementEntryCreate,
  SupplementProduct,
  SupplementProductCreate,
} from "../../../types";
import "./SupplementSection.css";

/**
 * Supplements per the owner-signed-off v3 design (#161 Lane 3b).
 *
 * NONE-TODAY DATA MODEL (the decision the wave plan left to this lane):
 * dose IS the state — a listed row with dose > 0 = took it; a row with
 * dose 0 = explicit "none today" (rust); a product not listed = not recorded
 * (NULL, excluded from analysis). A 0-dose product-linked entry aggregates to
 * `supplement_dose_<pid>` = 0.0 in Lane 2 (sum of [0.0]), which is exactly
 * what a `supplement:<pid>` absence key would yield — so the UI records
 * per-supplement "none today" ONLY as 0-dose entry rows and NEVER writes
 * `supplement:<pid>` absence keys. One canonical representation, no
 * dual-write drift; keys arriving from other writers still round-trip
 * untouched through the page's section_absences state. "Mark all none today"
 * zeroes every product-linked row (sticky products guarantee daily-routine
 * products are listed); legacy free-text rows are left untouched — a 0 on an
 * unlinked row carries no analysis meaning.
 *
 * A 0-dose row also never carries a time: Lane 2's timing predictor
 * (supplement_hbb_<pid>) samples the time of EVERY product entry regardless
 * of dose, so a 0-dose row with a time would fabricate a timing sample for a
 * product that was not taken. Every path that lands a dose on 0 (typed 0,
 * − nudge, "Mark all none today") clears the row's time, and a none-today
 * row offers no "+ time" chip (a time saved alongside dose 0 by an older
 * client still displays and can be cleared). Re-typing a positive dose
 * leaves the time cleared for the user to re-set.
 *
 * When the library fetch failed (products === null), product-linked rows
 * render degraded: stored name as read-only text, unit "—", ± disabled —
 * editing against guessed unit/step defaults must not persist mismatched
 * values. The typed dose stays editable (it is unit-agnostic on the entry).
 */

interface SupplementSectionProps {
  entries: SupplementEntryCreate[];
  onChange: (entries: SupplementEntryCreate[]) => void;
  /** Library products; null = not loaded (fetch failed). */
  products: SupplementProduct[] | null;
  onCreateProduct: (
    data: SupplementProductCreate,
  ) => Promise<SupplementProduct>;
  /** Pulls yesterday's supplement rows into today's unsaved state (#110);
   * resolves the number of entries pulled (0 = nothing logged yesterday). */
  onCopyYesterday: () => Promise<number>;
}

const UNITS = ["mg", "mcg", "IU", "g"];

function nowTimeStr(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:00`;
}

/** Nudge a dose by ±step without accumulating float noise. */
function nudged(dose: number | null, step: number, dir: 1 | -1): number {
  const next = Math.max(0, (dose ?? 0) + dir * step);
  return Math.round(next * 1000) / 1000;
}

/** Set a row's dose; a dose landing on 0 drops the time so a "none today"
 * row can never feed the Lane-2 timing predictor a phantom sample. */
function withDose(
  entry: SupplementEntryCreate,
  dose: number | null,
): SupplementEntryCreate {
  return { ...entry, dose_mg: dose, time: dose === 0 ? null : entry.time };
}

function rowForProduct(p: SupplementProduct): SupplementEntryCreate {
  return {
    time: null,
    name: p.name,
    dose_mg: p.default_dose ?? null,
    product_id: p.id,
  };
}

export function SupplementSection({
  entries,
  onChange,
  products,
  onCreateProduct,
  onCopyYesterday,
}: SupplementSectionProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    brand: "",
    form: "",
    default_dose: "",
    unit: "mg",
    step: "",
    is_sticky: false,
  });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [copyMsg, setCopyMsg] = useState<string | null>(null);

  const byId = useMemo(
    () => new Map((products ?? []).map((p) => [p.id, p])),
    [products],
  );

  const removeEntry = (index: number) =>
    onChange(entries.filter((_, i) => i !== index));
  const updateEntry = (index: number, updated: SupplementEntryCreate) =>
    onChange(entries.map((e, i) => (i === index ? updated : e)));

  const addProductRow = (p: SupplementProduct) => {
    onChange([...entries, rowForProduct(p)]);
    setPickerOpen(false);
    setFilter("");
    setShowCreate(false);
  };

  const handleCopyYesterday = async () => {
    setCopyMsg(null);
    try {
      const n = await onCopyYesterday();
      setCopyMsg(
        n > 0
          ? `Copied ${n} supplement${n === 1 ? "" : "s"} from yesterday`
          : "No supplements logged yesterday",
      );
    } catch {
      setCopyMsg("Couldn't load yesterday's log");
    }
  };

  const handleCreate = async () => {
    const name = draft.name.trim();
    if (!name) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await onCreateProduct({
        name,
        brand: draft.brand.trim() || null,
        form: draft.form.trim() || null,
        default_dose:
          draft.default_dose === "" ? null : Number(draft.default_dose),
        unit: draft.unit,
        ...(draft.step !== "" && Number(draft.step) > 0
          ? { step: Number(draft.step) }
          : {}),
        is_sticky: draft.is_sticky,
      });
      setDraft({
        name: "",
        brand: "",
        form: "",
        default_dose: "",
        unit: "mg",
        step: "",
        is_sticky: false,
      });
      addProductRow(created);
    } catch (e) {
      setCreateError(
        e instanceof ApiError && typeof e.detail === "string" && e.detail
          ? e.detail
          : "Couldn't create the product",
      );
    } finally {
      setCreating(false);
    }
  };

  const filtered = (products ?? []).filter((p) =>
    [p.name, p.brand ?? "", p.form ?? ""]
      .join(" ")
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );

  const renderRow = (entry: SupplementEntryCreate, i: number) => {
    const product =
      entry.product_id != null ? byId.get(entry.product_id) : undefined;
    // Library fetch failed → the product's real name/unit/step are unknown.
    // Render the row degraded (read-only name, "—" unit, ± disabled) rather
    // than let edits against guessed defaults persist mismatched values.
    const degraded = entry.product_id != null && products === null;
    const name = product?.name ?? entry.name;
    const unit = degraded ? "—" : (product?.unit ?? "mg");
    const step = product?.step ?? 0.5;
    const meta = product
      ? [product.brand, product.form].filter(Boolean).join(" · ")
      : "";
    const isNone = entry.dose_mg === 0;

    return (
      <div key={i} className={`supp-row${isNone ? " supp-row--none" : ""}`}>
        <div className="supp-row-info">
          {product != null || degraded ? (
            <span className="supp-row-name">{name}</span>
          ) : (
            <input
              className="supp-row-name-input"
              aria-label={`Supplement ${i + 1} name`}
              value={entry.name}
              onChange={(e) =>
                updateEntry(i, { ...entry, name: e.target.value })
              }
            />
          )}
          {meta && <span className="supp-row-meta">{meta}</span>}
          {isNone && <span className="supp-row-none-text">none today</span>}
        </div>

        <div className="supp-row-controls">
          <div className="supp-dose">
            <button
              type="button"
              className="supp-dose-nudge"
              aria-label={`Decrease ${name} dose`}
              disabled={degraded}
              onClick={() =>
                updateEntry(i, withDose(entry, nudged(entry.dose_mg, step, -1)))
              }
            >
              −
            </button>
            <input
              type="number"
              inputMode="decimal"
              className="supp-dose-input"
              aria-label={`${name} dose (${unit})`}
              min={0}
              step={step}
              value={entry.dose_mg ?? ""}
              onWheel={blurOnWheel}
              onChange={(e) => {
                const v = e.target.value === "" ? null : Number(e.target.value);
                // A typed negative is a typo — ignore it rather than clamp
                // to 0, which would fabricate a recorded "none today" skip.
                if (v != null && v < 0) return;
                updateEntry(
                  i,
                  withDose(entry, v == null || Number.isNaN(v) ? null : v),
                );
              }}
            />
            <button
              type="button"
              className="supp-dose-nudge"
              aria-label={`Increase ${name} dose`}
              disabled={degraded}
              onClick={() =>
                updateEntry(i, withDose(entry, nudged(entry.dose_mg, step, 1)))
              }
            >
              +
            </button>
            <span className="supp-unit">{unit}</span>
          </div>

          {entry.time ? (
            <span className="supp-time">
              <input
                type="time"
                aria-label={`${name} time`}
                value={entry.time.slice(0, 5)}
                onChange={(e) =>
                  updateEntry(i, {
                    ...entry,
                    time: e.target.value ? `${e.target.value}:00` : null,
                  })
                }
              />
              <button
                type="button"
                className="supp-chip"
                aria-label={`Clear ${name} time`}
                onClick={() => updateEntry(i, { ...entry, time: null })}
              >
                ×
              </button>
            </span>
          ) : isNone ? null : ( // no "+ time" on a none-today row — see header
            <button
              type="button"
              className="supp-chip"
              aria-label={`Set ${name} time`}
              onClick={() => updateEntry(i, { ...entry, time: nowTimeStr() })}
            >
              + time
            </button>
          )}

          <button
            type="button"
            className="supp-remove"
            aria-label={`Remove ${name}`}
            onClick={() => removeEntry(i)}
          >
            ×
          </button>
        </div>
      </div>
    );
  };

  return (
    <SectionWrapper
      title="Supplements"
      count={entries.length}
      storageKey="supplements"
    >
      <div className="supp-actions">
        <button
          type="button"
          className="supp-chip"
          aria-label="Copy yesterday's supplements"
          onClick={() => void handleCopyYesterday()}
        >
          ⟲ Copy yesterday
        </button>
        {entries.some((e) => e.product_id != null && e.dose_mg !== 0) && (
          <button
            type="button"
            className="supp-chip"
            onClick={() =>
              // Product-linked rows only: 0 on a legacy free-text row has no
              // analysis meaning. Times drop with the dose (see withDose).
              onChange(
                entries.map((e) =>
                  e.product_id == null ? e : { ...e, dose_mg: 0, time: null },
                ),
              )
            }
          >
            Mark all none today
          </button>
        )}
      </div>
      {copyMsg && (
        <p className="supp-msg" role="status">
          {copyMsg}
        </p>
      )}

      {entries.map(renderRow)}

      <button
        type="button"
        className="supp-add-btn"
        aria-expanded={pickerOpen}
        onClick={() => setPickerOpen((o) => !o)}
      >
        + Add a supplement
      </button>

      {pickerOpen && (
        <div className="supp-picker">
          <input
            aria-label="Search supplement library"
            placeholder="Type to filter your library..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {products === null ? (
            <p className="supp-msg">Couldn't load your supplement library.</p>
          ) : filtered.length > 0 ? (
            <ul className="supp-picker-list">
              {filtered.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => addProductRow(p)}>
                    <span className="supp-row-name">{p.name}</span>
                    <span className="supp-row-meta">
                      {[
                        p.brand,
                        p.form,
                        p.default_dose != null
                          ? `${p.default_dose} ${p.unit}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="supp-msg">No matching products in your library.</p>
          )}

          <button
            type="button"
            className="supp-chip"
            aria-expanded={showCreate}
            onClick={() => setShowCreate((s) => !s)}
          >
            + New product
          </button>

          {showCreate && (
            <div className="supp-create">
              <input
                aria-label="New product name"
                placeholder="Name (required)"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
              <input
                aria-label="New product brand"
                placeholder="Brand"
                value={draft.brand}
                onChange={(e) => setDraft({ ...draft, brand: e.target.value })}
              />
              <input
                aria-label="New product form"
                placeholder="Form (capsule, sublingual...)"
                value={draft.form}
                onChange={(e) => setDraft({ ...draft, form: e.target.value })}
              />
              <div className="supp-create-row">
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  aria-label="New product default dose"
                  placeholder="Default dose"
                  value={draft.default_dose}
                  onWheel={blurOnWheel}
                  onChange={(e) =>
                    setDraft({ ...draft, default_dose: e.target.value })
                  }
                />
                <select
                  aria-label="New product unit"
                  value={draft.unit}
                  onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
                >
                  {UNITS.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  aria-label="New product dose step"
                  placeholder="Step (0.5)"
                  value={draft.step}
                  onWheel={blurOnWheel}
                  onChange={(e) => setDraft({ ...draft, step: e.target.value })}
                />
              </div>
              <label className="supp-create-sticky">
                <input
                  type="checkbox"
                  checked={draft.is_sticky}
                  onChange={(e) =>
                    setDraft({ ...draft, is_sticky: e.target.checked })
                  }
                />
                Every day — auto-add to new logs at the default dose
              </label>
              <button
                type="button"
                disabled={creating || draft.name.trim() === ""}
                onClick={() => void handleCreate()}
              >
                {creating ? "Adding..." : "Add to library"}
              </button>
              {createError && (
                <p className="supp-msg supp-msg--error" role="alert">
                  {createError}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </SectionWrapper>
  );
}
