from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import attrs

from src.data import models

# Recipe fields compared when computing Hamming distance between two recipes.
# Each field counts as one unit of distance when its value differs.
_RECIPE_GRAPH_FIELDS: tuple[str, ...] = (
    "film_simulation",
    "dynamic_range",
    "d_range_priority",
    "grain_roughness",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "white_balance_red",
    "white_balance_blue",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
)

# Two recipes differing in every compared field are this far apart. Used as a
# sentinel that any real distance beats.
_MAX_HAMMING_DISTANCE = len(_RECIPE_GRAPH_FIELDS)


def hamming_distance(
    *,
    a: models.FujifilmRecipe,
    b: models.FujifilmRecipe,
) -> int:
    """
    Return the number of recipe fields that differ between *a* and *b*.
    """
    return sum(
        1 for field in _RECIPE_GRAPH_FIELDS
        if getattr(a, field) != getattr(b, field)
    )


@attrs.frozen
class RecipeTreeNode:
    id: int
    label: str
    distance: int
    image_count: int
    # False when the recipe has no name and `label` is the "#<pk>" fallback.
    is_named: bool


@attrs.frozen
class RecipeTreeEdge:
    source: int
    target: int
    distance: int
    # True when this edge satisfies the shortest-path constraint, meaning the
    # edge distances from the root down to `target` sum to the target's own
    # distance from root. False for fallback attachments, where they do not.
    is_exact: bool


@attrs.frozen
class RecipeTreeData:
    root_id: int | None
    nodes: tuple[RecipeTreeNode, ...]
    edges: tuple[RecipeTreeEdge, ...]


def recipes_within_distance(
    *,
    root: models.FujifilmRecipe,
    all_recipes: Iterable[models.FujifilmRecipe],
    max_distance: int,
) -> list[models.FujifilmRecipe]:
    """
    Return *root* plus every recipe whose Hamming distance from it is strictly
    less than *max_distance*.

    The root is always included, even when *max_distance* is zero, so the result
    is never empty and always usable as a candidate set for `build_recipe_tree`.
    """
    within = [root]
    within.extend(
        recipe for recipe in all_recipes
        if recipe.pk != root.pk and hamming_distance(a=root, b=recipe) < max_distance
    )
    return within


def named_recipes(
    *,
    root: models.FujifilmRecipe,
    all_recipes: Iterable[models.FujifilmRecipe],
) -> list[models.FujifilmRecipe]:
    """
    Return *root* plus every recipe that has a name.

    The root is kept even when it is unnamed. It anchors the tree, and the
    most-used recipe for a film simulation is often unnamed, so dropping it
    would leave the graph rootless. Keeping it also means toggling this filter
    never changes which recipe the others are compared against.
    """
    kept = [root]
    kept.extend(
        recipe for recipe in all_recipes
        if recipe.pk != root.pk and recipe.name
    )
    return kept


def build_recipe_tree(
    *,
    root: models.FujifilmRecipe,
    candidates: Sequence[models.FujifilmRecipe],
    image_counts: Mapping[int, int],
) -> RecipeTreeData:
    """
    Build a shortest-path spanning tree over *candidates*, rooted at *root*.

    The caller decides which recipes are candidates: all recipes sharing a film
    simulation, or everything within a maximum distance of the root. Every
    candidate ends up in the tree, so the graph never contains isolated islands.
    *root* is included whether or not it appears in *candidates*.

    Each node is connected to a parent satisfying the shortest-path constraint
    `dist(root, P) + dist(P, node) == dist(root, node)`, so summing the edge
    distances along any root to node path gives the node's true Hamming distance
    from the root. Among all valid parents the one minimising the direct edge
    distance is chosen, producing the most chain-like structure available.

    When no parent satisfies the constraint the node is attached to the nearest
    node already in the tree and its edge is marked `is_exact=False`. Path sums
    through such an edge exceed the true distance, so callers should present
    them differently.

    Nodes are processed in ascending distance-from-root order, which guarantees
    every candidate parent is already in the tree when a node is attached.

    Node `distance` is `hamming_distance(root, node)`, not hop depth.
    Edge `distance` is the Hamming distance between the two connected recipes.
    """
    recipes = list(candidates)
    if all(recipe.pk != root.pk for recipe in recipes):
        recipes.insert(0, root)

    recipe_by_pk = {recipe.pk: recipe for recipe in recipes}

    dist_from_root: dict[int, int] = {
        recipe.pk: (0 if recipe.pk == root.pk else hamming_distance(a=root, b=recipe))
        for recipe in recipes
    }

    # Kept as an insertion-ordered list rather than a set so that ties between
    # equally good parents resolve the same way on every request, making the
    # rendered graph stable.
    tree_pks: list[int] = [root.pk]
    parent_of: dict[int, int] = {}
    edge_distance_of: dict[int, int] = {}
    is_exact_of: dict[int, bool] = {}

    ordered = sorted(
        (recipe for recipe in recipes if recipe.pk != root.pk),
        key=lambda recipe: dist_from_root[recipe.pk],
    )

    for recipe in ordered:
        distance_to_root = dist_from_root[recipe.pk]

        # One pass finds both the best constrained parent and the nearest in-tree
        # node overall, so the fallback needs no further distance computations.
        best_parent_pk: int | None = None
        best_edge_distance = distance_to_root + 1  # worse than any valid parent
        nearest_pk = root.pk
        nearest_edge_distance = _MAX_HAMMING_DISTANCE + 1

        for pk in tree_pks:
            edge_distance = hamming_distance(a=recipe, b=recipe_by_pk[pk])
            if edge_distance < nearest_edge_distance:
                nearest_edge_distance = edge_distance
                nearest_pk = pk
            satisfies_constraint = dist_from_root[pk] + edge_distance == distance_to_root
            if satisfies_constraint and edge_distance < best_edge_distance:
                best_edge_distance = edge_distance
                best_parent_pk = pk

        if best_parent_pk is not None:
            parent_of[recipe.pk] = best_parent_pk
            edge_distance_of[recipe.pk] = best_edge_distance
            is_exact_of[recipe.pk] = True
        else:
            parent_of[recipe.pk] = nearest_pk
            edge_distance_of[recipe.pk] = nearest_edge_distance
            is_exact_of[recipe.pk] = False
        tree_pks.append(recipe.pk)

    nodes = tuple(
        RecipeTreeNode(
            id=recipe.pk,
            label=recipe.name or f"#{recipe.pk}",
            distance=dist_from_root[recipe.pk],
            image_count=image_counts.get(recipe.pk, 0),
            is_named=bool(recipe.name),
        )
        for recipe in recipes
    )

    edges = tuple(
        RecipeTreeEdge(
            source=parent_pk,
            target=pk,
            distance=edge_distance_of[pk],
            is_exact=is_exact_of[pk],
        )
        for pk, parent_pk in parent_of.items()
    )

    return RecipeTreeData(root_id=root.pk, nodes=nodes, edges=edges)
