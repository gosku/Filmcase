import pytest

from src.domain.recipes.queries import RecipeData, get_filtered_recipes
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetFilteredRecipesReturnType:
    def test_returns_recipe_data_instances(self):
        FujifilmRecipeFactory()

        result = get_filtered_recipes(active_filters={})

        assert all(isinstance(r, RecipeData) for r in result)

    def test_returns_empty_list_when_no_recipes_exist(self):
        result = get_filtered_recipes(active_filters={})

        assert result == []


@pytest.mark.django_db
class TestGetFilteredRecipesFiltering:
    def test_no_filters_returns_all_recipes(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()

        result = get_filtered_recipes(active_filters={})

        ids = [r.id for r in result]
        assert recipe_a.pk in ids
        assert recipe_b.pk in ids

    def test_filters_by_single_field_value(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Classic Chrome")

        result = get_filtered_recipes(active_filters={"film_simulation": ["Provia"]})

        assert [r.id for r in result] == [provia.pk]

    def test_filters_by_multiple_values_for_same_field(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        classic = FujifilmRecipeFactory(film_simulation="Classic Chrome")
        FujifilmRecipeFactory(film_simulation="Velvia")

        result = get_filtered_recipes(
            active_filters={"film_simulation": ["Provia", "Classic Chrome"]}
        )

        ids = {r.id for r in result}
        assert ids == {provia.pk, classic.pk}

    def test_filters_by_multiple_fields(self):
        match = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Off")

        result = get_filtered_recipes(
            active_filters={"film_simulation": ["Provia"], "grain_roughness": ["Off"]}
        )

        assert [r.id for r in result] == [match.pk]

    def test_empty_list_for_a_key_is_ignored(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")

        result = get_filtered_recipes(
            active_filters={"film_simulation": [], "grain_roughness": ["Off"]}
        )

        ids = [r.id for r in result]
        assert recipe.pk in ids

    def test_returns_empty_list_when_no_recipes_match(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_filtered_recipes(active_filters={"film_simulation": ["Velvia"]})

        assert result == []


@pytest.mark.django_db
class TestGetFilteredRecipesOrdering:
    def test_recipe_with_more_images_comes_first(self):
        few = FujifilmRecipeFactory()
        many = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=few)
        ImageFactory(fujifilm_recipe=many)
        ImageFactory(fujifilm_recipe=many)

        result = get_filtered_recipes(active_filters={})

        ids = [r.id for r in result]
        assert ids.index(many.pk) < ids.index(few.pk)

    def test_named_recipe_comes_before_unnamed_when_image_count_is_equal(self):
        unnamed = FujifilmRecipeFactory(name="")
        named = FujifilmRecipeFactory(name="My Recipe")

        result = get_filtered_recipes(active_filters={})

        ids = [r.id for r in result]
        assert ids.index(named.pk) < ids.index(unnamed.pk)

    def test_name_beats_image_count(self):
        named_few = FujifilmRecipeFactory(name="Named")
        unnamed_many = FujifilmRecipeFactory(name="")
        ImageFactory(fujifilm_recipe=unnamed_many)
        ImageFactory(fujifilm_recipe=unnamed_many)

        result = get_filtered_recipes(active_filters={})

        ids = [r.id for r in result]
        assert ids.index(named_few.pk) < ids.index(unnamed_many.pk)

    def test_lower_pk_is_stable_tiebreaker(self):
        first = FujifilmRecipeFactory(name="")
        second = FujifilmRecipeFactory(name="")

        result = get_filtered_recipes(active_filters={})

        ids = [r.id for r in result]
        assert ids.index(first.pk) < ids.index(second.pk)


@pytest.mark.django_db
class TestGetFilteredRecipesDataFields:
    def test_recipe_data_exposes_image_count(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)

        result = get_filtered_recipes(active_filters={})

        recipe_data = next(r for r in result if r.id == recipe.pk)
        assert recipe_data.image_count == 2

    def test_recipe_data_exposes_all_recipe_fields(self):
        recipe = FujifilmRecipeFactory(
            film_simulation="Provia",
            dynamic_range="DR200",
            grain_roughness="Strong",
            white_balance="Daylight",
            white_balance_red=3,
            white_balance_blue=-2,
        )

        result = get_filtered_recipes(active_filters={})

        data = next(r for r in result if r.id == recipe.pk)
        assert data.film_simulation == "Provia"
        assert data.dynamic_range == "DR200"
        assert data.grain_roughness == "Strong"
        assert data.white_balance == "Daylight"
        assert data.white_balance_red == 3
        assert data.white_balance_blue == -2

    def test_recipe_data_image_count_is_zero_when_no_images(self):
        recipe = FujifilmRecipeFactory()

        result = get_filtered_recipes(active_filters={})

        data = next(r for r in result if r.id == recipe.pk)
        assert data.image_count == 0
