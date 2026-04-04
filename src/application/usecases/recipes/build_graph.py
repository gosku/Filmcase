import attrs

from src.domain.recipes import graph as recipe_graph
from src.domain.recipes import queries as recipe_queries


@attrs.frozen
class RecipeNetworkResult:
    graph_data: recipe_graph.FilmSimTreeData
    film_simulations: tuple[str, ...]
    active_film_simulation: str


def build_recipe_network(*, film_simulation: str) -> RecipeNetworkResult:
    """Build a spanning tree of recipes for a single film simulation.

    The tree is rooted at the most-used recipe for that film simulation (the one
    with the most images; ties broken by lowest pk). All recipes for the film
    simulation are included regardless of distance from root. The full list of
    distinct film simulations is returned alongside the graph so the caller can
    render a filter control.
    """
    recipes = recipe_queries.get_recipes_by_film_simulation(film_simulation=film_simulation)
    film_simulations = tuple(recipe_queries.get_distinct_film_simulations())

    if not recipes:
        return RecipeNetworkResult(
            graph_data=recipe_graph.FilmSimTreeData(root_id=None, nodes=(), edges=()),
            film_simulations=film_simulations,
            active_film_simulation=film_simulation,
        )

    image_counts = recipe_queries.get_image_counts_for_film_simulation(film_simulation=film_simulation)
    default_recipe = recipe_queries.get_default_recipe_for_film_simulation(film_simulation=film_simulation)
    assert default_recipe is not None  # guaranteed: recipes is non-empty

    graph_data = recipe_graph.build_film_sim_tree(
        root=default_recipe,
        all_recipes=recipes,
        image_counts=image_counts,
    )
    return RecipeNetworkResult(
        graph_data=graph_data,
        film_simulations=film_simulations,
        active_film_simulation=film_simulation,
    )
