import pytest

from src.domain.recipes.queries import (
    get_default_recipe_for_film_simulation,
    get_distinct_film_simulations,
    get_image_counts_for_film_simulation,
    get_recipes_by_film_simulation,
)
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetDefaultRecipeForFilmSimulation:
    def test_returns_none_when_no_recipes_exist(self):
        result = get_default_recipe_for_film_simulation(film_simulation="Provia")
        assert result is None

    def test_returns_the_only_recipe_when_one_exists(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        result = get_default_recipe_for_film_simulation(film_simulation="Provia")
        assert result.pk == recipe.pk

    def test_returns_recipe_with_most_images(self):
        low = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        high = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        ImageFactory.create_batch(1, fujifilm_recipe=low)
        ImageFactory.create_batch(5, fujifilm_recipe=high)

        result = get_default_recipe_for_film_simulation(film_simulation="Provia")

        assert result.pk == high.pk

    def test_breaks_tie_by_lowest_pk(self):
        r1 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        r2 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        # Both have zero images — r1 has lower pk so should win
        assert r1.pk < r2.pk

        result = get_default_recipe_for_film_simulation(film_simulation="Provia")

        assert result.pk == r1.pk

    def test_ignores_recipes_from_other_film_sims(self):
        FujifilmRecipeFactory(film_simulation="Velvia")
        provia = FujifilmRecipeFactory(film_simulation="Provia")

        result = get_default_recipe_for_film_simulation(film_simulation="Provia")

        assert result.pk == provia.pk


@pytest.mark.django_db
class TestGetRecipesByFilmSimulation:
    def test_returns_recipes_matching_film_simulation(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert [r.pk for r in result] == [provia.pk]

    def test_returns_multiple_matching_recipes(self):
        p1 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        p2 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")

        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert {r.pk for r in result} == {p1.pk, p2.pk}

    def test_returns_empty_list_when_no_match(self):
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert result == []

    def test_returns_empty_list_when_no_recipes_exist(self):
        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert result == []

    def test_does_not_return_recipes_with_different_film_simulation(self):
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="Classic Chrome")

        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert result == []

    def test_returns_plain_list(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_recipes_by_film_simulation(film_simulation="Provia")

        assert isinstance(result, list)


@pytest.mark.django_db
class TestGetDistinctFilmSimulations:
    def test_returns_all_distinct_values(self):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")

        result = get_distinct_film_simulations()

        assert result == ["Provia", "Velvia"]

    def test_returns_empty_list_when_no_recipes_exist(self):
        result = get_distinct_film_simulations()

        assert result == []

    def test_result_is_sorted_alphabetically(self):
        FujifilmRecipeFactory(film_simulation="Velvia")
        FujifilmRecipeFactory(film_simulation="ACROS")
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_distinct_film_simulations()

        assert result == sorted(result)

    def test_returns_plain_list(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_distinct_film_simulations()

        assert isinstance(result, list)


@pytest.mark.django_db
class TestGetImageCountsForFilmSimulation:
    def test_returns_image_count_for_matching_recipe(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert result[recipe.pk] == 3

    def test_excludes_images_belonging_to_different_film_sim(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")
        ImageFactory(fujifilm_recipe=provia)
        ImageFactory(fujifilm_recipe=velvia)

        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert provia.pk in result
        assert velvia.pk not in result

    def test_returns_empty_dict_when_no_images(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert result == {}

    def test_returns_empty_dict_when_film_sim_has_no_recipes(self):
        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert result == {}

    def test_counts_multiple_recipes_independently(self):
        r1 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        r2 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        ImageFactory.create_batch(2, fujifilm_recipe=r1)
        ImageFactory.create_batch(5, fujifilm_recipe=r2)

        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert result[r1.pk] == 2
        assert result[r2.pk] == 5

    def test_returns_plain_dict(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)

        result = get_image_counts_for_film_simulation(film_simulation="Provia")

        assert isinstance(result, dict)
