"""
Python half of the shared recipe -> PTP value golden vectors.

The JavaScript port asserts against the same file, which is what stops the two
implementations drifting apart without anyone noticing. These vectors do not
prove the conversion is correct; test_camera_queries.py does that. They prove
the two ports agree, and they freeze the wire format so a change to it shows up
as a deliberate diff rather than a surprise on the camera.

A failure here means one of two things: the conversion changed, or an encoding
changed. Either way, regenerate the fixture only once you are satisfied the new
values are the ones you meant to send.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.domain.camera import queries as camera_queries
from src.domain.camera import validation
from src.domain.images import dataclasses as image_dataclasses

VECTORS_PATH = pathlib.Path(__file__).parents[3] / "fixtures" / "camera" / "recipe_ptp_vectors.json"

_FIXTURE = json.loads(VECTORS_PATH.read_text())
_VECTORS = _FIXTURE["vectors"]
# The recipe every validation vector starts from, before its overrides.
_BASE_RECIPE = next(v for v in _VECTORS if v["name"] == "named_white_balance")["recipe"]


def _recipe_from_vector(vector: dict) -> image_dataclasses.FujifilmRecipeData:
    fields = dict(vector["recipe"])
    fields["sensors"] = tuple(fields.get("sensors") or ())
    return image_dataclasses.FujifilmRecipeData(**fields)


class TestRecipePTPVectors:
    @pytest.mark.parametrize("vector", _VECTORS, ids=[v["name"] for v in _VECTORS])
    def test_conversion_matches_the_frozen_expectation(self, vector) -> None:
        recipe = _recipe_from_vector(vector)

        items = camera_queries.recipe_to_ptp_values(recipe).items()

        expected = [(code, value) for code, value in vector["expected_items"]]
        assert items == expected, vector["why"]

    def test_the_vectors_are_not_empty(self) -> None:
        # A truncated or mis-generated fixture would otherwise turn every
        # parametrized test above into zero tests, silently.
        assert len(_VECTORS) >= 10

    def test_every_vector_has_a_distinct_name(self) -> None:
        names = [v["name"] for v in _VECTORS]

        assert len(names) == len(set(names))

    def test_a_vector_pins_the_colour_temperature_ordering_rule(self) -> None:
        # The rule these vectors exist to protect most: writing the shifts
        # before the temperature makes the camera zero them.
        codes = camera_queries.client_camera_encodings().custom_slot_codes
        temperature = codes["WhiteBalanceColorTemperature"]
        red = codes["WhiteBalanceRed"]

        covering = [
            v for v in _VECTORS
            if temperature in [code for code, _ in v["expected_items"]]
        ]
        assert covering, "no vector exercises a Kelvin white balance"

        for vector in covering:
            written = [code for code, _ in vector["expected_items"]]
            assert written.index(temperature) < written.index(red), vector["name"]

    def test_a_vector_covers_the_grain_off_sentinel(self) -> None:
        grain = camera_queries.client_camera_encodings().custom_slot_codes["GrainEffect"]

        written_grain_values = {
            value
            for vector in _VECTORS
            for code, value in vector["expected_items"]
            if code == grain
        }

        assert camera_queries.GRAIN_OFF_SENTINEL in written_grain_values

    def test_a_vector_covers_a_monochrome_simulation(self) -> None:
        # Monochrome is the case where the field set itself changes: colour
        # drops out and the two toning axes appear.
        codes = camera_queries.client_camera_encodings().custom_slot_codes
        colour = codes["ColorMode"]
        warm_cool = codes["MonochromaticColorWarmCool"]

        covering = [
            v for v in _VECTORS
            if warm_cool in [code for code, _ in v["expected_items"]]
        ]
        assert covering, "no vector exercises a monochrome simulation"

        for vector in covering:
            written = [code for code, _ in vector["expected_items"]]
            assert colour not in written, vector["name"]

    def test_a_vector_covers_negative_values(self) -> None:
        # Negatives go on the wire as two's complement and read back masked to
        # 16 bits, which is the easiest thing to get wrong in a port.
        assert any(
            value < 0
            for vector in _VECTORS
            for _, value in vector["expected_items"]
        )

    def test_a_vector_covers_half_step_tone_curves(self) -> None:
        # Half steps are why the tone curves round rather than truncate.
        codes = camera_queries.client_camera_encodings().custom_slot_codes
        highlight = codes["HighLightTone"]

        values = {
            value
            for vector in _VECTORS
            for code, value in vector["expected_items"]
            if code == highlight
        }

        assert any(value % 10 != 0 for value in values), "no vector uses a half step"


class TestVectorsFixtureShape:
    def test_carries_an_encodings_snapshot_for_the_javascript_suite(self) -> None:
        # The JS tests have no Django to ask, so the tables they convert with
        # travel alongside the expectations they were frozen with.
        encodings = _FIXTURE["encodings"]

        assert encodings["write_order"]
        assert encodings["custom_slot_codes"]
        assert encodings["film_simulation_to_ptp"]

    def test_every_written_code_is_a_known_custom_slot_code(self) -> None:
        known = set(camera_queries.client_camera_encodings().custom_slot_codes.values())

        written = {code for v in _VECTORS for code, _ in v["expected_items"]}

        assert written <= known


_VALIDATION_VECTORS = _FIXTURE["validation_vectors"]


class TestValidationVectors:
    """
    The accept/reject table both validators must agree on.

    The JavaScript asserts the same list. Python's int() rejects "1.5" while
    JavaScript's parseInt returns 1, so without this a lenient port would accept
    a half step for an integer field and have it silently truncated on the way
    to the camera.
    """

    @pytest.mark.parametrize(
        "vector", _VALIDATION_VECTORS, ids=[v["name"] for v in _VALIDATION_VECTORS]
    )
    def test_outcome_matches_the_frozen_expectation(self, vector) -> None:
        fields = {**_BASE_RECIPE, **vector["overrides"]}
        fields["sensors"] = tuple(fields.get("sensors") or ())
        # The attrs name validator is bypassed so this exercises the same
        # function the browser does: it receives plain JSON and has no
        # constructor checks, so validate_recipe_for_camera is all that stands
        # between a bad name and the camera there.
        recipe = image_dataclasses.FujifilmRecipeData(**{**fields, "name": "placeholder"})
        object.__setattr__(recipe, "name", fields["name"])

        try:
            validation.validate_recipe_for_camera(recipe)
            outcome = "ok"
        except validation.RecipeValidationError as error:
            outcome = f"reject:{error.field}"

        assert outcome == vector["expected"]

    def test_covers_both_outcomes(self) -> None:
        outcomes = {v["expected"] for v in _VALIDATION_VECTORS}

        assert "ok" in outcomes
        assert any(o.startswith("reject:") for o in outcomes)

    def test_covers_the_half_step_hazard(self) -> None:
        # The single case most likely to diverge between the two languages.
        half_steps = [
            v for v in _VALIDATION_VECTORS
            if v["overrides"].get("color") == "1.5"
        ]

        assert half_steps, "no vector feeds a half step to an integer field"
        assert half_steps[0]["expected"] == "reject:color"
