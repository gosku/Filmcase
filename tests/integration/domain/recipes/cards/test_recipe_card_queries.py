import json

import pytest

from src.data import models
from src.domain.recipes.cards import queries, templates


def _recipe(**kwargs: object) -> models.FujifilmRecipe:
    """
    Return a saved FujifilmRecipe with sensible defaults, overridable via kwargs.

    The recipe is persisted because get_recipe_as_json() and
    get_recipe_cover_lines() both query the ``sensors`` M2M relation, which
    Django refuses to evaluate on unsaved instances.
    """
    defaults: dict[str, object] = {
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
    }
    defaults.update(kwargs)
    return models.FujifilmRecipe.objects.create(**defaults)


@pytest.mark.django_db
class TestGetRecipeAsJson:
    def test_includes_current_version_key(self) -> None:
        # The producer emits the current schema version. Decoders accept the
        # current version plus any documented legacy versions
        # (see _ACCEPTED_QR_SCHEMA_VERSIONS in cards/queries.py).
        payload = json.loads(queries.get_recipe_as_json(recipe=_recipe()))
        assert payload["v"] == queries._CURRENT_QR_SCHEMA_VERSION

    def test_includes_film_simulation(self) -> None:
        payload = json.loads(queries.get_recipe_as_json(recipe=_recipe(film_simulation="Classic Chrome")))
        assert payload["film_simulation"] == "Classic Chrome"

    def test_output_is_minified(self) -> None:
        result = queries.get_recipe_as_json(recipe=_recipe())
        assert " " not in result

    def test_omits_color_only_fields_for_monochromatic_simulation(self) -> None:
        # ``color`` is the only field flagged as colour-only in
        # _COLOR_ONLY_FIELDS; CCE and CC FX Blue apply to both monochrome and
        # colour simulations (mono recipes set them too) and are kept in the
        # payload.
        recipe = _recipe(film_simulation="Acros STD", color=None)
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "color" not in payload

    def test_includes_color_fields_for_colour_simulation(self) -> None:
        recipe = _recipe(film_simulation="Provia", color_chrome_effect="Strong", color_chrome_fx_blue="Weak")
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "color_chrome_effect" in payload
        assert "color_chrome_fx_blue" in payload

    def test_omits_monochrome_only_fields_for_colour_simulation(self) -> None:
        recipe = _recipe(film_simulation="Provia", monochromatic_color_warm_cool=None, monochromatic_color_magenta_green=None)
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "monochromatic_color_warm_cool" not in payload
        assert "monochromatic_color_magenta_green" not in payload

    def test_includes_monochrome_only_fields_for_monochromatic_simulation(self) -> None:
        from decimal import Decimal
        recipe = _recipe(
            film_simulation="Acros STD",
            monochromatic_color_warm_cool=Decimal("0"),
            monochromatic_color_magenta_green=Decimal("2"),
        )
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "monochromatic_color_warm_cool" in payload
        assert "monochromatic_color_magenta_green" in payload

    def test_includes_zero_decimal_values(self) -> None:
        from decimal import Decimal
        recipe = _recipe(highlight=Decimal("0"), shadow=Decimal("0"))
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "highlight" in payload
        assert payload["highlight"] == 0

    def test_omits_none_values_for_applicable_fields(self) -> None:
        recipe = _recipe(highlight=None, shadow=None)
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "highlight" not in payload
        assert "shadow" not in payload

    def test_omits_drp_fields_when_drp_is_active(self) -> None:
        from decimal import Decimal
        recipe = _recipe(d_range_priority="Auto", dynamic_range="DR100", highlight=Decimal("1"), shadow=Decimal("-1"))
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "dynamic_range" not in payload
        assert "highlight" not in payload
        assert "shadow" not in payload

    def test_omits_grain_size_when_grain_roughness_is_off(self) -> None:
        recipe = _recipe(grain_roughness="Off", grain_size="Small")
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "grain_size" not in payload

    def test_includes_grain_size_when_grain_roughness_is_not_off(self) -> None:
        recipe = _recipe(grain_roughness="Weak", grain_size="Small")
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "grain_size" in payload

    def test_includes_name_when_recipe_has_a_name(self) -> None:
        recipe = _recipe(name="My Summer Recipe")
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert payload["name"] == "My Summer Recipe"

    def test_omits_name_when_recipe_is_unnamed(self) -> None:
        recipe = _recipe()  # default model name is ""
        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))
        assert "name" not in payload


