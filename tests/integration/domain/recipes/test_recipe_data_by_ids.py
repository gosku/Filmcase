import pytest

from src.domain.recipes.queries import recipe_data_by_ids
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestRecipeDataByIds:
    def test_returns_data_keyed_by_id(self):
        first = FujifilmRecipeFactory(name="First", film_simulation="Provia")
        second = FujifilmRecipeFactory(name="Second", film_simulation="Velvia")

        result = recipe_data_by_ids(recipe_ids=[first.pk, second.pk])

        assert set(result) == {first.pk, second.pk}
        assert result[first.pk].name == "First"
        assert result[second.pk].film_simulation == "Velvia"

    def test_absent_ids_are_omitted(self):
        recipe = FujifilmRecipeFactory()

        result = recipe_data_by_ids(recipe_ids=[recipe.pk, 999999])

        assert set(result) == {recipe.pk}

    def test_empty_ids_returns_empty(self):
        assert recipe_data_by_ids(recipe_ids=[]) == {}
