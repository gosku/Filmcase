from unittest.mock import MagicMock

import pytest

from src.domain.images import events
from src.domain.images.operations import RecipeNameValidationError, set_recipe_name


class TestSetRecipeNameValidation:
    @pytest.mark.parametrize("name", [
        "",
        "X" * 26,
        "caf\xe9",
    ])
    def test_invalid_name_raises(self, name):
        recipe = MagicMock()
        with pytest.raises(RecipeNameValidationError):
            set_recipe_name(recipe=recipe, name=name)

    def test_recipe_not_saved_on_invalid_name(self):
        recipe = MagicMock()
        with pytest.raises(RecipeNameValidationError):
            set_recipe_name(recipe=recipe, name="caf\xe9")
        recipe.save.assert_not_called()


class TestSetRecipeNameEventPublishing:
    def test_publishes_recipe_image_updated_event(self, captured_logs):
        recipe = MagicMock()
        recipe.pk = 42
        set_recipe_name(recipe=recipe, name="My Recipe")

        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_IMAGE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["params"]["name"] == "My Recipe"
        assert updated_events[0]["params"]["recipe_id"] == 42
