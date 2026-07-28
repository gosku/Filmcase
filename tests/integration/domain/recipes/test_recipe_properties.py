import pytest

from src.domain.recipes.queries import (
    PROPERTY_GROUPS,
    RECIPE_FIELDS,
    PropertyGroup,
    PropertyRow,
    RecipePropertyView,
    get_recipe_properties,
    get_recipe_property_comparison,
)
from tests.factories import FujifilmRecipeFactory


def _recipe(**kwargs):
    defaults = {
        "film_simulation": "Provia",
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


def _rows(view):
    return [row for group in view.groups for row in group.rows]


def _row(view, key):
    return next(row for row in _rows(view) if row.key == key)


def _group_labels(view):
    return [group.label for group in view.groups]


# ---------------------------------------------------------------------------
# Group definition
# ---------------------------------------------------------------------------

class TestPropertyGroupsCoverEveryField:
    def test_every_recipe_field_appears_in_a_group(self):
        # Without this, adding a field to RECIPE_FIELDS would silently omit it
        # from the comparison panel.
        grouped = {field for _, fields in PROPERTY_GROUPS for field in fields}
        assert grouped == set(RECIPE_FIELDS)

    def test_no_field_appears_in_two_groups(self):
        grouped = [field for _, fields in PROPERTY_GROUPS for field in fields]
        assert len(grouped) == len(set(grouped))

    def test_group_labels_are_unique(self):
        labels = [label for label, _ in PROPERTY_GROUPS]
        assert len(labels) == len(set(labels))


# ---------------------------------------------------------------------------
# get_recipe_properties (single recipe)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGetRecipeProperties:
    def test_returns_frozen_value_objects(self):
        view = get_recipe_properties(recipe=_recipe())

        assert isinstance(view, RecipePropertyView)
        assert isinstance(view.groups[0], PropertyGroup)
        assert isinstance(view.groups[0].rows[0], PropertyRow)

    def test_rows_carry_the_field_key_for_icon_mapping(self):
        view = get_recipe_properties(recipe=_recipe())

        assert _row(view, "film_simulation").key == "film_simulation"

    def test_rows_use_the_display_label(self):
        view = get_recipe_properties(recipe=_recipe())

        assert _row(view, "d_range_priority").label == "D-Range Priority"

    def test_reference_value_is_populated(self):
        view = get_recipe_properties(recipe=_recipe(film_simulation="Velvia"))

        assert _row(view, "film_simulation").reference_value == "Velvia"

    def test_nothing_is_marked_changed(self):
        view = get_recipe_properties(recipe=_recipe())

        assert view.changed_count == 0
        assert all(not row.changed for row in _rows(view))

    def test_compared_value_is_absent(self):
        view = get_recipe_properties(recipe=_recipe())

        assert all(row.compared_value is None for row in _rows(view))

    def test_decimal_fields_are_signed(self):
        view = get_recipe_properties(recipe=_recipe(shadow=2))

        assert _row(view, "shadow").reference_value.startswith("+")

    def test_groups_follow_the_declared_order(self):
        view = get_recipe_properties(recipe=_recipe())

        declared = [label for label, _ in PROPERTY_GROUPS]
        assert _group_labels(view) == [g for g in declared if g in _group_labels(view)]


@pytest.mark.django_db
class TestMonochromeGroupOnlyAppearsWhenRelevant:
    def test_colour_recipe_has_no_monochrome_group(self):
        view = get_recipe_properties(recipe=_recipe(
            monochromatic_color_warm_cool=None,
            monochromatic_color_magenta_green=None,
        ))

        assert "Monochrome" not in _group_labels(view)

    def test_monochrome_recipe_gets_the_group(self):
        view = get_recipe_properties(recipe=_recipe(
            film_simulation="Acros",
            monochromatic_color_warm_cool=2,
            monochromatic_color_magenta_green=-1,
        ))

        assert "Monochrome" in _group_labels(view)

    def test_monochrome_group_is_last(self):
        view = get_recipe_properties(recipe=_recipe(
            film_simulation="Acros",
            monochromatic_color_warm_cool=2,
            monochromatic_color_magenta_green=-1,
        ))

        assert _group_labels(view)[-1] == "Monochrome"

    def test_a_field_with_no_value_on_either_side_is_dropped(self):
        view = get_recipe_properties(recipe=_recipe(monochromatic_color_warm_cool=None))

        assert "monochromatic_color_warm_cool" not in {row.key for row in _rows(view)}


# ---------------------------------------------------------------------------
# get_recipe_property_comparison (two recipes)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGetRecipePropertyComparison:
    def test_unchanged_rows_are_kept(self):
        # The panel shows the whole recipe, not only the differences.
        reference = _recipe(grain_roughness="Off")
        compared = _recipe(grain_roughness="Strong")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        assert not _row(view, "film_simulation").changed
        assert _row(view, "film_simulation") in _rows(view)

    def test_changed_row_is_flagged(self):
        reference = _recipe(grain_roughness="Off")
        compared = _recipe(grain_roughness="Strong")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        assert _row(view, "grain_roughness").changed is True

    def test_changed_row_carries_both_values(self):
        reference = _recipe(grain_roughness="Off")
        compared = _recipe(grain_roughness="Strong")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        row = _row(view, "grain_roughness")
        assert row.reference_value == "Off"
        assert row.compared_value == "Strong"

    def test_unchanged_row_repeats_the_same_value(self):
        reference = _recipe(film_simulation="Provia")
        compared = _recipe(film_simulation="Provia", grain_roughness="Strong")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        row = _row(view, "film_simulation")
        assert row.reference_value == row.compared_value == "Provia"

    def test_changed_count_matches_the_flagged_rows(self):
        reference = _recipe(grain_roughness="Off", grain_size="Off")
        compared = _recipe(grain_roughness="Strong", grain_size="Large")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        assert view.changed_count == 2
        assert view.changed_count == sum(1 for row in _rows(view) if row.changed)

    def test_identical_recipes_report_no_changes(self):
        reference = _recipe()

        view = get_recipe_property_comparison(reference=reference, compared=reference)

        assert view.changed_count == 0

    def test_group_changed_count_is_per_group(self):
        reference = _recipe(grain_roughness="Off", grain_size="Off")
        compared = _recipe(grain_roughness="Strong", grain_size="Large")

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        grain = next(g for g in view.groups if g.label == "Grain")
        basic = next(g for g in view.groups if g.label == "Basic")
        assert grain.changed_count == 2
        assert basic.changed_count == 0

    def test_a_value_missing_on_one_side_is_still_compared(self):
        reference = _recipe(monochromatic_color_warm_cool=2)
        compared = _recipe(monochromatic_color_warm_cool=None)

        view = get_recipe_property_comparison(reference=reference, compared=compared)

        row = _row(view, "monochromatic_color_warm_cool")
        assert row.changed is True
        assert row.reference_value == "+2"
        assert row.compared_value  # a placeholder, not an empty string
