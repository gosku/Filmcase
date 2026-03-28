import pytest

from src.domain.images import events
from src.domain.images.operations import set_recipe_name
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestSetRecipeNamePersistence:
    def test_sets_recipe_name_in_db(self):
        recipe = FujifilmRecipeFactory(name="")
        set_recipe_name(recipe=recipe, name="My Recipe")
        recipe.refresh_from_db()
        assert recipe.name == "My Recipe"

    def test_only_updates_name_field(self):
        recipe = FujifilmRecipeFactory(name="", film_simulation="Provia")
        set_recipe_name(recipe=recipe, name="My Recipe")
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"

    def test_publishes_recipe_image_updated_event(self, captured_logs):
        recipe = FujifilmRecipeFactory(name="")
        set_recipe_name(recipe=recipe, name="My Recipe")

        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_IMAGE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["params"]["name"] == "My Recipe"
        assert updated_events[0]["params"]["recipe_id"] == recipe.pk

    def test_event_params_contain_name_and_recipe_id(self, captured_logs):
        recipe = FujifilmRecipeFactory(name="")
        set_recipe_name(recipe=recipe, name="Velvia Vivid")

        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_IMAGE_UPDATED]
        params = updated_events[0]["params"]
        assert set(params.keys()) >= {"name", "recipe_id"}
