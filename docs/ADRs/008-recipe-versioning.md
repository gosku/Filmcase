# ADR 008 — Recipe versioning via generalised grouping

**Status**: Accepted
**Date**: 2026-05-15

---

## Context

Recipes became editable in PR #38. A recipe's settings fields can now be changed through the UI. However, recipes are linked to images via a `PROTECT` foreign key (`Image.fujifilm_recipe`). Editing a recipe's settings in place would silently rewrite what settings every associated image is recorded as having been shot with — the EXIF source of truth (`FujifilmExif`) remains unchanged, creating an inconsistency between the two records of the same shot.

The only safe "edit" at the data level is to create a new `FujifilmRecipe` row with the tweaked settings and leave existing images pointing at the old row. This works for integrity but loses the relationship between the two recipes — there is no way to surface that one is an evolution of the other.

---

## Problem

How can we allow recipe evolution while:

1. Preserving the integrity of the image → recipe association (images remain linked to the exact settings they were shot with).
2. Expressing that two recipes are related — one is a deliberate tweak of the other.
3. Leaving room for a future `recipe families` concept, where recipes are grouped thematically rather than chronologically.

---

## Options considered

### Option A — Mutable recipes (status quo from PR #38)

Allow `update_settings` to mutate an existing recipe row in place.

**Why we did not choose this option:**

Every image associated with the recipe would silently acquire new settings. The `FujifilmExif` row still carries the original camera EXIF data, so the two representations of the same shot would diverge. The app has no mechanism to detect or recover from this inconsistency.

### Option B — Immutable recipes with a version-specific table

Add a `RecipeVersion` table that chains `FujifilmRecipe` rows into an ordered sequence: each row holds a FK to the previous version.

**Why we did not choose this option:**

It solves versioning but cannot express thematic grouping (families). Adding families later would require a second grouping mechanism, leaving the codebase with two overlapping models that serve similar purposes.

### Option C — Generalised recipe grouping (chosen)

Introduce two models: `RecipeGroup` (a typed container) and `RecipeGroupMember` (a through table). The `group_type` field controls the semantics — `VERSION_LINE` for chronological evolution, `FAMILY` for thematic grouping. Both needs are satisfied by the same underlying structure.

**Why this was chosen:**

A single abstraction covers both the immediate need (versioning) and the planned future need (families) without requiring a second model later. The `group_type` field keeps the two use cases distinct at the data level while sharing all the plumbing. The cost — one extra table and one denormalised field — is low.

---

## Decision

Add `RecipeGroup` and `RecipeGroupMember` to the data layer.

`RecipeGroup` carries a `group_type` (`VERSION_LINE` or `FAMILY`) and an optional `name`. For version lines the name is the stable concept identity shared across all versions; for families it is user-defined. The two names are semantically independent — individual recipe names can drift freely across versions.

`RecipeGroupMember` links a `FujifilmRecipe` to a `RecipeGroup`. It denormalises `group_type` from the group to enable a DB-level partial unique constraint (`unique_version_line_per_recipe`) that prevents a recipe from belonging to more than one version line. `position` records chronological order within a version line and is `null` for family memberships. `added_at` is the domain-layer timestamp of when the recipe joined the group (distinct from the audit `created_at`).

Creating a new version means creating a new `FujifilmRecipe` row — never mutating the old one — and appending it to the version line group at `position = max(current positions) + 1`. `Image.fujifilm_recipe` FK values are never touched.

---

## Diagrams

### Data model

```mermaid
erDiagram
    RecipeGroup {
        int id PK
        string group_type "VERSION_LINE | FAMILY"
        string name "optional"
    }
    RecipeGroupMember {
        int id PK
        int group_id FK
        int recipe_id FK
        string group_type "denormalised from RecipeGroup"
        int position "null for FAMILY memberships"
        datetime added_at
    }
    FujifilmRecipe {
        int id PK
        string film_simulation
        string name
        string other_settings "16 additional camera settings fields"
    }
    Image {
        int id PK
        int fujifilm_recipe_id FK
    }

    RecipeGroup ||--o{ RecipeGroupMember : "has members"
    FujifilmRecipe ||--o{ RecipeGroupMember : "belongs to"
    FujifilmRecipe ||--o{ Image : "shot with (PROTECT)"
```

