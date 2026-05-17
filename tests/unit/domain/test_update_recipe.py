from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes import normalization as recipe_normalization
from src.domain.recipes import operations

_ATOMIC = "src.domain.recipes.operations.transaction.atomic"
_RECIPE_FROM_DB = "src.domain.recipes.operations.recipe_queries.recipe_from_db"


@contextmanager
def _noop_atomic(*args: object, **kwargs: object):
    yield


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    base: dict[str, object] = dict(
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
        color="0",
        name="My Recipe",
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


def _make_normalized(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    """Return a normalized FujifilmRecipeData — suitable as a recipe_from_db return value."""
    return recipe_normalization.normalize_recipe_data(_make_data(**overrides))


def _make_image_qs(count: int = 0) -> MagicMock:
    qs = MagicMock()
    qs.filter.return_value.count.return_value = count
    qs.filter.return_value.exists.return_value = count > 0
    return qs


class TestUpdateRecipeHasImages:
    def test_raises_recipe_cannot_be_edited_when_settings_change_and_recipe_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "My Recipe"
        # current recipe has Velvia; incoming data has Provia → settings are changing
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=2)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
                    operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 1
        assert exc_info.value.image_count == 2
        assert exc_info.value.name == "My Recipe"

    def test_recipe_not_saved_when_settings_change_and_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with pytest.raises(operations.RecipeCannotBeEditedError):
                    operations.update_recipe(recipe=recipe, data=_make_data())
        recipe.update_settings.assert_not_called()

    def test_error_carries_image_count(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = ""
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=5)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
                    operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.image_count == 5


class TestUpdateRecipeNameOnlyChange:
    def test_calls_set_name_when_only_name_changes(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "Old Name"
        # current_data has same settings as incoming, only name differs
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(name="Old Name")):
                operations.update_recipe(recipe=recipe, data=_make_data(name="New Name"))
        recipe.set_name.assert_called_once_with(name="New Name")

    def test_update_settings_not_called_when_only_name_changes(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "Old Name"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(name="Old Name")):
                operations.update_recipe(recipe=recipe, data=_make_data(name="New Name"))
        recipe.update_settings.assert_not_called()

    def test_set_name_not_called_when_name_is_unchanged(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "Same Name"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(name="Same Name")):
                operations.update_recipe(recipe=recipe, data=_make_data(name="Same Name"))
        recipe.set_name.assert_not_called()

    def test_publishes_event_when_only_name_changes_with_images(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 7
        recipe.name = "Old Name"
        recipe.film_simulation = "Provia"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(name="Old Name")):
                operations.update_recipe(recipe=recipe, data=_make_data(name="New Name"))
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1


class TestUpdateRecipeSettingsConflict:
    def test_raises_settings_conflict_when_save_raises_integrity_error(self) -> None:
        from django.db import IntegrityError

        recipe = MagicMock()
        recipe.pk = 5
        recipe.update_settings.side_effect = IntegrityError()
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    with pytest.raises(operations.RecipeSettingsConflictError) as exc_info:
                        operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 5

    def test_no_event_published_when_settings_conflict(self, captured_logs: list[dict]) -> None:
        from django.db import IntegrityError

        recipe = MagicMock()
        recipe.pk = 5
        recipe.update_settings.side_effect = IntegrityError()
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    with pytest.raises(operations.RecipeSettingsConflictError):
                        operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 0


class TestUpdateRecipeSave:
    def test_update_settings_called_when_recipe_has_no_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    operations.update_recipe(recipe=recipe, data=_make_data())
        recipe.update_settings.assert_called_once()

    def test_name_passed_to_update_settings_when_data_has_name(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    operations.update_recipe(recipe=recipe, data=_make_data(name="Updated Name"))
        assert recipe.update_settings.call_args.kwargs["name"] == "Updated Name"

    def test_existing_name_kept_when_data_name_is_empty(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "Original Name"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    operations.update_recipe(recipe=recipe, data=_make_data(name=""))
        assert recipe.update_settings.call_args.kwargs["name"] == "Original Name"


class TestUpdateRecipeEventPublishing:
    def test_publishes_recipe_updated_event(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 7
        recipe.film_simulation = "Provia"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with patch(_ATOMIC, _noop_atomic):
                    operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["recipe_id"] == 7

    def test_no_event_published_when_settings_change_and_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with patch(_RECIPE_FROM_DB, return_value=_make_normalized(film_simulation="Velvia")):
                with pytest.raises(operations.RecipeCannotBeEditedError):
                    operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 0
