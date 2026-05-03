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
    """
    Return the number of recipe fields that differ between *a* and *b*.
    """
    return sum(
        1 for field in _RECIPE_GRAPH_FIELDS
        if getattr(a, field) != getattr(b, field)
    )


@attrs.frozen
class RecipeNode:
    id: int
    label: str
    distance: int
    image_count: int


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
    """
    Build a shortest-path spanning tree rooted at *root*.

    Each node is connected to a parent such that the sum of edge distances along
    the path from root to that node equals hamming_distance(root, node). This means
    traversing any root→node path and summing its edge distances gives the true
    Hamming distance — no artificial inflation from chaining via unrelated nodes.

    Among all valid parents (those satisfying the shortest-path constraint), the one
    that minimises the direct edge distance to the child is chosen, producing the
    most chain-like structure when multiple valid parents exist.

    Nodes are processed in ascending dist(root, node) order so that all candidate
    parents are already in the tree when a node is attached.

    Node `distance` = hamming_distance(root, node).
    Edge `distance` = hamming distance between the two directly connected nodes.
    """
    recipe_by_pk = {r.pk: r for r in all_recipes}

    dist_from_root: dict[int, int] = {
        r.pk: (0 if r.pk == root.pk else hamming_distance(a=root, b=r))
        for r in all_recipes
    }

    in_tree: set[int] = {root.pk}
    parent_of: dict[int, int] = {}
    edge_distances: dict[int, int] = {}

    # Process non-root nodes in ascending dist-from-root order so every valid
    # parent (dist d-k for some k≥1) is already in the tree.
    ordered = sorted(
        (r for r in all_recipes if r.pk != root.pk),
        key=lambda r: dist_from_root[r.pk],
    )

    for recipe in ordered:
        d_to_root = dist_from_root[recipe.pk]
        # Valid parents are in-tree nodes P where dist(root,P) + dist(P,recipe) == dist(root,recipe).
        # Among those, pick the one with the smallest direct edge (dist(P, recipe)).
        best_parent_pk: int | None = None
        best_edge_d = d_to_root + 1  # sentinel — worse than any valid parent
        for pk in in_tree:
            edge_d = hamming_distance(a=recipe, b=recipe_by_pk[pk])
            if dist_from_root[pk] + edge_d == d_to_root and edge_d < best_edge_d:
                best_edge_d = edge_d
                best_parent_pk = pk

        # Fallback: no strictly valid parent (can happen when dist_from_root values
        # don't form an exact chain). Attach to the tree node with minimum edge cost.
        if best_parent_pk is None:
            best_parent_pk = min(
                in_tree, key=lambda pk: hamming_distance(a=recipe, b=recipe_by_pk[pk])
            )
            best_edge_d = hamming_distance(a=recipe, b=recipe_by_pk[best_parent_pk])

        in_tree.add(recipe.pk)
        parent_of[recipe.pk] = best_parent_pk
        edge_distances[recipe.pk] = best_edge_d

    nodes = tuple(
        FilmSimTreeNode(
            id=r.pk,
            label=r.name or f"#{r.pk}",
            distance=dist_from_root[r.pk],
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
    """
    Build a per-film-simulation recipe network.

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
        """
        A node is blocked from distance-d edges if it already has neighbours at
        both d-1 and d-2. Distances 1 and 2 are never blocked (d-2 <= 0 never exists).
        """
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
    image_counts: dict[int, int],
) -> RecipeGraphData:
    """
    Build a recipe graph centred on *root*.

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
            image_count=image_counts.get(r.pk, 0),
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
