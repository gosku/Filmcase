import pytest

from src.application.usecases.recipes.build_graph import (
    RecipeNeighbourhoodResult,
    RecipeNetworkResult,
    build_recipe_neighbourhood,
    build_recipe_network,
)
from src.domain.recipes.graph import RecipeTreeData, hamming_distance
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestBuildRecipeNetwork:
    def test_returns_frozen_result(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = build_recipe_network(film_simulation="Provia")

        assert isinstance(result, RecipeNetworkResult)
        assert isinstance(result.graph_data, RecipeTreeData)

    def test_active_film_simulation_matches_argument(self):
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = build_recipe_network(film_simulation="Velvia")

        assert result.active_film_simulation == "Velvia"

    def test_nodes_contain_only_recipes_for_given_film_sim(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = build_recipe_network(film_simulation="Provia")

        node_ids = {n.id for n in result.graph_data.nodes}
        assert provia.pk in node_ids
        assert len(node_ids) == 1

    def test_empty_graph_when_no_recipes_for_film_sim(self):
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = build_recipe_network(film_simulation="Provia")

        assert result.graph_data.nodes == ()
        assert result.graph_data.edges == ()

    def test_film_simulations_includes_sims_with_multiple_recipes(self):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Strong")

        result = build_recipe_network(film_simulation="Provia")

        assert "Provia" in result.film_simulations
        assert "Velvia" in result.film_simulations

    def test_film_simulations_excludes_sims_with_only_one_recipe(self):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = build_recipe_network(film_simulation="Provia")

        assert "Velvia" not in result.film_simulations

    def test_film_simulations_is_sorted(self):
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="ACROS")
        FujifilmRecipeFactory(film_simulation="ACROS", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")

        result = build_recipe_network(film_simulation="Velvia")

        assert list(result.film_simulations) == sorted(result.film_simulations)

    def test_node_image_count_reflects_actual_images(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory.create_batch(4, fujifilm_recipe=recipe)

        result = build_recipe_network(film_simulation="Provia")

        node = next(n for n in result.graph_data.nodes if n.id == recipe.pk)
        assert node.image_count == 4

    def test_image_counts_from_other_film_sims_not_included(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")
        ImageFactory.create_batch(2, fujifilm_recipe=provia)
        ImageFactory.create_batch(10, fujifilm_recipe=velvia)

        result = build_recipe_network(film_simulation="Provia")

        node = next(n for n in result.graph_data.nodes if n.id == provia.pk)
        assert node.image_count == 2

    def test_edges_connect_recipes_within_film_sim(self):
        r1 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        r2 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong", white_balance_red=0, white_balance_blue=0)

        result = build_recipe_network(film_simulation="Provia")

        assert len(result.graph_data.edges) == 1
        edge = result.graph_data.edges[0]
        assert {edge.source, edge.target} == {r1.pk, r2.pk}


def _recipe(film_simulation="Provia", **kwargs):
    """Create a recipe with sequence-driven fields pinned so hamming distances
    depend only on the fields under test."""
    defaults = {
        "film_simulation": film_simulation,
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


@pytest.mark.django_db
class TestBuildRecipeNeighbourhood:
    def test_returns_frozen_result(self):
        root = _recipe()

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert isinstance(result, RecipeNeighbourhoodResult)
        assert isinstance(result.graph_data, RecipeTreeData)

    def test_root_is_the_given_recipe(self):
        root = _recipe()

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert result.graph_data.root_id == root.pk

    def test_root_label_uses_recipe_name(self):
        root = _recipe()
        root.name = "My Provia"

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert result.root_label == "My Provia"

    def test_root_label_falls_back_to_id_prefix(self):
        root = _recipe()
        assert root.name == ""

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert result.root_label == f"#{root.pk}"

    def test_max_distance_is_echoed_back(self):
        root = _recipe()

        result = build_recipe_neighbourhood(root=root, max_distance=5)

        assert result.max_distance == 5

    def test_nearby_recipe_is_included(self):
        root = _recipe(grain_roughness="Off")
        close = _recipe(grain_roughness="Strong")

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert close.pk in {n.id for n in result.graph_data.nodes}

    def test_recipe_beyond_max_distance_is_excluded(self):
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        far = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")
        assert hamming_distance(a=root, b=far) == 3

        result = build_recipe_neighbourhood(root=root, max_distance=3)

        assert far.pk not in {n.id for n in result.graph_data.nodes}

    def test_recipes_from_other_film_simulations_are_included(self):
        # Unlike the film-sim network, the neighbourhood spans film simulations.
        root = _recipe(film_simulation="Provia")
        other_sim = _recipe(film_simulation="Velvia")

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert other_sim.pk in {n.id for n in result.graph_data.nodes}

    def test_node_image_count_reflects_actual_images(self):
        root = _recipe()
        ImageFactory.create_batch(3, fujifilm_recipe=root)

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        node = next(n for n in result.graph_data.nodes if n.id == root.pk)
        assert node.image_count == 3

    def test_solo_root_produces_a_single_node_and_no_edges(self):
        root = _recipe()

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        assert len(result.graph_data.nodes) == 1
        assert result.graph_data.edges == ()

    def test_path_sums_match_distance_from_root(self):
        # The invariant that the per-recipe graph previously broke.
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        a = _recipe(grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")
        b = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Off")

        result = build_recipe_neighbourhood(root=root, max_distance=4)

        parent_of = {e.target: e.source for e in result.graph_data.edges}
        distance_of = {e.target: e.distance for e in result.graph_data.edges}
        node_distance = {n.id: n.distance for n in result.graph_data.nodes}

        for recipe in [a, b]:
            pk = recipe.pk
            total = 0
            while pk in parent_of:
                total += distance_of[pk]
                pk = parent_of[pk]
            assert total == node_distance[recipe.pk]
