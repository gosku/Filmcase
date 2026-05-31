import pytest

from src.domain.images.filter_queries import get_sidebar_filter_options
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetSidebarFilterOptionsNoFilters:
    def test_returns_entry_for_every_filter_field(self):
        result = get_sidebar_filter_options({})

        expected_fields = [
            "film_simulation", "dynamic_range", "d_range_priority",
            "grain_roughness", "grain_size", "color_chrome_effect",
            "color_chrome_fx_blue", "white_balance",
            "white_balance_red", "white_balance_blue",
            "highlight", "shadow", "color", "sharpness", "high_iso_nr", "clarity",
        ]
        assert list(result.keys()) == expected_fields

    def test_shows_all_distinct_values_when_no_filter_active(self):
        FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        FujifilmRecipeFactory(film_simulation="Velvia", grain_size="Weak")
        ImageFactory(fujifilm_recipe=FujifilmRecipeFactory(film_simulation="Provia"))
        ImageFactory(fujifilm_recipe=FujifilmRecipeFactory(film_simulation="Velvia"))

        result = get_sidebar_filter_options({})

        film_values = {o["value"] for o in result["film_simulation"]["options"]}
        assert "Provia" in film_values
        assert "Velvia" in film_values

    def test_images_without_recipe_are_excluded_from_counts(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=None)  # no recipe — must not count

        result = get_sidebar_filter_options({})

        provia_opt = next(
            o for o in result["film_simulation"]["options"] if o["value"] == "Provia"
        )
        assert provia_opt["count"] == 1


@pytest.mark.django_db
class TestGetSidebarFilterOptionsFacetedBehaviour:
    def test_selecting_one_value_restricts_other_fields(self):
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        recipe_b = FujifilmRecipeFactory(film_simulation="Velvia", grain_size="Weak")
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        result = get_sidebar_filter_options({"film_simulation": ["Provia"]})

        grain_available = {
            o["value"] for o in result["grain_size"]["options"] if o["available"]
        }
        assert grain_available == {"Off"}
        assert "Weak" not in grain_available

    def test_own_field_options_not_narrowed_by_own_selection(self):
        """Selecting Provia must not hide Velvia from the film_simulation list."""
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia")
        recipe_b = FujifilmRecipeFactory(film_simulation="Velvia")
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        result = get_sidebar_filter_options({"film_simulation": ["Provia"]})

        film_available = {
            o["value"] for o in result["film_simulation"]["options"] if o["available"]
        }
        assert "Provia" in film_available
        assert "Velvia" in film_available

    def test_multiple_values_in_same_field_are_or_combined(self):
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        recipe_b = FujifilmRecipeFactory(film_simulation="Velvia", grain_size="Weak")
        recipe_c = FujifilmRecipeFactory(film_simulation="Astia", grain_size="Strong")
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)
        ImageFactory(fujifilm_recipe=recipe_c)

        result = get_sidebar_filter_options({"film_simulation": ["Provia", "Velvia"]})

        grain_available = {
            o["value"] for o in result["grain_size"]["options"] if o["available"]
        }
        # Only Off (Provia) and Weak (Velvia); Strong belongs to Astia which is excluded
        assert grain_available == {"Off", "Weak"}
        assert "Strong" not in grain_available

    def test_counts_reflect_filtered_image_set(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)
        other = FujifilmRecipeFactory(film_simulation="Velvia", grain_size="Off")
        ImageFactory(fujifilm_recipe=other)

        result = get_sidebar_filter_options({"film_simulation": ["Provia"]})

        grain_opts = {o["value"]: o for o in result["grain_size"]["options"]}
        # Only the 3 Provia images contribute to the Off count
        assert grain_opts["Off"]["count"] == 3


@pytest.mark.django_db
class TestGetSidebarFilterOptionsUnavailableValues:
    def test_selected_but_unavailable_value_is_included_with_available_false(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        ImageFactory(fujifilm_recipe=recipe)

        # Selecting Weak grain together with Provia film — no image matches both
        result = get_sidebar_filter_options({
            "film_simulation": ["Provia"],
            "grain_size": ["Weak"],
        })

        grain_opts = {o["value"]: o for o in result["grain_size"]["options"]}
        assert "Weak" in grain_opts
        assert grain_opts["Weak"]["available"] is False
        assert grain_opts["Weak"]["selected"] is True
        assert grain_opts["Weak"]["count"] == 0

    def test_unavailable_value_becomes_available_after_conflicting_filter_removed(self):
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        recipe_b = FujifilmRecipeFactory(film_simulation="Velvia", grain_size="Weak")
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        # With Provia selected, Weak is unavailable
        result_restricted = get_sidebar_filter_options({
            "film_simulation": ["Provia"],
            "grain_size": ["Weak"],
        })
        grain_opts = {o["value"]: o for o in result_restricted["grain_size"]["options"]}
        assert grain_opts["Weak"]["available"] is False

        # Without the film_simulation filter, Weak becomes available again
        result_open = get_sidebar_filter_options({"grain_size": ["Weak"]})
        grain_opts_open = {o["value"]: o for o in result_open["grain_size"]["options"]}
        assert grain_opts_open["Weak"]["available"] is True

    def test_unavailable_values_sorted_after_available_ones(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia", grain_size="Off")
        ImageFactory(fujifilm_recipe=recipe)

        result = get_sidebar_filter_options({
            "film_simulation": ["Provia"],
            "grain_size": ["Weak"],  # unavailable
        })

        options = result["grain_size"]["options"]
        available_indices = [i for i, o in enumerate(options) if o["available"]]
        unavailable_indices = [i for i, o in enumerate(options) if not o["available"]]
        if available_indices and unavailable_indices:
            assert max(available_indices) < min(unavailable_indices)


@pytest.mark.django_db
class TestGetSidebarFilterOptionsDecimalFields:
    def test_null_decimal_recipes_excluded_from_options(self):
        # Factory leaves decimal fields as None; they must not appear in options.
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)

        result = get_sidebar_filter_options({})

        assert result["highlight"]["options"] == []

    def test_decimal_field_values_sort_numerically(self):
        recipe_a = FujifilmRecipeFactory(highlight="-2.0", white_balance_red=0)
        recipe_b = FujifilmRecipeFactory(highlight="1.5", white_balance_red=1)
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        result = get_sidebar_filter_options({})

        values = [o["value"] for o in result["highlight"]["options"]]
        assert values.index("-2") < values.index("1.5")


@pytest.mark.django_db
class TestGetSidebarFilterOptionsIntegerFields:
    def test_integer_field_values_are_strings_in_options(self):
        recipe = FujifilmRecipeFactory(white_balance_red=3, white_balance_blue=-2)
        ImageFactory(fujifilm_recipe=recipe)

        result = get_sidebar_filter_options({})

        wb_red_values = [o["value"] for o in result["white_balance_red"]["options"]]
        assert "3" in wb_red_values  # normalised to string
        assert 3 not in wb_red_values  # not an int

    def test_integer_field_selected_value_matches_string_from_url(self):
        recipe = FujifilmRecipeFactory(white_balance_red=3)
        ImageFactory(fujifilm_recipe=recipe)

        result = get_sidebar_filter_options({"white_balance_red": ["3"]})

        wb_opts = {o["value"]: o for o in result["white_balance_red"]["options"]}
        assert wb_opts["3"]["selected"] is True
        assert wb_opts["3"]["available"] is True
