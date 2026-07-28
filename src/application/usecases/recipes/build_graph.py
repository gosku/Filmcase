import attrs

from src.data import models
from src.domain.recipes import graph as recipe_graph
from src.domain.recipes import queries as recipe_queries


@attrs.frozen
class RecipeNetworkResult:
    graph_data: recipe_graph.RecipeTreeData
    film_simulations: tuple[str, ...]
    active_film_simulation: str
    named_only: bool


@attrs.frozen
class RecipeNeighbourhoodResult:
    graph_data: recipe_graph.RecipeTreeData
    root_label: str
    max_distance: int
    named_only: bool


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
        )

    image_counts = recipe_queries.get_image_counts_for_film_simulation(film_simulation=film_simulation)
    default_recipe = recipe_queries.get_default_recipe_for_film_simulation(film_simulation=film_simulation)
    assert default_recipe is not None  # guaranteed: recipes is non-empty

    candidates = recipes
    if named_only:
        candidates = recipe_graph.named_recipes(root=default_recipe, all_recipes=recipes)

    graph_data = recipe_graph.build_recipe_tree(
        root=default_recipe,
        candidates=candidates,
        image_counts=image_counts,
    )
    return RecipeNetworkResult(
        graph_data=graph_data,
        film_simulations=film_simulations,
        active_film_simulation=film_simulation,
        named_only=named_only,
    )


def build_recipe_neighbourhood(
    *,
    root: models.FujifilmRecipe,
    max_distance: int,
    named_only: bool = False,
) -> RecipeNeighbourhoodResult:
    """
    Build a spanning tree of the recipes closest to *root*.

    Candidates are every recipe strictly within *max_distance* of the root, across
    all film simulations. The same shortest-path tree used by
    `build_recipe_network` connects them, so ring distance and summed edge
    distances mean the same thing on both graph pages.

    When *named_only* is set, unnamed recipes are dropped from the candidates.
    The root is always kept, named or not.
    """
    candidates = recipe_graph.recipes_within_distance(
        root=root,
        all_recipes=models.FujifilmRecipe.objects.all(),
        max_distance=max_distance,
    )
    if named_only:
        candidates = recipe_graph.named_recipes(root=root, all_recipes=candidates)

    image_counts = recipe_queries.get_image_counts(recipe_pks=[recipe.pk for recipe in candidates])
    graph_data = recipe_graph.build_recipe_tree(
        root=root,
        candidates=candidates,
        image_counts=image_counts,
    )
    return RecipeNeighbourhoodResult(
        graph_data=graph_data,
        root_label=root.name or f"#{root.pk}",
        max_distance=max_distance,
        named_only=named_only,
    )
