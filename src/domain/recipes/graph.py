from __future__ import annotations

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


def hamming_distance(
    *,
    a: models.FujifilmRecipe,
    b: models.FujifilmRecipe,
) -> int:
    """Return the number of recipe fields that differ between *a* and *b*."""
    return sum(
        1 for field in _RECIPE_GRAPH_FIELDS
        if getattr(a, field) != getattr(b, field)
    )


@attrs.frozen
class RecipeNode:
    id: int
    label: str
    distance: int


@attrs.frozen
class RecipeEdge:
    source: int
    target: int
    distance: int


@attrs.frozen
class RecipeGraphData:
    root_id: int
    nodes: tuple[RecipeNode, ...]
    edges: tuple[RecipeEdge, ...]


def build_recipe_graph(
    *,
    root: models.FujifilmRecipe,
    all_recipes: list[models.FujifilmRecipe],
    max_distance: int,
) -> RecipeGraphData:
    """Build a recipe graph centred on *root*.

    Nodes: all recipes (including root) whose Hamming distance from *root* is
    strictly less than *max_distance*.

    Edges: a spanning tree where each node connects to its nearest neighbour at
    distance - 1, forming chains like root → N2 → N3 rather than always
    connecting every node back to root directly. When an intermediate distance
    layer is empty, the algorithm falls back to the nearest node at any lower
    distance to avoid isolated islands.
    """
    dist_from_root: dict[int, int] = {root.pk: 0}
    for recipe in all_recipes:
        if recipe.pk == root.pk:
            continue
        d = hamming_distance(a=root, b=recipe)
        if d < max_distance:
            dist_from_root[recipe.pk] = d

    visible: dict[int, models.FujifilmRecipe] = {
        r.pk: r for r in all_recipes if r.pk in dist_from_root
    }

    nodes = tuple(
        RecipeNode(
            id=r.pk,
            label=r.name or f"#{r.pk}",
            distance=dist_from_root[r.pk],
        )
        for r in visible.values()
    )

    # Group visible recipes by their distance from root.
    by_distance: dict[int, list[models.FujifilmRecipe]] = {}
    for r in visible.values():
        by_distance.setdefault(dist_from_root[r.pk], []).append(r)

    # For each node at distance d, connect it to the closest node at any lower
    # distance. Prefer d-1 but fall back through d-2, d-3 … to avoid islands
    # when an intermediate distance layer is empty.
    edges: list[RecipeEdge] = []
    for d in sorted(by_distance):
        if d == 0:
            continue
        parents: list[models.FujifilmRecipe] = []
        for pd in range(d - 1, -1, -1):
            parents = by_distance.get(pd, [])
            if parents:
                break
        if not parents:
            continue
        for recipe in by_distance[d]:
            closest = min(parents, key=lambda p: hamming_distance(a=recipe, b=p))
            edges.append(RecipeEdge(
                source=closest.pk,
                target=recipe.pk,
                distance=hamming_distance(a=recipe, b=closest),
            ))

    return RecipeGraphData(
        root_id=root.pk,
        nodes=nodes,
        edges=tuple(edges),
    )
