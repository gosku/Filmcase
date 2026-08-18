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
from src.domain.images import dataclasses as image_dataclasses

VECTORS_PATH = pathlib.Path(__file__).parents[3] / "fixtures" / "camera" / "recipe_ptp_vectors.json"

_FIXTURE = json.loads(VECTORS_PATH.read_text())
_VECTORS = _FIXTURE["vectors"]


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
