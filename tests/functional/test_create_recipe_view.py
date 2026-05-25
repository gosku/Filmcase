from decimal import Decimal
from unittest.mock import patch

import pytest

from src.application.usecases.recipes import create_recipe_manually as create_recipe_manually_uc
from src.data import models
from src.interfaces import forms as interface_forms

_URL = "/recipes/create/"


def _valid_data(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "My Recipe",
        "film_simulation": "Provia",
        "dynamic_range": "DR100",
        "d_range_priority": "Off",
        "grain_roughness": "Off",
        "grain_size": "Off",
        "color_chrome_effect": "Off",
        "color_chrome_fx_blue": "Off",
        "white_balance": "Auto",
        "white_balance_red": "0",
        "white_balance_blue": "0",
        "highlight": "0",
        "shadow": "0",
        "color": "0",
        "sharpness": "0",
        "high_iso_nr": "0",
        "clarity": "0",
    }
    base.update(overrides)
    return base


def _bound_form(**overrides: object) -> interface_forms.CreateRecipe:
    """Return a bound, validated CreateRecipe form without going through the view."""
    form = interface_forms.CreateRecipe(data=_valid_data(**overrides))
    form.is_valid()
    return form


@pytest.mark.django_db
class TestCreateRecipeView:
    def test_get_renders_the_form(self, client) -> None:
        response = client.get(_URL)
        assert response.status_code == 200

    def test_post_with_valid_data_redirects(self, client) -> None:
        response = client.post(_URL, _valid_data())
        assert response.status_code == 302

    def test_post_without_name_shows_error(self, client) -> None:
        data = _valid_data()
        del data["name"]
        form = client.post(_URL, data).context["form"]
        assert "name" in form.errors

    def test_post_with_name_exceeding_max_length_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(name="a" * 26)).context["form"]
        assert "name" in form.errors

    # ── Field range validation ────────────────────────────────────

    def test_post_with_color_above_max_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(color="5")).context["form"]
        assert "color" in form.errors

    def test_post_with_color_below_min_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(color="-5")).context["form"]
        assert "color" in form.errors

    def test_post_with_highlight_above_max_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(highlight="5")).context["form"]
        assert "highlight" in form.errors

    def test_post_with_highlight_below_min_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(highlight="-3")).context["form"]
        assert "highlight" in form.errors

    def test_post_with_highlight_on_invalid_step_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(highlight="1.3")).context["form"]
        assert "highlight" in form.errors

    def test_post_with_highlight_on_valid_half_step_redirects(self, client) -> None:
        response = client.post(_URL, _valid_data(highlight="1.5"))
        assert response.status_code == 302

    def test_post_with_sharpness_above_max_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(sharpness="5")).context["form"]
        assert "sharpness" in form.errors

    def test_post_with_clarity_above_max_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(clarity="6")).context["form"]
        assert "clarity" in form.errors

    def test_post_with_white_balance_red_above_max_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(white_balance_red="10")).context["form"]
        assert "white_balance_red" in form.errors

    def test_post_with_white_balance_blue_below_min_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(white_balance_blue="-10")).context["form"]
        assert "white_balance_blue" in form.errors

    # ── Kelvin white balance ──────────────────────────────────────

    def test_post_with_kelvin_wb_without_temperature_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(white_balance="Kelvin")).context["form"]
        assert "kelvin_temperature" in form.errors

    def test_post_with_kelvin_wb_and_valid_temperature_redirects(self, client) -> None:
        response = client.post(_URL, _valid_data(white_balance="Kelvin", kelvin_temperature="6500"))
        assert response.status_code == 302

    def test_post_with_kelvin_temperature_out_of_range_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(white_balance="Kelvin", kelvin_temperature="100")).context["form"]
        assert "kelvin_temperature" in form.errors

    def test_non_kelvin_wb_cleans_temperature_to_none(self) -> None:
        form = _bound_form(white_balance="Auto", kelvin_temperature="6500")
        assert form.cleaned_data["kelvin_temperature"] is None

    # ── Monochromatic cross-field cleaning ────────────────────────

    def test_mono_film_sim_preserves_mono_fields(self) -> None:
        form = _bound_form(
            film_simulation="Acros STD",
            monochromatic_color_warm_cool="3",
            monochromatic_color_magenta_green="-2",
        )
        assert form.cleaned_data["monochromatic_color_warm_cool"] == Decimal("3")
        assert form.cleaned_data["monochromatic_color_magenta_green"] == Decimal("-2")

    def test_non_mono_film_sim_cleans_mono_fields_to_none(self) -> None:
        form = _bound_form(
            film_simulation="Provia",
            monochromatic_color_warm_cool="3",
            monochromatic_color_magenta_green="-2",
        )
        assert form.cleaned_data["monochromatic_color_warm_cool"] is None
        assert form.cleaned_data["monochromatic_color_magenta_green"] is None

    def test_post_with_mono_field_out_of_range_shows_error(self, client) -> None:
        form = client.post(_URL, _valid_data(
            film_simulation="Acros STD",
            monochromatic_color_warm_cool="10",
        )).context["form"]
        assert "monochromatic_color_warm_cool" in form.errors

    # ── Grain cross-field cleaning ────────────────────────────────

    def test_grain_roughness_off_cleans_grain_size_to_none(self) -> None:
        form = _bound_form(grain_roughness="Off", grain_size="Large")
        assert form.cleaned_data["grain_size"] is None

    def test_grain_roughness_set_preserves_grain_size(self) -> None:
        form = _bound_form(grain_roughness="Weak", grain_size="Large")
        assert form.cleaned_data["grain_size"] == "Large"

    # ── D-Range Priority cross-field cleaning ─────────────────────

    def test_active_d_range_priority_cleans_dynamic_range_to_none(self) -> None:
        form = _bound_form(d_range_priority="Weak", dynamic_range="DR200")
        assert form.cleaned_data["dynamic_range"] is None

    def test_post_with_active_d_range_priority_without_dynamic_range_redirects(self, client) -> None:
        # Browser does not submit disabled selects; dynamic_range must not be required
        # when D-Range Priority is active.
        data = _valid_data(d_range_priority="Weak")
        del data["dynamic_range"]
        response = client.post(_URL, data)
        assert response.status_code == 302

    def test_d_range_priority_off_preserves_dynamic_range(self) -> None:
        form = _bound_form(d_range_priority="Off", dynamic_range="DR400")
        assert form.cleaned_data["dynamic_range"] == "DR400"

    def test_post_with_d_range_priority_off_and_no_dynamic_range_shows_error(self, client) -> None:
        data = _valid_data(d_range_priority="Off")
        del data["dynamic_range"]
        form = client.post(_URL, data).context["form"]
        assert "dynamic_range" in form.errors


