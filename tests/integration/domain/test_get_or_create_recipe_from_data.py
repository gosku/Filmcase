import pytest

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes.operations import get_or_create_recipe_from_data
from src.domain.recipes.validation import InvalidFujifilmRecipeData


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    base = dict(
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
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


@pytest.mark.django_db
class TestGetOrCreateRecipeFromData:
    def test_creates_recipe_and_returns_created_true(self) -> None:
        recipe, created = get_or_create_recipe_from_data(data=_make_data(name="First"))

        assert recipe.pk is not None
        assert created is True

    def test_returns_existing_recipe_and_created_false_on_second_call(self) -> None:
        first, _ = get_or_create_recipe_from_data(data=_make_data(name="First"))
        second, created = get_or_create_recipe_from_data(data=_make_data(name="First"))

        assert second.pk == first.pk
        assert created is False
        assert models.FujifilmRecipe.objects.count() == 1

    def test_publishes_created_event_on_first_call(self, captured_logs) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data())

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert len(created_events) == 1
        assert created_events[0]["recipe_id"] == recipe.pk

    def test_publishes_deduplicated_event_on_subsequent_call(self, captured_logs) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data())
        captured_logs.clear()
        get_or_create_recipe_from_data(data=_make_data())

        assert not [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        dedup_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_DEDUPLICATED]
        assert len(dedup_events) == 1
        assert dedup_events[0]["recipe_id"] == recipe.pk

    # ── Name is settings-lookup-only, never written back on get path ────────

    def test_same_settings_different_name_deduplicates_to_same_recipe(self) -> None:
        first, _ = get_or_create_recipe_from_data(data=_make_data(name="Alpha"))

        second, created = get_or_create_recipe_from_data(data=_make_data(name="Beta"))

        assert second.pk == first.pk
        assert created is False

    def test_name_from_first_create_is_preserved_on_get(self) -> None:
        get_or_create_recipe_from_data(data=_make_data(name="Original"))

        recipe, _ = get_or_create_recipe_from_data(data=_make_data(name="Ignored"))

        recipe.refresh_from_db()
        assert recipe.name == "Original"

    def test_different_settings_produce_separate_recipes(self) -> None:
        _, created_a = get_or_create_recipe_from_data(data=_make_data(white_balance_red=1))
        _, created_b = get_or_create_recipe_from_data(data=_make_data(white_balance_red=2))

        assert created_a is True
        assert created_b is True
        assert models.FujifilmRecipe.objects.count() == 2

    # ── Normalization ─────────────────────────────────────────────────────────

    def test_normalizes_inapplicable_mono_fields_for_colour_sim(self) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data(
            monochromatic_color_warm_cool="3",
            monochromatic_color_magenta_green="-2",
        ))
        assert recipe.monochromatic_color_warm_cool is None
        assert recipe.monochromatic_color_magenta_green is None

    def test_normalizes_drp_fields_when_d_range_priority_is_active(self) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data(
            d_range_priority="Auto",
            dynamic_range="DR100",
            highlight="0",
            shadow="0",
        ))
        assert recipe.highlight is None
        assert recipe.shadow is None
        assert recipe.dynamic_range == ""

    def test_deduplicates_unnormalised_data_against_existing_clean_recipe(self) -> None:
        first, _ = get_or_create_recipe_from_data(data=_make_data())
        second, created = get_or_create_recipe_from_data(data=_make_data(
            monochromatic_color_warm_cool="3",
            monochromatic_color_magenta_green="-2",
        ))
        assert second.pk == first.pk
        assert created is False

    def test_raises_invalid_recipe_data_before_touching_db(self) -> None:
        # Mono sim with no monochromatic colour fields — normalization preserves None
        # for missing required fields and cannot recover them, so validation still raises.
        invalid_data = _make_data(film_simulation="Acros STD")
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            get_or_create_recipe_from_data(data=invalid_data)
        assert exc_info.value.field == "monochromatic_color_warm_cool"
        assert models.FujifilmRecipe.objects.count() == 0


@pytest.mark.django_db
class TestGetOrCreateRecipeFromDataVersionLine:

    def test_creates_version_line_membership_when_recipe_is_new(self) -> None:
        recipe, created = get_or_create_recipe_from_data(data=_make_data())

        assert created is True
        assert models.RecipeGroupMember.objects.filter(
            recipe=recipe,
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
        ).count() == 1

    def test_new_recipe_is_at_position_1_in_its_own_group(self) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data())

        member = models.RecipeGroupMember.objects.get(recipe=recipe)
        assert member.position == 1

    def test_does_not_create_additional_membership_when_recipe_is_deduplicated(self) -> None:
        recipe, _ = get_or_create_recipe_from_data(data=_make_data())
        get_or_create_recipe_from_data(data=_make_data())

        assert models.RecipeGroupMember.objects.filter(recipe=recipe).count() == 1

    def test_appends_to_existing_version_line_when_group_id_given(self) -> None:
        original, _ = get_or_create_recipe_from_data(data=_make_data(white_balance_red=1))
        original_member = models.RecipeGroupMember.objects.get(recipe=original)

        new_version, _ = get_or_create_recipe_from_data(
            data=_make_data(white_balance_red=2),
            group_id=original_member.group_id,
        )

        new_member = models.RecipeGroupMember.objects.get(recipe=new_version)
        assert new_member.group_id == original_member.group_id
        assert new_member.position == 2

    def test_does_not_raise_when_invalid_group_id_given_on_get_path(self) -> None:
        get_or_create_recipe_from_data(data=_make_data())

        recipe, created = get_or_create_recipe_from_data(data=_make_data(), group_id=99999)

        assert created is False
