from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes import operations

_ATOMIC = "src.domain.recipes.operations.transaction.atomic"


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


def _make_recipe_qs(recipe: object = None) -> MagicMock:
    qs = MagicMock()
    qs.get.return_value = recipe
    return qs


def _make_image_qs(count: int = 0) -> MagicMock:
    qs = MagicMock()
    qs.filter.return_value.count.return_value = count
    qs.filter.return_value.exists.return_value = count > 0
    return qs


class TestUpdateRecipeHasImages:
    def test_raises_recipe_cannot_be_edited_when_recipe_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "My Recipe"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=2)):
            with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
                operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 1
        assert exc_info.value.image_count == 2
        assert exc_info.value.name == "My Recipe"

    def test_recipe_not_saved_when_it_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with pytest.raises(operations.RecipeCannotBeEditedError):
                operations.update_recipe(recipe=recipe, data=_make_data())
        recipe.update_settings.assert_not_called()

    def test_error_carries_image_count(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = ""
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=5)):
            with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
                operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.image_count == 5


class TestUpdateRecipeSettingsConflict:
    def test_raises_settings_conflict_when_save_raises_integrity_error(self) -> None:
        from django.db import IntegrityError

        recipe = MagicMock()
        recipe.pk = 5
        recipe.update_settings.side_effect = IntegrityError()
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_ATOMIC, _noop_atomic):
                with pytest.raises(operations.RecipeSettingsConflictError) as exc_info:
                    operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 5

    def test_no_event_published_when_settings_conflict(self, captured_logs: list[dict]) -> None:
        from django.db import IntegrityError
        from src.domain.images import events

        recipe = MagicMock()
        recipe.pk = 5
        recipe.update_settings.side_effect = IntegrityError()
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
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
            with patch(_ATOMIC, _noop_atomic):
                operations.update_recipe(recipe=recipe, data=_make_data())
        recipe.update_settings.assert_called_once()

    def test_name_passed_to_update_settings_when_data_has_name(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_ATOMIC, _noop_atomic):
                operations.update_recipe(recipe=recipe, data=_make_data(name="Updated Name"))
        assert recipe.update_settings.call_args.kwargs["name"] == "Updated Name"

    def test_existing_name_kept_when_data_name_is_empty(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "Original Name"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_ATOMIC, _noop_atomic):
                operations.update_recipe(recipe=recipe, data=_make_data(name=""))
        assert recipe.update_settings.call_args.kwargs["name"] == "Original Name"


class TestUpdateRecipeEventPublishing:
    def test_publishes_recipe_updated_event(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 7
        recipe.film_simulation = "Provia"
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)):
            with patch(_ATOMIC, _noop_atomic):
                operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["recipe_id"] == 7

    def test_no_event_published_when_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)):
            with pytest.raises(operations.RecipeCannotBeEditedError):
                operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 0
