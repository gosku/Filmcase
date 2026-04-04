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


@attrs.frozen
class AllRecipeNode:
    id: int
    label: str
    film_simulation: str
    image_count: int


@attrs.frozen
class AllRecipeEdge:
    source: int
    target: int
    distance: int


@attrs.frozen
class AllRecipeGraphData:
    nodes: tuple[AllRecipeNode, ...]
    edges: tuple[AllRecipeEdge, ...]


@attrs.frozen
class FilmSimTreeNode:
    id: int
    label: str
    distance: int
    image_count: int


@attrs.frozen
class FilmSimTreeData:
    root_id: int | None
    nodes: tuple[FilmSimTreeNode, ...]
    edges: tuple[AllRecipeEdge, ...]


def build_film_sim_tree(
    *,
    root: models.FujifilmRecipe,
    all_recipes: list[models.FujifilmRecipe],
    image_counts: dict[int, int],
) -> FilmSimTreeData:
    """Build a minimum spanning tree from *root* covering every recipe in *all_recipes*.

    Builds a shortest-path spanning tree rooted at *root*. Nodes are attached in
    ascending order of their hamming distance from root (BFS order). For each node,
    it connects to whichever already-in-tree recipe is closest by hamming distance.

    Processing close nodes first means that when a distant node is attached, the
    tree already contains nearby intermediate nodes for it to connect to — keeping
    hop depth proportional to actual hamming distance from root and preventing the
    long chains that a pure Prim's MST can produce.

    Node `distance` = tree hop depth from root (0 for root, 1 for direct children, …).
    Edge `distance` = actual hamming distance between the two connected recipes.
    """
    recipe_by_pk = {r.pk: r for r in all_recipes}

    dist_from_root: dict[int, int] = {
        r.pk: (0 if r.pk == root.pk else hamming_distance(a=root, b=r))
        for r in all_recipes
    }

    # Process non-root recipes in ascending hamming-distance-from-root order
    # so close nodes enter the tree before distant ones.
    ordered = sorted(
        (r for r in all_recipes if r.pk != root.pk),
        key=lambda r: dist_from_root[r.pk],
    )

    # in_tree maps pk → tree hop depth from root
    in_tree: dict[int, int] = {root.pk: 0}
    parent_of: dict[int, int] = {}
    edge_distances: dict[int, int] = {}

    for recipe in ordered:
        best_parent_pk = min(in_tree, key=lambda pk: hamming_distance(a=recipe, b=recipe_by_pk[pk]))
        best_d = hamming_distance(a=recipe, b=recipe_by_pk[best_parent_pk])
        in_tree[recipe.pk] = in_tree[best_parent_pk] + 1
        parent_of[recipe.pk] = best_parent_pk
        edge_distances[recipe.pk] = best_d

    nodes = tuple(
        FilmSimTreeNode(
            id=r.pk,
            label=r.name or f"#{r.pk}",
            distance=in_tree[r.pk],
            image_count=image_counts.get(r.pk, 0),
        )
        for r in all_recipes
    )

    edges = tuple(
        AllRecipeEdge(source=parent_of[pk], target=pk, distance=edge_distances[pk])
        for pk in parent_of
    )

    return FilmSimTreeData(root_id=root.pk, nodes=nodes, edges=edges)


_ALL_RECIPE_GRAPH_MAX_DISTANCE = 9


def build_all_recipe_graph(
    *,
    all_recipes: list[models.FujifilmRecipe],
    image_counts: dict[int, int],
) -> AllRecipeGraphData:
    """Build a per-film-simulation recipe network.

    Recipes are only connected to other recipes sharing the same film simulation,
    producing one island per film sim. Within each island, edges are drawn for pairs
    whose Hamming distance is <= _ALL_RECIPE_GRAPH_MAX_DISTANCE, with the same
    blocking constraint: a distance-d edge is suppressed for a node that already has
    neighbours at both d-1 and d-2 (distances 1 and 2 are never suppressed).
    """
    nodes = tuple(
        AllRecipeNode(
            id=r.pk,
            label=r.name or f"#{r.pk}",
            film_simulation=r.film_simulation,
            image_count=image_counts.get(r.pk, 0),
        )
        for r in all_recipes
    )

    # Group recipes by film simulation so pairs are only computed within each group.
    by_film_sim: dict[str, list[models.FujifilmRecipe]] = {}
    for r in all_recipes:
        by_film_sim.setdefault(r.film_simulation, []).append(r)

    # Pass 1 — collect intra-group pairs within the max distance and record which
    # distances each node has at least one neighbour at.
    pairs: list[tuple[int, int, int]] = []  # (pk_a, pk_b, distance)
    distances_present: dict[int, set[int]] = {r.pk: set() for r in all_recipes}
    for group in by_film_sim.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                d = hamming_distance(a=group[i], b=group[j])
                if d > _ALL_RECIPE_GRAPH_MAX_DISTANCE:
                    continue
                pk_i = group[i].pk
                pk_j = group[j].pk
                pairs.append((pk_i, pk_j, d))
                distances_present[pk_i].add(d)
                distances_present[pk_j].add(d)

    def _blocked(pk: int, d: int) -> bool:
        """A node is blocked from distance-d edges if it already has neighbours at
        both d-1 and d-2. Distances 1 and 2 are never blocked (d-2 <= 0 never exists)."""
        present = distances_present[pk]
        return (d - 1) in present and (d - 2) in present

    # Pass 2 — emit edges where neither endpoint is blocked at that distance.
    edges: list[AllRecipeEdge] = []
    for pk_i, pk_j, d in pairs:
        if not _blocked(pk_i, d) and not _blocked(pk_j, d):
            edges.append(AllRecipeEdge(source=pk_i, target=pk_j, distance=d))

    return AllRecipeGraphData(nodes=nodes, edges=tuple(edges))


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