@pytest.mark.django_db
class TestGetRecipeCoverLines:
    def test_returns_field_lines(self) -> None:
        recipe = _recipe()
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        assert all(isinstance(line, queries.FieldLine) for line in lines)

    def test_uses_long_labels_for_long_template(self) -> None:
        recipe = _recipe(film_simulation="Provia")
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        labels = [line.label for line in lines]
        assert "Film Simulation" in labels

    def test_uses_short_labels_for_short_template(self) -> None:
        recipe = _recipe(film_simulation="Provia")
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.SHORT_LABEL)
        labels = [line.label for line in lines]
        assert "Film Sim" in labels
        assert "Film Simulation" not in labels

    def test_film_simulation_value_is_present(self) -> None:
        recipe = _recipe(film_simulation="Velvia")
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        film_line = next(l for l in lines if l.label == "Film Simulation")
        assert film_line.value == "Velvia"

    def test_omits_inapplicable_fields(self) -> None:
        # ``color`` is the only field flagged as colour-only via
        # _COLOR_ONLY_FIELDS; for a mono sim it is omitted from the card.
        recipe = _recipe(film_simulation="Acros STD", color=None)
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        labels = [line.label for line in lines]
        assert "Color" not in labels

    def test_omits_grain_size_when_grain_roughness_is_off(self) -> None:
        recipe = _recipe(grain_roughness="Off", grain_size="Small")
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        labels = [line.label for line in lines]
        assert "Grain Size" not in labels

    def test_omits_none_values(self) -> None:
        recipe = _recipe(highlight=None, shadow=None)
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        labels = [line.label for line in lines]
        assert "Highlight" not in labels
        assert "Shadow" not in labels

    def test_omits_drp_fields_when_drp_is_active(self) -> None:
        from decimal import Decimal
        recipe = _recipe(d_range_priority="Auto", dynamic_range="DR100", highlight=Decimal("1"), shadow=Decimal("-1"))
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        labels = [line.label for line in lines]
        assert "Dynamic Range" not in labels
        assert "Highlight" not in labels
        assert "Shadow" not in labels

    def test_field_order_matches_display_fields(self) -> None:
        from decimal import Decimal
        recipe = _recipe(
            film_simulation="Provia",
            grain_roughness="Weak",
            grain_size="Large",
            white_balance="Daylight",
            highlight=Decimal("1"),
            shadow=Decimal("-1"),
        )
        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)
        present_fields = [line.label for line in lines]
        film_idx = present_fields.index("Film Simulation")
        wb_idx = present_fields.index("White Balance")
        hl_idx = present_fields.index("Highlight")
        assert film_idx < wb_idx < hl_idx


@pytest.mark.django_db
class TestGetRecipeAsJsonSensors:
    """Encoder behaviour around the ``sensors`` key (introduced in v=2)."""

    def test_omits_sensors_when_recipe_has_no_attached_sensors(self) -> None:
        recipe = _recipe()

        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))

        assert "sensors" not in payload

    def test_includes_sensors_sorted_when_recipe_has_them(self) -> None:
        recipe = _recipe()
        recipe.set_sensors(
            sensors=models.Sensor.objects.filter(name__in=["X-Trans IV", "GFX"])
        )

        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))

        # Lexicographic sort: "GFX" < "X-Trans IV".
        assert payload["sensors"] == ["GFX", "X-Trans IV"]


@pytest.mark.django_db
class TestGetRecipeAsJsonDescription:
    def test_description_never_appears_in_payload(self) -> None:
        # By design: description is private notes, not sharing-relevant
        # settings, so it's excluded from the QR payload regardless of
        # whether the recipe has a description set.
        recipe = _recipe(description="Some recipe notes")

        payload = json.loads(queries.get_recipe_as_json(recipe=recipe))

        assert "description" not in payload


@pytest.mark.django_db
class TestGetRecipeCoverLinesSensors:
    def test_omits_sensors_line_when_recipe_has_none(self) -> None:
        recipe = _recipe()

        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)

        assert "Sensors" not in [line.label for line in lines]

    def test_prepends_sensors_line_when_recipe_has_sensors(self) -> None:
        recipe = _recipe()
        recipe.set_sensors(
            sensors=models.Sensor.objects.filter(name__in=["X-Trans IV", "GFX"])
        )

        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.LONG_LABEL)

        # The sensors line is first so receivers see compatibility before
        # reading any settings.
        assert lines[0].label == "Sensors"
        assert lines[0].value == "GFX, X-Trans IV"

    def test_uses_short_label_style(self) -> None:
        recipe = _recipe()
        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="X-Trans V"))

        lines = queries.get_recipe_cover_lines(recipe=recipe, template=templates.SHORT_LABEL)

        # Long/short happen to be identical here ("Sensors"); the test
        # documents the contract for future divergence.
        assert lines[0].label == "Sensors"
        assert lines[0].value == "X-Trans V"
