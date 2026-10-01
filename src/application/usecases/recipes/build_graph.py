import attrs

from src.data import models
from src.domain.recipes import graph as recipe_graph
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes import similarity as recipe_similarity
from src.domain.settings import queries as settings_queries


def _similarity_weights() -> tuple[float, float]:
    """Read the runtime identity/extras weights (ADR 019 A/B) as one pair."""
    return (
        settings_queries.get_recipe_similarity_identity_weight(),
        settings_queries.get_recipe_similarity_extras_weight(),
    )


@attrs.frozen
class RecipeNetworkResult:
    graph_data: recipe_graph.RecipeTreeData
    film_simulations: tuple[str, ...]
    active_film_simulation: str
    named_only: bool
    recipes_by_usage: tuple[recipe_graph.RecipeTreeNode, ...]


@attrs.frozen
class RecipeNeighbourhoodResult:
    graph_data: recipe_graph.RecipeTreeData
    root_label: str
    min_similarity: float
    named_only: bool
    recipes_by_usage: tuple[recipe_graph.RecipeTreeNode, ...]


def _by_usage(
    nodes: tuple[recipe_graph.RecipeTreeNode, ...],
) -> tuple[recipe_graph.RecipeTreeNode, ...]:
    """
    Order graph nodes for the sidebar list: most-used first, then by label.

    The label tie-break keeps the order stable across requests when several
    recipes share an image count, which is common for unused recipes.
    """
    return tuple(sorted(nodes, key=lambda node: (-node.image_count, node.label)))


def build_recipe_network(
    *,
    film_simulation: str,
    named_only: bool = False,
) -> RecipeNetworkResult:
    """
    Build a spanning tree of recipes for a single film simulation.

    The tree is rooted at the most-used recipe for that film simulation (the one
    with the most images; ties broken by lowest pk). All recipes for the film
    simulation are included regardless of distance from root. The full list of
    distinct film simulations is returned alongside the graph so the caller can
    render a filter control.

    When *named_only* is set, unnamed recipes are dropped before the tree is
    built, so it stays a connected spanning tree over the recipes that remain.
    """
    recipes = recipe_queries.get_recipes_by_film_simulation(film_simulation=film_simulation)
    film_simulations = tuple(recipe_queries.get_film_simulations_with_multiple_recipes())

    if not recipes:
        return RecipeNetworkResult(
            graph_data=recipe_graph.RecipeTreeData(root_id=None, nodes=(), edges=()),
            film_simulations=film_simulations,
            active_film_simulation=film_simulation,
            named_only=named_only,
            recipes_by_usage=(),
        )

    image_counts = recipe_queries.get_image_counts_for_film_simulation(film_simulation=film_simulation)
    default_recipe = recipe_queries.get_default_recipe_for_film_simulation(film_simulation=film_simulation)
    assert default_recipe is not None  # guaranteed: recipes is non-empty

    candidates = recipes
    if named_only:
        candidates = recipe_graph.named_recipes(root=default_recipe, all_recipes=recipes)

    identity_weight, extras_weight = _similarity_weights()
    graph_data = recipe_graph.build_recipe_tree(
        root=default_recipe,
        candidates=candidates,
        image_counts=image_counts,
        identity_weight=identity_weight,
        extras_weight=extras_weight,
    )
    return RecipeNetworkResult(
        graph_data=graph_data,
        film_simulations=film_simulations,
        active_film_simulation=film_simulation,
        named_only=named_only,
        recipes_by_usage=_by_usage(graph_data.nodes),
    )


def build_recipe_neighbourhood(
    *,
    root: models.FujifilmRecipe,
    min_similarity: float,
    named_only: bool = False,
) -> RecipeNeighbourhoodResult:
    """
    Build a spanning tree of the recipes most similar to *root*.

    Candidates are every recipe at least *min_similarity* similar to the root,
    across all film simulations. The same similarity tree used by
    `build_recipe_network` connects them, so a node's ring encodes how alike it
    is to the root on both graph pages.

    When *named_only* is set, unnamed recipes are dropped from the candidates.
    The root is always kept, named or not.
    """
    identity_weight, extras_weight = _similarity_weights()
    candidates = recipe_similarity.recipes_at_least_similar(
        reference=root,
        min_similarity=min_similarity,
        identity_weight=identity_weight,
        extras_weight=extras_weight,
    )
    if named_only:
        candidates = recipe_graph.named_recipes(root=root, all_recipes=candidates)

    # `recipes_at_least_similar` excludes the root, so add it back for the image
    # count (the root always appears in the tree).
    image_counts = recipe_queries.get_image_counts(
        recipe_pks=[root.pk, *(recipe.pk for recipe in candidates)],
    )
    graph_data = recipe_graph.build_recipe_tree(
        root=root,
        candidates=candidates,
        image_counts=image_counts,
        identity_weight=identity_weight,
        extras_weight=extras_weight,
    )
    return RecipeNeighbourhoodResult(
        graph_data=graph_data,
        root_label=root.name or f"#{root.pk}",
        min_similarity=min_similarity,
        named_only=named_only,
        recipes_by_usage=_by_usage(graph_data.nodes),
    )
