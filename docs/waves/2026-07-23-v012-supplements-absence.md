# v0.1.2 stacked chain — explicit absence + supplement analysis

Owner-directed 2026-07-23. Build-all-at-once, merged as a **stacked chain**
(each branch off the previous, reviewed separately, merged in order) — the
lanes are dependent, so this is not a parallel wave. Decisions settled with
the owner: full scope in one push; per-supplement absence (not section-level);
pull the supplement input-speed work in (#110, #160) since we're unlocking
supplement usefulness and logging must stay fast enough to sustain the data.

Base `dev`, release `main`. Gate live (4-leg battery per PR, required
`review-gate` check). Worktrees under `.claude/worktrees/`.

## Why a chain, not a wave
Lane 2 needs Lane 1's absence semantics; Lane 3 needs Lane 1's schema/API;
Lane 4's coverage list needs Lanes 1–2's predictor set. Shared files
(`stats_engine.py`, `schemas.py`, `DailyLogPage.tsx`) recur across lanes —
legal in a stack (sequential), illegal in a wave (parallel).

## Escalation / data posture
- Schema is **purely additive** (new absence records; existing `daily_logs`
  untouched; a blank day still means "not recorded"/unknown). No
  "beyond additive-nullable" migration → no separate data escalation.
- **ADR 003 amendment** (the third data state) is the reviewable
  data-semantics decision; owner directed it 2026-07-23. Ships in Lane 1.
- Lane 3 is a **new user-facing flow** → UX mockup to the owner for sign-off
  before building.

## Lane 1 — #159 absence core (feat/159-absence-core)
The third data state: *did it* (value) / *explicitly did not* (recorded 0/
False) / *not recorded* (NULL, excluded). Unlocks the 8 binary habits, which
are currently uncorrelatable (all-1.0-or-NULL → zero variance → always
skipped).
- **Schema:** additive `section_absences` table `(id, date FK→daily_logs,
  section_key str)`. `section_key` is a section id (e.g. `caffeine`,
  `alcohol`, `nsdr`) or a namespaced supplement key (`supplement:melatonin`,
  Lane 2 uses that form). Existing logs: no rows = unchanged semantics.
- **Aggregation** (`_aggregate_daily_log`): a section marked absent maps its
  column(s) to the explicit zero — binary → `0.0`, continuous → `0`
  (`total_caffeine_mg=0`, `nap_total_minutes=0`, etc.; clock/"last-hour"
  columns stay NULL — there is no time when it didn't happen). A blank
  section stays NULL.
- **ADR 003 amendment** documenting the three states + why absence ≠ missing.
- Touch-set: `backend/models.py`, `backend/migrations|alembic/<new>`,
  `backend/services/stats_engine.py` (`_aggregate_daily_log`),
  `backend/schemas.py`, `docs/adr/003-*.md`, `backend/tests/test_stats_engine.py`,
  this plan file.

## Lane 2 — per-product supplement predictors (feat/161-supplement-analysis, off Lane 1) — BACKEND, DONE
Supplements were logged (`SupplementEntry` name+dose) but never analyzed. Lane
2 makes each **library product** analyzable, per the owner's locked model
(issue #161 comments 2026-07-23): granularity is **product-level** (brand +
form + dose distinct; no form rollups), dose is **per-day state** (not fixed on
the library entry), and each product yields **two** predictors — dose and
timing-before-sleep. Backend only; the write-API, Daily Log UI, and library
management are Lane 3.
- **Library model** (`SupplementProduct`, additive table): `id, name, brand?,
  form?, default_dose?, unit(default "mg" — mg/mcg/IU/g), step(0.5),
  is_sticky`. `default_dose` is prefill-only; the analyzed dose is the per-day
  value on `SupplementEntry`.
- **Linkage:** `SupplementEntry.product_id` (nullable FK → `supplement_products`).
  Purely additive — existing free-text rows keep `product_id` NULL + their
  `name`/`dose_mg` and are never analyzed. **`dose_mg` is reused as the
  unit-agnostic dose VALUE** (legacy column name kept to avoid touching
  existing data; the unit lives on the product).
- **Migration 005** (chained off 004): additive `create_table` +
  batch-mode `add_column` (SQLite can't ALTER-ADD an FK; batch + PRAGMA
  foreign_keys OFF/ON per `alembic/env.py`). `test_migrations` gets a 005
  parity + upgrade/downgrade round-trip test.
- **Aggregation** (`_aggregate_supplements` in `_aggregate_daily_log`;
  hbb conversion in `prepare_analysis_dataframe`): per product observed with
  entries → `supplement_dose_<pid>` (summed per-day dose in the product's unit;
  `supplement:<pid>` absence or none-today → 0.0; blank → NULL) and
  `supplement_hbb_<pid>` = **hours before bedtime** =
  `bedtime_hour − evening_hour(latest entry time)` (same evening-clock
  normalization as caffeine; multiple same-day entries → latest time + summed
  dose; absence/0-dose day → timing stays NULL, like caffeine's last-hour).
  The `supplement:<pid>` key is wired into `_apply_section_absences` (Lane 1
  left `supplement:*` a no-op).
- **Dynamic predictor discovery:** `compute_correlations` predictor list =
  `[c for c in PREDICTOR_COLUMNS if c in df] + [c for c in df.columns if
  c.startswith("supplement_")]`; the existing min_days/variance/NaN gates skip
  rarely-logged or zero-variance products unchanged. Labels + effect increments
  for the dynamic columns are built from the observed products in
  `prepare_analysis_dataframe` and attached via `df.attrs`
  (`"<Name> (dose)"` / `"<Name> — timing before bed"`); dose gets contrast +
  a `1 <unit>` slope, timing an `hour earlier` slope.
- Touch-set: `backend/models.py`, `alembic/versions/005_*`,
  `backend/services/stats_engine.py`, `backend/services/report_service.py`
  (prefer resolved `predictor_label`), `backend/tests/test_stats_engine.py`,
  `backend/tests/test_migrations.py`, this plan file.

## Lane 3 — Daily Log write-path + UX + input speed (backend + frontend, off Lane 2)
**UX mockup → owner sign-off before build.**

**BLOCKING write-path requirements (Codex P1/P2 on Lane 1, validated real —
these MUST land atomically with the absence write-API so dev never has a
state where absences can be created but a save destroys them):**
- Expose `section_absences` in `DailyLogCreate` / `DailyLogOut` (Pydantic).
- `save_daily_log` uses delete-the-log-and-recreate (`daily_log_service.py:95`)
  with `cascade="all, delete-orphan"` → it currently WIPES absences on every
  save. The write-API PR must recreate/replace absences from the payload in
  `_create_sub_entries` (same lifecycle as other sub-entries), not leave them
  orphan-deleted. Regression test: create log + absence → save (editing an
  unrelated field) → absence survives.
- `copy_day` (`daily_log_service.py:118`) iterates `ENTRY_TYPE_MAP`, which
  omits absences → copy drops them. Add absences to the copy. Regression test.
- **Exports (Codex P2):** JSON export serializes `DailyLogOut` (add the field)
  and the CSV archive must emit `section_absences.csv`; import/restore must
  round-trip them, or an export silently converts every explicit negative back
  to "unknown" and changes correlations. Round-trip test. (If export lives in
  its own module, this facet may split into its own PR in the chain — but it is
  NOT optional and is tracked here.)

**Write-path landmine now also covers supplement products/absences:** the
Lane-2 model added `supplement:<pid>` absences and product-linked entries. The
same delete-and-recreate save (`daily_log_service.py`) that wipes
`section_absences` will wipe supplement `section_absences` too, and `copy_day`
must copy product-linked supplement entries + their `supplement:<pid>`
absences (dose + timing intact). Exports/import must round-trip
`supplement_products` (the library) AND the per-entry `product_id`, or an
export silently un-links every product and drops the per-product predictors.

**UX (per the owner-signed-off v3 mock, #161):**
- Generic **"None today"** affordance per log section, and per-supplement
  **dose-is-state**: a listed supplement is `dose > 0` (took) or `0 mg` (none
  today, rust) — no separate ✓/✗ icon; × removes the row (→ NULL/not recorded).
- **Typeable dose input** + `±` steppers at the product's `step` (decimals,
  e.g. 0.5 mg melatonin); per-product **unit** (mg/mcg/IU/g) shown.
- **Per-supplement TIME** exposed in the row (feeds the Lane-2 timing predictor).
- **#110:** "Copy yesterday's supplements + doses" + common-dose prefill.
- **#160 / #161:** supplement **library** management — create/edit
  `SupplementProduct` (name + brand + form + default_dose + unit + step +
  sticky) inline + in settings; "Add from library" autocomplete; **sticky**
  products auto-appear at default dose; seed a common list; onboarding seed
  step. Product-level, NOT fuzzy name-canonicalize.
- New API + Pydantic for `SupplementProduct` CRUD and product-linked
  `SupplementEntry` on `DailyLogCreate`/`DailyLogOut`.
- Touch-set: `backend/schemas.py`, `backend/services/daily_log_service.py`,
  new `supplement_product` router/service, `backend/services/export*`,
  `frontend/src/components/DailyLog/*`, onboarding + settings surfaces, new
  components, `api/`, `types/`, tests.

## Lane 4 — #158 coverage / countdown (backend + frontend, off Lane 3)
- Backend: per-predictor coverage in the analysis response — co-logged non-
  sick day count, and exclusion reason (`too_few_days` N/14 · `no_variance` ·
  `needs_on_off_days` for binary/absence-gated).
- Frontend: list the not-yet-unlocked correlations with countdowns / prompts.
- Touch-set: `backend/services/stats_engine.py`, `backend/routers/analysis.py`,
  `backend/schemas.py`, `frontend/src/components/Analysis/*`, tests.

## Issues
#159 (absence, priority — Lane 1, MERGED), #161 (per-product supplement
analysis — Lane 2, backend done here), #158 (coverage — Lane 4), #110 + #160
(supplement input + library — Lane 3).
