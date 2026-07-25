/** Shared between SupplementSection and DailyLogPage (a separate module so
 * SupplementSection.tsx exports only components, per react-refresh). */

import type { SupplementEntryCreate, SupplementProduct } from "../../../types";

/** Prefilled entry row for a library product (default dose, no time). Used
 * by the section's picker path and by DailyLogPage to append the row after
 * an inline product create — that append lives at the page layer, where the
 * viewed date is known and the update can be functional (see the
 * onCreateProduct prop doc in SupplementSection). */
export function rowForProduct(p: SupplementProduct): SupplementEntryCreate {
  return {
    time: null,
    name: p.name,
    dose_mg: p.default_dose ?? null,
    product_id: p.id,
  };
}
