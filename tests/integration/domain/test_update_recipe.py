from __future__ import annotations

from decimal import Decimal

import pytest

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes import operations
from tests.factories import FujifilmRecipeFactory, ImageFactory


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
        name="Updated",
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


@pytest.mark.django_db
class TestUpdateRecipePersistence:
    def test_updates_film_simulation_in_db(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Velvia"

    def test_updates_numeric_fields_in_db(self) -> None:
        recipe = FujifilmRecipeFactory()
        operations.update_recipe(recipe=recipe, data=_make_data(sharpness="+2", high_iso_nr="-1", clarity="+3"))
        recipe.refresh_from_db()
        assert recipe.sharpness == Decimal("2")
        assert recipe.high_iso_nr == Decimal("-1")
        assert recipe.clarity == Decimal("3")

    def test_updates_name_when_data_name_is_non_empty(self) -> None:
        recipe = FujifilmRecipeFactory(name="Old Name")
        operations.update_recipe(recipe=recipe, data=_make_data(name="New Name"))
        recipe.refresh_from_db()
        assert recipe.name == "New Name"

    def test_does_not_overwrite_name_when_data_name_is_empty(self) -> None:
        recipe = FujifilmRecipeFactory(name="Kept Name")
        operations.update_recipe(recipe=recipe, data=_make_data(name=""))
        recipe.refresh_from_db()
        assert recipe.name == "Kept Name"

    def test_recipe_row_count_unchanged_after_update(self) -> None:
        recipe = FujifilmRecipeFactory()
        count_before = models.FujifilmRecipe.objects.count()
        operations.update_recipe(recipe=recipe, data=_make_data())
        assert models.FujifilmRecipe.objects.count() == count_before


@pytest.mark.django_db
class TestUpdateRecipeSettingsConflict:
    def test_raises_settings_conflict_when_new_settings_match_existing_recipe(self) -> None:
        existing, _ = operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(white_balance_red=99)
        with pytest.raises(operations.RecipeSettingsConflictError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.recipe_id == recipe.pk

    def test_recipe_not_saved_when_settings_conflict(self) -> None:
        operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=99)
        with pytest.raises(operations.RecipeSettingsConflictError):
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"


@pytest.mark.django_db
class TestUpdateRecipeGuards:
    def test_raises_recipe_cannot_be_edited_when_settings_change_and_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(name="My Recipe")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.recipe_id == recipe.pk
        assert exc_info.value.image_count == 1
        assert exc_info.value.name == "My Recipe"

    def test_recipe_cannot_be_edited_error_reflects_actual_image_count(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.image_count == 2

    def test_settings_not_updated_when_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError):
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"

    def test_updates_name_when_recipe_has_images_and_settings_unchanged(self) -> None:
        from src.domain.recipes import queries as recipe_queries
        recipe = FujifilmRecipeFactory(name="Old Name")
        ImageFactory(fujifilm_recipe=recipe)
        # Build data that exactly matches the current recipe's settings so settings_changing=False
        current = recipe_queries.recipe_from_db(recipe=recipe)
        import attrs
        data = attrs.evolve(current, name="New Name")
        operations.update_recipe(recipe=recipe, data=data)
        recipe.refresh_from_db()
        assert recipe.name == "New Name"


@pytest.mark.django_db
class TestUpdateRecipeEventPublishing:
    def test_publishes_recipe_updated_event(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory()
        operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["recipe_id"] == recipe.pk

    def test_no_event_when_settings_change_and_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError):
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 0

    def test_publishes_event_when_only_name_changes_with_images(self, captured_logs: list[dict]) -> None:
        from src.domain.recipes import queries as recipe_queries
        import attrs
        recipe = FujifilmRecipeFactory(name="Old Name")
        ImageFactory(fujifilm_recipe=recipe)
        current = recipe_queries.recipe_from_db(recipe=recipe)
        data = attrs.evolve(current, name="New Name")
        operations.update_recipe(recipe=recipe, data=data)
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1


@pytest.mark.django_db
class TestUpdateRecipeSensors:
    def test_attaches_new_sensor_set(self) -> None:
        recipe = FujifilmRecipeFactory(white_balance_red=7001)

        operations.update_recipe(
            recipe=recipe, data=_make_data(white_balance_red=7001, sensors=("X-Trans IV", "GFX"))
        )

        recipe.refresh_from_db()
        assert sorted(s.name for s in recipe.sensors.all()) == ["GFX", "X-Trans IV"]
        assert recipe.sensor_signature == "gfx,x-trans iv"

    def test_replaces_existing_sensor_set(self) -> None:
        recipe = FujifilmRecipeFactory(white_balance_red=7002)
        operations.update_recipe(
            recipe=recipe, data=_make_data(white_balance_red=7002, sensors=("X-Trans IV",))
        )

        operations.update_recipe(
            recipe=recipe, data=_make_data(white_balance_red=7002, sensors=("X-Trans V",))
        )

        recipe.refresh_from_db()
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans V"]
        assert recipe.sensor_signature == "x-trans v"

    def test_sensor_change_allowed_when_images_are_attached(self) -> None:
        # Sensors are catalogue metadata, not identity: a user may add or
        # remove compatible sensors on a recipe that's already been used to
        # develop photos. Build the update payload from the current recipe
        # so only the sensors field differs and the settings-change guard
        # doesn't fire.
        from src.domain.recipes import queries as recipe_queries
        import attrs

        recipe = FujifilmRecipeFactory(white_balance_red=7003)
        ImageFactory(fujifilm_recipe=recipe)
        current = recipe_queries.recipe_from_db(recipe=recipe)
        data = attrs.evolve(current, sensors=("X-Trans IV",))

        operations.update_recipe(recipe=recipe, data=data)

        recipe.refresh_from_db()
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans IV"]
        assert recipe.sensor_signature == "x-trans iv"

    def test_sensor_change_to_a_set_that_matches_existing_recipe_raises_conflict(self) -> None:
        # An existing recipe with same settings + sensors=(X-Trans IV,) means
        # changing this one's sensors to that set would collide on the
        # UniqueConstraint -- this surfaces as RecipeSettingsConflictError.
        operations.get_or_create_recipe_from_data(
            data=_make_data(white_balance_red=7004, sensors=("X-Trans IV",))
        )
        other = FujifilmRecipeFactory(white_balance_red=7004)

        with pytest.raises(operations.RecipeSettingsConflictError):
            operations.update_recipe(
                recipe=other, data=_make_data(white_balance_red=7004, sensors=("X-Trans IV",))
            )

    def test_no_op_when_sensors_unchanged(self) -> None:
        recipe = FujifilmRecipeFactory(white_balance_red=7005)
        operations.update_recipe(
            recipe=recipe, data=_make_data(white_balance_red=7005, sensors=("X-Trans IV",))
        )

        # Re-running with the same sensors must not raise even when images
        # are attached.
        ImageFactory(fujifilm_recipe=recipe)
        operations.update_recipe(
            recipe=recipe, data=_make_data(white_balance_red=7005, sensors=("X-Trans IV",))
        )

        recipe.refresh_from_db()
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans IV"]


@pytest.mark.django_db
class TestUpdateRecipeDescription:
    def test_writes_description(self) -> None:
        recipe = FujifilmRecipeFactory(white_balance_red=7101)

        operations.update_recipe(
            recipe=recipe,
            data=_make_data(white_balance_red=7101, description="Recipe notes."),
        )

        recipe.refresh_from_db()
        assert recipe.description == "Recipe notes."

    def test_description_change_is_metadata_so_always_editable(self) -> None:
        # description-only change must succeed even when images are attached.
        # Build data from current to keep all settings identical -- only the
        # description field differs.
        from src.domain.recipes import queries as recipe_queries
        import attrs

        recipe = FujifilmRecipeFactory(white_balance_red=7102)
        ImageFactory(fujifilm_recipe=recipe)
        current = recipe_queries.recipe_from_db(recipe=recipe)
        data = attrs.evolve(current, description="Added later")

        operations.update_recipe(recipe=recipe, data=data)

        recipe.refresh_from_db()
        assert recipe.description == "Added later"

    def test_does_not_overwrite_description_when_data_description_is_empty(self) -> None:
        from src.domain.recipes import queries as recipe_queries
        import attrs

        recipe = FujifilmRecipeFactory(white_balance_red=7103)
        # First write a description.
        operations.update_recipe(
            recipe=recipe,
            data=_make_data(white_balance_red=7103, description="Keep me"),
        )
        # Then issue an update with an empty description -- should be a no-op
        # for the description field.
        current = recipe_queries.recipe_from_db(recipe=recipe)
        data = attrs.evolve(current, description="")

        operations.update_recipe(recipe=recipe, data=data)

        recipe.refresh_from_db()
        assert recipe.description == "Keep me"
