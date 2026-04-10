import pytest

from src.domain.recipes.queries import get_recipe_list
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetRecipeListFiltering:
    def test_returns_all_recipes_when_no_filters(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()

        result = get_recipe_list(filters={}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert recipe_a.pk in ids
        assert recipe_b.pk in ids

    def test_filters_by_film_simulation(self):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Classic Chrome")

        result = get_recipe_list(filters={"film_simulation": "Provia"}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids == [provia.pk]

    def test_filters_by_multiple_fields_simultaneously(self):
        match = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Classic Chrome", grain_roughness="Off")

        result = get_recipe_list(
            filters={"film_simulation": "Provia", "grain_roughness": "Off"},
            page_number=1,
            page_size=50,
        )

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids == [match.pk]

    def test_returns_empty_page_when_no_matches(self):
        FujifilmRecipeFactory(film_simulation="Provia")

        result = get_recipe_list(
            filters={"film_simulation": "Velvia"},
            page_number=1,
            page_size=50,
        )

        assert list(result.page_obj.object_list) == []


@pytest.mark.django_db
class TestGetRecipeListOrdering:
    def test_recipe_with_more_images_comes_first(self):
        few = FujifilmRecipeFactory()
        many = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=few)
        ImageFactory(fujifilm_recipe=many)
        ImageFactory(fujifilm_recipe=many)

        result = get_recipe_list(filters={}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids.index(many.pk) < ids.index(few.pk)

    def test_named_recipe_comes_before_unnamed_when_image_count_is_equal(self):
        unnamed = FujifilmRecipeFactory(name="")
        named = FujifilmRecipeFactory(name="My Recipe")

        result = get_recipe_list(filters={}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids.index(named.pk) < ids.index(unnamed.pk)

    def test_image_count_beats_name(self):
        named_few = FujifilmRecipeFactory(name="Named")
        unnamed_many = FujifilmRecipeFactory(name="")
        ImageFactory(fujifilm_recipe=unnamed_many)
        ImageFactory(fujifilm_recipe=unnamed_many)

        result = get_recipe_list(filters={}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids.index(unnamed_many.pk) < ids.index(named_few.pk)

    def test_lower_pk_is_stable_tiebreaker(self):
        first = FujifilmRecipeFactory(name="")
        second = FujifilmRecipeFactory(name="")

        result = get_recipe_list(filters={}, page_number=1, page_size=50)

        ids = [r.pk for r in result.page_obj.object_list]
        assert ids.index(first.pk) < ids.index(second.pk)


@pytest.mark.django_db
class TestGetRecipeListPagination:
    def test_page_size_limits_results_per_page(self):
        FujifilmRecipeFactory.create_batch(5)

        result = get_recipe_list(filters={}, page_number=1, page_size=3)

        assert len(result.page_obj.object_list) == 3

    def test_page_number_selects_correct_page(self):
        recipes = FujifilmRecipeFactory.create_batch(4)

        page1 = get_recipe_list(filters={}, page_number=1, page_size=2)
        page2 = get_recipe_list(filters={}, page_number=2, page_size=2)

        ids_p1 = {r.pk for r in page1.page_obj.object_list}
        ids_p2 = {r.pk for r in page2.page_obj.object_list}
        assert ids_p1.isdisjoint(ids_p2)
        assert ids_p1 | ids_p2 == {r.pk for r in recipes}

    def test_has_next_when_more_pages_exist(self):
        FujifilmRecipeFactory.create_batch(3)

        result = get_recipe_list(filters={}, page_number=1, page_size=2)

        assert result.page_obj.has_next()

    def test_last_page_has_no_next(self):
        FujifilmRecipeFactory.create_batch(3)

        result = get_recipe_list(filters={}, page_number=2, page_size=2)

        assert not result.page_obj.has_next()