@pytest.mark.django_db
class TestCreateRecipeViewSubmission:
    def test_valid_post_creates_recipe_in_db(self, client) -> None:
        client.post(_URL, _valid_data())
        assert models.FujifilmRecipe.objects.count() == 1

    def test_valid_post_redirects_to_recipe_detail(self, client) -> None:
        response = client.post(_URL, _valid_data())
        recipe = models.FujifilmRecipe.objects.get()
        assert response.status_code == 302
        assert response["Location"] == f"/recipes/{recipe.pk}/?name_search=My+Recipe"

    def test_duplicate_settings_show_already_exists_error(self, client) -> None:
        client.post(_URL, _valid_data(name="First"))
        response = client.post(_URL, _valid_data(name="Second"))
        assert response.status_code == 200
        errors = response.context["form"].non_field_errors()
        assert any("already exists" in e for e in errors)

    def test_already_exists_error_includes_existing_recipe_name(self, client) -> None:
        client.post(_URL, _valid_data(name="My Preset"))
        response = client.post(_URL, _valid_data(name="Other Name"))
        errors = " ".join(response.context["form"].non_field_errors())
        assert "My Preset" in errors

    def test_unexpected_error_shows_generic_message(self, client) -> None:
        with patch.object(create_recipe_manually_uc, "create_recipe_manually", side_effect=RuntimeError("boom")):
            response = client.post(_URL, _valid_data())
        assert response.status_code == 200
        errors = response.context["form"].non_field_errors()
        assert any("unexpected error" in e.lower() for e in errors)


@pytest.mark.django_db
class TestCreateRecipeViewWithSensorsAndDescription:
    def test_post_with_sensors_attaches_them_to_the_recipe(self, client) -> None:
        data = _valid_data(name="With Sensors")
        # Django test client serialises lists as repeated keys, matching the
        # browser's encoding of <input type="checkbox" name="sensors" ...>.
        data["sensors"] = ["X-Trans IV", "GFX"]

        client.post(_URL, data)

        recipe = models.FujifilmRecipe.objects.get(name="With Sensors")
        assert sorted(s.name for s in recipe.sensors.all()) == ["GFX", "X-Trans IV"]

    def test_post_with_description_writes_it_to_the_recipe(self, client) -> None:
        data = _valid_data(name="With Notes", description="Recipe notes here.")

        client.post(_URL, data)

        recipe = models.FujifilmRecipe.objects.get(name="With Notes")
        assert recipe.description == "Recipe notes here."

    def test_post_without_new_fields_creates_recipe_with_defaults(self, client) -> None:
        # Submissions that omit the new fields (e.g. an older HTML page or a
        # programmatic POST) still succeed; sensors stays empty, description
        # stays "".
        client.post(_URL, _valid_data(name="No New Fields"))

        recipe = models.FujifilmRecipe.objects.get(name="No New Fields")
        assert list(recipe.sensors.all()) == []
        assert recipe.description == ""

    def test_post_rejects_unknown_sensor_name(self, client) -> None:
        data = _valid_data(name="Bad Sensor")
        data["sensors"] = ["Imaginary Sensor"]

        response = client.post(_URL, data)

        assert response.status_code == 200  # form re-renders with errors
        assert "sensors" in response.context["form"].errors
