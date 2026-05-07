# ADR 007 — Normalize recipe data before storage

**Status**: Accepted
**Date**: 2026-05-07

---

## Context

`FujifilmRecipeData` is the single domain dataclass bridging every recipe
representation: EXIF import, QR card import, camera slot reads, manual form
submission, and the DB read path. Its fields are conditionally applicable —
several fields only make sense under specific combinations of other field values
(see *Recipe shape specification* below).

When `validate_recipe_data()` was introduced to enforce these rules at the DB
write boundary, a structural problem emerged: multiple translators that produce
`FujifilmRecipeData` were independently implementing (or omitting) their own
applicability logic. The same rule — "when D-Range Priority is active,
`dynamic_range` must be `None`" — was encoded in six different places:

| Location | Mechanism |
|---|---|
| `validate_recipe_data()` | raises on violation |
| `get_recipe_data_from_qr_recipe()` | manual `if drp_active` / `if is_mono` guards |
| `exif_to_recipe()` | inline conditional expressions |
| `_is_applicable()` in `cards/queries.py` | field-level exclusion from JSON and card display |
| `recipe_to_ptp_values()` in `camera/queries.py` | skips or defaults inapplicable fields |
| `forms.py` `clean()` | nulls out inapplicable fields |

When a rule changed, each site required an independent update — and omissions
were silent. This made the system fragile and hard to audit.

---

## Recipe shape specification

This section is the authoritative source of truth for the valid shape of a
`FujifilmRecipeData`. Any code that produces or validates a `FujifilmRecipeData`
must conform to these rules.

### Always-required string fields

The following fields must always be present (non-empty string):

`film_simulation`, `d_range_priority`, `grain_roughness`, `color_chrome_effect`,
`color_chrome_fx_blue`, `white_balance`, `sharpness`, `high_iso_nr`, `clarity`

### D-Range Priority rules (mutually exclusive groups)

- **DRP active** (`d_range_priority != "Off"`) →
  `dynamic_range` must be `None`,
  `highlight` must be `None`,
  `shadow` must be `None`

- **DRP off** (`d_range_priority == "Off"`) →
  `dynamic_range` must be a non-empty string,
  `highlight` must be present,
  `shadow` must be present

### Grain rules

- `grain_roughness == "Off"` → `grain_size` must be `None`
- `grain_roughness` active → `grain_size` must be a non-empty string

### Film simulation type rules (mutually exclusive groups)

- **Monochromatic sim** (Acros \*, Monochrome \*, Sepia) →
  `color` must be `None`;
  `monochromatic_color_warm_cool` and `monochromatic_color_magenta_green` must be present

- **Colour sim** (all others) →
  `color` must be present;
  `monochromatic_color_warm_cool` and `monochromatic_color_magenta_green` must be `None`

---

## Options considered

### Option A — Subtypes per shape

Introduce `ColorRecipeData`, `MonoRecipeData`, and `DRPActiveRecipeData` as
distinct types, making invalid states unrepresentable at the type level.

**Why not chosen:** Every function signature, translator, and test fixture would
need to handle a union type. The refactor cost is high relative to the size of
the codebase and the frequency of these rule changes.

### Option B — Single `normalize_recipe_data()` function ✓ CHOSEN

Introduce a single `normalize_recipe_data()` function in a new
`src/domain/recipes/normalization.py` module. It accepts a `FujifilmRecipeData`
and returns a copy with all inapplicable fields set to `None`, using
`attrs.evolve()`. Every translator calls it before handing the object to a
downstream consumer. `validate_recipe_data()` stays as the final gate before DB
storage.

**Why chosen:** Zero breaking API change. Applicability logic lives in one place.
All translators call a single function rather than re-implementing the rules.

### Option C — Leave as-is

Accept the duplication and fix sites on a case-by-case basis.

**Why not chosen:** The number of inconsistencies grows as new producers are
added, and omissions are not detected until runtime.

---

## Decision

Introduce `normalize_recipe_data()` as the single canonical implementation of
the applicability rules defined in the *Recipe shape specification* section
above. Wire it into every translator that produces a `FujifilmRecipeData`.

---

## Consequences

### What `normalize_recipe_data()` does

- Sets inapplicable fields to `None` according to the rules in the *Recipe shape
  specification*.
- Returns a new `FujifilmRecipeData` via `attrs.evolve()` — the input is
  unchanged.
- Is idempotent: calling it twice on the same input produces the same result.

### What `normalize_recipe_data()` does NOT do

- It does **not** validate the recipe. It does not check that required fields are
  present, that values are within range, or that the overall shape is correct.
- It does **not** fill in missing required fields. A recipe with `color=None` for
  a colour sim after normalization still has `color=None` — normalization cannot
  supply a value it does not have.

### Normalize and validate are both required on the write path

Every code path that writes a recipe to the database must call **both** steps in
order:

1. `normalize_recipe_data(data)` — null out inapplicable fields.
2. `validate_recipe_data(normalized)` — assert that all required fields are
   present and no inapplicable fields remain.

Calling only `normalize_recipe_data()` is not sufficient for write paths: a
producer may have omitted a required field entirely, and normalization cannot
detect that. Calling only `validate_recipe_data()` is not sufficient either: a
producer that populates all fields unconditionally (e.g., from a camera read that
returns all PTP properties regardless of film sim) will fail validation before
normalization has had a chance to null out the inapplicable extras.

### Live bug fixed as a consequence

`get_recipe_as_json()` was emitting `"dynamic_range": ""` for DRP-active recipes
because `_is_applicable()` had no awareness of DRP state. Adding DRP awareness to
`_is_applicable()` fixes this for both `get_recipe_as_json()` and
`get_recipe_cover_lines()`.
