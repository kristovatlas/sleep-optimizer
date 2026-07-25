/** TypeScript interfaces mirroring backend schemas for daily log entries. */

import type {
  CaffeineSource,
  HabitType,
  NSDRType,
  PreBedRitualType,
  SexualActivityType,
  StimulatingActivityType,
} from "./enums";

// --- Entry Create types (for PUT body) ---

export interface CaffeineEntryCreate {
  time: string | null;
  amount_mg: number;
  source: CaffeineSource;
}

export interface MealEntryCreate {
  time: string | null;
  is_last_meal: boolean | null;
  notes: string | null;
}

export interface SupplementEntryCreate {
  time: string | null;
  name: string;
  // Unit-agnostic dose VALUE in the linked product's unit (legacy column name;
  // mg for free-text rows). Dose IS the state: > 0 = took it, 0 = explicit
  // "none today", and a row absent from the list = not recorded (NULL).
  dose_mg: number | null;
  // Link to a SupplementProduct library row; null = legacy free-text entry
  // (kept editable but never analyzed).
  product_id: number | null;
}

export interface HabitEntryCreate {
  habit_type: HabitType;
  time: string | null;
  value: string | null;
  duration_minutes: number | null;
  notes: string | null;
}

export interface StimulatingActivityCreate {
  end_time: string | null;
  activity_type: StimulatingActivityType;
  duration_minutes: number | null;
}

export interface SexualActivityCreate {
  time: string | null;
  activity_type: SexualActivityType;
}

export interface PreBedRitualCreate {
  time: string | null;
  ritual_type: PreBedRitualType;
  duration_minutes: number | null;
}

export interface NapEntryCreate {
  start_time: string | null;
  end_time: string | null;
  duration_minutes: number | null;
}

export interface SunlightEntryCreate {
  start_time: string | null;
  duration_minutes: number | null;
  estimated_lux: number | null;
  notes: string | null;
}

export interface RedLightEntryCreate {
  panel_id: number | null;
  start_time: string | null;
  duration_minutes: number | null;
  distance_inches: number | null;
}

export interface NSDREntryCreate {
  time: string | null;
  duration_minutes: number | null;
  nsdr_type: NSDRType;
}

// --- Entry Out types (from GET response) ---

export interface CaffeineEntryOut extends CaffeineEntryCreate {
  id: number;
  date: string;
}

export interface MealEntryOut extends MealEntryCreate {
  id: number;
  date: string;
}

export interface SupplementEntryOut extends SupplementEntryCreate {
  id: number;
  date: string;
}

export interface HabitEntryOut extends HabitEntryCreate {
  id: number;
  date: string;
}

export interface StimulatingActivityOut extends StimulatingActivityCreate {
  id: number;
  date: string;
}

export interface SexualActivityOut extends SexualActivityCreate {
  id: number;
  date: string;
}

export interface PreBedRitualOut extends PreBedRitualCreate {
  id: number;
  date: string;
}

export interface NapEntryOut extends NapEntryCreate {
  id: number;
  date: string;
}

export interface SunlightEntryOut extends SunlightEntryCreate {
  id: number;
  date: string;
}

export interface RedLightEntryOut extends RedLightEntryCreate {
  id: number;
  date: string;
  dose_joules_cm2: number | null;
}

export interface NSDREntryOut extends NSDREntryCreate {
  id: number;
  date: string;
}

// --- Composite daily log ---

export interface DailyLogCreate {
  is_sick: boolean | null;
  notes: string | null;
  caffeine_entries: CaffeineEntryCreate[];
  meal_entries: MealEntryCreate[];
  supplement_entries: SupplementEntryCreate[];
  habit_entries: HabitEntryCreate[];
  stimulating_activity_entries: StimulatingActivityCreate[];
  sexual_activity_entry: SexualActivityCreate | null;
  pre_bed_ritual_entries: PreBedRitualCreate[];
  nap_entries: NapEntryCreate[];
  sunlight_entries: SunlightEntryCreate[];
  red_light_entries: RedLightEntryCreate[];
  nsdr_entries: NSDREntryCreate[];
  // Explicit "did not do X" section keys (e.g. "caffeine", "sauna",
  // "supplement:<product_id>"). ROUND-TRIP CONTRACT: the PUT has REPLACE
  // semantics — every save must carry the day's absences (loaded keys plus
  // local changes) or it silently wipes them on the backend. See ADR 003.
  section_absences: string[];
}

export interface DailyLogOut {
  date: string;
  copied_from_date: string | null;
  is_sick: boolean | null;
  notes: string | null;
  caffeine_entries: CaffeineEntryOut[];
  meal_entries: MealEntryOut[];
  supplement_entries: SupplementEntryOut[];
  habit_entries: HabitEntryOut[];
  stimulating_activity_entries: StimulatingActivityOut[];
  sexual_activity_entry: SexualActivityOut | null;
  pre_bed_ritual_entries: PreBedRitualOut[];
  nap_entries: NapEntryOut[];
  sunlight_entries: SunlightEntryOut[];
  red_light_entries: RedLightEntryOut[];
  nsdr_entries: NSDREntryOut[];
  section_absences: string[];
}

export interface DailyLogResponse {
  data: DailyLogOut;
  warnings: string[];
}

export interface DailyLogSummary {
  date: string;
  copied_from_date: string | null;
  is_sick: boolean | null;
  has_entries: boolean;
}
