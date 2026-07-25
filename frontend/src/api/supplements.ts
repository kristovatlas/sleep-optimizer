/** API functions for the supplement library (#161 Lane 3b). */

import { fetchJson } from "./client";
import type { SupplementProduct, SupplementProductCreate } from "../types";

export function listSupplementProducts(): Promise<SupplementProduct[]> {
  return fetchJson<SupplementProduct[]>("/api/supplement-products");
}

export function createSupplementProduct(
  data: SupplementProductCreate,
): Promise<SupplementProduct> {
  return fetchJson<SupplementProduct>("/api/supplement-products", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
