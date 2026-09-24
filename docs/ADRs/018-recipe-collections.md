# ADR 018 — Recipe collections via the existing grouping mechanism

**Status**: Accepted
**Date**: 2026-09-25

---

## Context

Recipes can be browsed, filtered and graphed, but there is no way to gather a
set of recipes under a user-chosen name. The motivating need is a future
feature — pushing several recipes to a camera's custom slots (C1–Cn) in one
action — which requires a durable, *ordered* set of recipes. That camera push
is a separate, later task; this decision covers only the concept and its
create/edit UI. The ordering is stored now because the later task consumes it
(recipe 1 → C1, recipe 2 → C2, …).

A recipe collection is therefore a **named, ordered set of recipes**. A recipe
may appear in many collections; within a collection it appears once, at a
definite position.

ADR 008 already introduced `RecipeGroup` (a typed container) and
`RecipeGroupMember` (a through table with `position` and `added_at`) to back
recipe *version lines*, and explicitly anticipated a second `group_type` for
thematic grouping ("families"). Collections are close to that idea, which
raises the question of whether to reuse that mechanism or model collections
separately.

---

## Options considered

### Option A — Dedicated `RecipeCollection` / `RecipeCollectionMember` models

Two new models purpose-built for collections.

**Why we did not choose this option:**

The membership shape is identical to what `RecipeGroupMember` already provides
— a recipe FK, an ordered `position`, an `added_at`, and a unique-recipe-per-
container constraint. Duplicating that structure adds a second, near-identical
grouping mechanism for no behavioural gain, which is exactly the outcome ADR 008
chose the generalised grouping to avoid.

### Option B — Reuse `RecipeGroup` / `RecipeGroupMember` with a new `COLLECTION` type (chosen)

Add `GROUP_TYPE_COLLECTION` alongside `VERSION_LINE` and `FAMILY`. Collections
are `RecipeGroup` rows of that type; their recipes are `RecipeGroupMember` rows
ordered by `position`.

**Why this was chosen:**

The existing structure already carries everything a collection needs. The
`unique_recipe_per_group` constraint gives "a recipe appears once per
collection" for free, and the `unique_version_line_per_recipe` constraint is
scoped to `VERSION_LINE`, so a recipe may belong to any number of collections
without a new rule. The cost is a `group_type = "COLLECTION"` filter on every
collection query and operation — the same discipline version lines already
follow.

---

## Decision

Model collections as `RecipeGroup` rows with `group_type = "COLLECTION"` and
their ordered recipes as `RecipeGroupMember` rows, reusing the ADR 008
mechanism. Specific choices:

- **Name is required and unique, case-insensitively.** Enforced with a
  partial functional constraint,
  `UniqueConstraint(Lower("name"), condition=Q(group_type="COLLECTION"), name="unique_collection_name_ci")`,
  scoped by condition so it does not touch version-line or family groups (whose
  names are blank or non-unique). Valid on both SQLite and Postgres.
- **Order is carried by `position`** (0-based), assigned by the domain
  operations. Intra-collection order integrity is enforced by those operations,
  not a `unique(group, position)` constraint — this keeps reordering (which
  swaps positions) simple, matching how version lines already behave.
- **A single `update_collection` operation** reconciles a collection's name and
  its full ordered membership from the list the edit page submits (add, remove
  and reposition in one call). Granular add/remove/reorder operations are
  deferred until a caller needs them.
- **Collections are a user-facing concept**, distinct from the internal
  version-line and family groups. They have their own list, detail and
  create/edit pages under the Recipes section, reached from a third arm added to
  the Explorer/Graph sidebar switch.

On the list page, a collection's card shows a mosaic of the best-rated images
across its recipes, falling back to a legend of the recipes' film-simulation
logos when none of the recipes has an imported image yet.

---

## Consequences

- Every collection query and operation filters `group_type = "COLLECTION"`; a
  bug that omits the filter would leak version-line/family groups into the
  collections UI. This is the standing cost of the shared mechanism.
- `RecipeGroupMember` and its constraints are unchanged; no new fields.
- A recipe may belong to many collections and to a version line simultaneously;
  deleting a collection removes only the grouping (cascading its members), never
  the `FujifilmRecipe` rows or their images.
- Duplicating a collection is intentionally out of scope for now.
- The generalised grouping introduced in ADR 008 now backs three group types.
  Any future per-type behaviour must continue to branch on `group_type`.
