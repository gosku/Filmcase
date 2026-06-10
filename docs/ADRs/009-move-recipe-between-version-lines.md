# ADR 009 — Moving a recipe between VERSION_LINE groups

**Status**: Accepted
**Date**: 2026-06-08

---

## Context

ADR 008 introduced `RecipeGroup` and `RecipeGroupMember` to represent version timelines (`VERSION_LINE`) and thematic families (`FAMILY`). At the time, the only write path was appending a newly created recipe to a version line group. There was no way to reassign an existing recipe to a different group after the fact.

This became a practical gap: a recipe created in the wrong version line, or one that needs to be reorganised after a refactor of the timeline, had no migration path short of deleting and re-creating it.

---

## Problem

How do we allow a recipe to be moved from its current `VERSION_LINE` group to a different one, while:

1. Keeping the positions of all remaining members in the source group contiguous (no gaps).
2. Allowing the caller to specify where in the destination group the recipe should land.
3. Not leaving empty groups behind after the move.
4. Doing all of this atomically, with no window of inconsistency visible to concurrent readers.

---

## Decision

Add a single domain operation `move_recipe_to_version_line` in `src/domain/recipes/operations.py`.

The operation derives the source group from the recipe's existing `RecipeGroupMember` row — the caller provides only the destination. This matches the constraint that a recipe belongs to at most one `VERSION_LINE` group (enforced by `unique_version_line_per_recipe`).

### Invariants

- **Source derived internally.** The source group is not a parameter; it is resolved from the recipe's current membership. This keeps the caller's intent minimal: "move this recipe to that group."
- **Destination must exist.** The destination group must be an existing `VERSION_LINE` group. Empty groups cannot exist (see below), so "existing" implies "has at least one member."
- **Position is optional.** If omitted, the recipe is appended at the end (`max(destination positions) + 1`). A 1-indexed position can be supplied to insert at a specific slot.
- **Source group is deleted if it becomes empty.** An empty `RecipeGroup` has no valid state; the group is removed atomically as part of the same transaction.
- **The membership row is updated in place**, not deleted and re-created. This avoids the brief absence window a delete-then-insert would produce.

### Order of operations (within a single `@transaction.atomic` block)

```
1. Resolve source_member, source_group_id, source_position
2. Validate source != destination
3. Validate destination group exists
4. Compute target_position (default: destination_count + 1)
5. Validate target_position in [1, destination_count + 1]
6. Shift destination members at position >= target_position UP by 1
7. Update source_member.group → destination, source_member.position → target_position
8. Shift source members at position > source_position DOWN by 1
9. Delete source group if now empty
10. Publish RECIPE_VERSION_LINE_UPDATED event
```

Steps 6–8 are safe in this order because step 7 moves the row out of the source group before step 8 compacts it, so the compaction filter (`group_id=source_group_id`) never touches the moved row.

---

## Diagrams

### Example 1 — Default position (append to end)

```
BEFORE
  Source: [X:1, Y:2, Z:3]    Destination: [A:1, B:2]

  Call: move_recipe_to_version_line(recipe_id=X, destination_group_id=Dest)

AFTER
  Source: [Y:1, Z:2]          Destination: [A:1, B:2, X:3]
```

### Example 2 — Explicit position (insert in the middle)

```
BEFORE
  Source: [X:1, Y:2, Z:3]    Destination: [A:1, B:2]

  Call: move_recipe_to_version_line(recipe_id=X, destination_group_id=Dest, position=2)

AFTER
  Source: [Y:1, Z:2]          Destination: [A:1, X:2, B:3]
```

### Example 3 — Source becomes empty → group deleted

```
BEFORE
  Source: [X:1]               Destination: [A:1, B:2]

  Call: move_recipe_to_version_line(recipe_id=X, destination_group_id=Dest)

AFTER
  Source: (group deleted)      Destination: [A:1, B:2, X:3]
```

### Example 4 — Position shifting in source after removal

```
Source before:  [X:1, Y:2, Z:3]

X is moved out (was at position 1).
Members with position > 1 shift down by 1.

Source after:   [Y:1, Z:2]
```

### Example 5 — Position shifting in destination before insertion

```
Destination before:  [A:1, B:2]

Insert at position 2 → members at position >= 2 shift up by 1 first.

Destination after:   [A:1, X:2, B:3]
```

### Edge cases

```
Scenario                          | Behaviour
----------------------------------+------------------------------------------
recipe has no VERSION_LINE group  | raises RecipeNotInVersionLineError
destination group does not exist  | raises VersionLineGroupNotFoundError
source == destination             | raises CannotMoveToSameGroupError
position < 1 or > count + 1      | raises InvalidVersionLinePositionError
source has exactly one member     | source group deleted after move
```

---

## Consequences

- `move_recipe_to_version_line` is the single seam for reassigning a recipe's version line membership.
- Empty `VERSION_LINE` groups cannot exist in steady state; any group that loses its last member is deleted atomically.
- The `unique_version_line_per_recipe` constraint continues to hold: the row is updated in place, so the constraint is never violated even transiently.
- The operation publishes a `recipe.version_line.updated` event on every successful move.
- Callers at the application layer see four translated exceptions: `RecipeNotInVersionLineError`, `VersionLineGroupNotFoundError`, `CannotMoveToSameGroupError`, `InvalidVersionLinePositionError`.
