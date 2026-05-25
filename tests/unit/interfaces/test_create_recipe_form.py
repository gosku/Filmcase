"""Unit tests for the CreateRecipe form's sensors and description fields."""

from src.interfaces import forms as interface_forms


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
        "white_balance_red": 0,
        "white_balance_blue": 0,
        "highlight": "0",
        "shadow": "0",
        "color": "0",
        "sharpness": 0,
        "high_iso_nr": 0,
        "clarity": 0,
        "monochromatic_color_warm_cool": "0",
        "monochromatic_color_magenta_green": "0",
    }
    base.update(overrides)
    return base


class TestCreateRecipeSensors:
    def test_omitting_sensors_is_valid(self):
        # Existing forms that don't render the new field must still validate.
        form = interface_forms.CreateRecipe(data=_valid_data())

        assert form.is_valid(), form.errors

    def test_accepts_single_known_sensor(self):
        form = interface_forms.CreateRecipe(data=_valid_data(sensors=["X-Trans IV"]))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["sensors"] == ["X-Trans IV"]

    def test_accepts_multiple_known_sensors(self):
        form = interface_forms.CreateRecipe(
            data=_valid_data(sensors=["X-Trans IV", "GFX"])
        )

        assert form.is_valid(), form.errors
        assert set(form.cleaned_data["sensors"]) == {"X-Trans IV", "GFX"}

    def test_rejects_unknown_sensor_name(self):
        form = interface_forms.CreateRecipe(
            data=_valid_data(sensors=["Imaginary Sensor"])
        )

        assert not form.is_valid()
        assert "sensors" in form.errors


class TestCreateRecipeDescription:
    def test_omitting_description_is_valid(self):
        form = interface_forms.CreateRecipe(data=_valid_data())

        assert form.is_valid(), form.errors
        # Django CharField returns "" when not submitted.
        assert form.cleaned_data["description"] == ""

    def test_accepts_short_description(self):
        form = interface_forms.CreateRecipe(
            data=_valid_data(description="Some notes")
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["description"] == "Some notes"

    def test_accepts_long_description(self):
        long_text = "x" * 5000

        form = interface_forms.CreateRecipe(data=_valid_data(description=long_text))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["description"] == long_text
