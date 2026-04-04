import pytest

from src.application.usecases.recipes.build_graph import RecipeNetworkResult, build_recipe_network
from src.domain.recipes.graph import FilmSimTreeData
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestBuildRecipeNetwork:
    def test_returns_frozen_result(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = build_recipe_network(film_simulation="Provia")

        assert isinstance(result, RecipeNetworkResult)
        assert isinstance(result.graph_data, FilmSimTreeData)

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

    def test_film_simulations_includes_all_distinct_values(self):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = build_recipe_network(film_simulation="Provia")

        assert "Provia" in result.film_simulations
        assert "Velvia" in result.film_simulations

    def test_film_simulations_is_sorted(self):
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="ACROS")
        FujifilmRecipeFactory(film_simulation="Provia")

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
