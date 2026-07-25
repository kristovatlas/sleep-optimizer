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
 * zeroes every listed row (sticky products guarantee daily-routine products
 * are listed).
 */

interface SupplementSectionProps {
  entries: SupplementEntryCreate[];
  onChange: (entries: SupplementEntryCreate[]) => void;
  /** Library products; null = not loaded (fetch failed). */
  products: SupplementProduct[] | null;
  onCreateProduct: (
    data: SupplementProductCreate,
  ) => Promise<SupplementProduct>;
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
    const name = product?.name ?? entry.name;
    const unit = product?.unit ?? "mg";
    const step = product?.step ?? 0.5;
    const meta = product
      ? [product.brand, product.form].filter(Boolean).join(" · ")
      : "";
    const isNone = entry.dose_mg === 0;

    return (
      <div key={i} className={`supp-row${isNone ? " supp-row--none" : ""}`}>
        <div className="supp-row-info">
          {product ? (
            <span className="supp-row-name">{product.name}</span>
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
              onClick={() =>
                updateEntry(i, {
                  ...entry,
                  dose_mg: nudged(entry.dose_mg, step, -1),
                })
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
                updateEntry(i, {
                  ...entry,
                  dose_mg: v == null || Number.isNaN(v) ? null : Math.max(0, v),
                });
              }}
            />
            <button
              type="button"
              className="supp-dose-nudge"
              aria-label={`Increase ${name} dose`}
              onClick={() =>
                updateEntry(i, {
                  ...entry,
                  dose_mg: nudged(entry.dose_mg, step, 1),
                })
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
          ) : (
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
      {entries.some((e) => e.dose_mg !== 0) && (
        <div className="supp-actions">
          <button
            type="button"
            className="supp-chip"
            onClick={() => onChange(entries.map((e) => ({ ...e, dose_mg: 0 })))}
          >
            Mark all none today
          </button>
        </div>
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
