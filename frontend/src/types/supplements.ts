/** TypeScript interfaces mirroring backend supplement-library schemas (#161). */

export interface SupplementProduct {
  id: number;
  name: string;
  brand: string | null;
  form: string | null;
  default_dose: number | null;
  unit: string;
  step: number;
  is_sticky: boolean;
}

export interface SupplementProductCreate {
  name: string;
  brand?: string | null;
  form?: string | null;
  default_dose?: number | null;
  unit?: string;
  step?: number;
  is_sticky?: boolean;
}