### Create-version flow

```mermaid
sequenceDiagram
    actor User
    participant View as CreateRecipeVersion view
    participant UC as create_recipe_version usecase
    participant Op as get_or_create_recipe_from_data
    participant VL as add_recipe_to_version_line
    participant DB

    User->>View: GET /recipes/<id>/create-version/
    View->>DB: Load source recipe + version line membership
    DB-->>View: recipe, group_id
    View-->>User: Form pre-populated with source recipe settings

    User->>View: POST (tweaked settings)
    View->>UC: create_recipe_version(data, group_id)
    UC->>Op: get_or_create_recipe_from_data(data, group_id)
    Op->>DB: FujifilmRecipe.get_or_create(settings)
    DB-->>Op: (new_recipe, created=True)
    Op->>VL: add_recipe_to_version_line(new_recipe, group_id)
    VL->>DB: Append RecipeGroupMember at position = max + 1
    Op-->>UC: (new_recipe, created=True)
    UC-->>View: new_recipe
    View-->>User: Redirect to new recipe detail page

    note over DB: Source recipe and its images are untouched.<br/>Only a new FujifilmRecipe row is created.
```

---

## Consequences

- `FujifilmRecipe` rows remain immutable once images are associated with them. "Editing" a recipe always produces a new row.
- The existing `UniqueConstraint` on the 17 recipe settings fields is preserved — a new version must differ in at least one setting.
- A recipe can belong to at most one `VERSION_LINE` group (DB-enforced) and any number of `FAMILY` groups.
- The `group_type` field on `RecipeGroupMember` must be kept in sync with `RecipeGroup.group_type` by the domain layer on every write. This is the tradeoff for getting a DB-level partial unique index without a cross-table constraint.
- `RecipeCard` and all other existing models are unchanged.

---

## Interface layer

### Options considered

**Option 1 — extend the existing `CreateRecipe` view.**
Add a `recipe_id` query parameter to `recipes/create/`. When present, the view pre-populates the form from the source recipe and routes the submission to a `create_recipe_version` use case instead of `create_recipe_manually`. The `CreateRecipe` form class is reused unchanged.

**Option 2 — a dedicated view and use case (chosen).**
Introduce a new URL `recipes/<int:recipe_id>/create-version/`, a new `CreateRecipeVersion` view, and a new `create_recipe_version` use case. The existing `interface_forms.CreateRecipe` form class is reused as the shared form between `CreateRecipe`, `EditRecipe`, and the new view.

### Why Option 2

Option 1 would force every extension point of `CreateRecipe` — `dispatch`, `get_initial`, `form_valid` — to branch on the presence of `recipe_id`. The template would need conditionals for the heading and submit label. The URL would conflate two operations with different preconditions (creating from scratch vs. creating from an existing version line).

Option 2 keeps each view responsible for exactly one operation. The form is the right level of reuse; the view and use case are not. The URL makes intent explicit and each view can be tested in isolation without conditional paths.

### Implementation

| Artifact | Location |
|---|---|
| Use case | `src/application/usecases/recipes/create_recipe_version.py` |
| View | `CreateRecipeVersion` in `src/interfaces/views.py` |
| URL | `recipes/<int:recipe_id>/create-version/` (name: `create-recipe-version`) |
| Template | `src/interfaces/templates/recipes/create_recipe_version.html` |
| Form | `interface_forms.CreateRecipe` (shared with `CreateRecipe` and `EditRecipe`) |

The view uses `setup` to load the source recipe and its version line membership, `dispatch` to return 400 if no membership exists, `get_initial` to pre-populate all form fields from the source recipe, and `form_valid` to delegate to the use case and redirect to the new recipe's detail page.
