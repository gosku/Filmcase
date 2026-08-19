"""
Python half of the shared push sequences.

The other fixtures pin the pieces: how a packet is framed, what a recipe
converts to, which recipes are rejected. This pins the sequence they are used
in, which is where the two implementations are most likely to differ while every
component still looks correct.

The JavaScript replays the same scenarios. Between them these say the browser
and the server hit the camera with the same writes, in the same order, with the
same pauses, and fail in the same way.
"""

from __future__ import annotations

import json
import pathlib
import time

import pytest

from src.application.usecases.camera import push_recipe as push_recipe_uc
from src.data.camera import constants
from src.domain.camera import ptp_device
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import queries as recipe_queries
from tests.fakes import FakePTPDevice

FIXTURES = pathlib.Path(__file__).parents[3] / "fixtures" / "camera"
_PUSH = json.loads((FIXTURES / "push_vectors.json").read_text())
_RECIPES = json.loads((FIXTURES / "recipe_ptp_vectors.json").read_text())
_SCENARIOS = _PUSH["scenarios"]


class _Recording(FakePTPDevice):
    """A fake that keeps every write attempted, refused ones included."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.writes: list[list[object]] = []
        self.reads: list[int] = []

    def set_property_int(self, code: int, value: int) -> int:
        self.writes.append([code, value])
        return super().set_property_int(code, value)

    def set_property_uint16(self, code: int, value: int) -> int:
        self.writes.append([code, value])
        return super().set_property_uint16(code, value)

    def set_property_string(self, code: int, value: str) -> int:
        self.writes.append([code, value])
        return super().set_property_string(code, value)

    def get_property_int(self, code: int) -> int:
        self.reads.append(code)
        return super().get_property_int(code)

    def get_property_string(self, code: int) -> str:
        self.reads.append(code)
        return super().get_property_string(code)


def _device_for(behaviour: dict) -> _Recording:
    codes = constants.CUSTOM_SLOT_CODES
    reject = {codes[name]: rc for name, rc in behaviour.get("reject", {}).items()}
    if "reject_cursor" in behaviour:
        reject[constants.PROP_SLOT_CURSOR] = behaviour["reject_cursor"]
    if "reject_slot_name" in behaviour:
        reject[constants.PROP_SLOT_NAME] = behaviour["reject_slot_name"]
    return _Recording(
        set_rejection_codes=reject,
        set_errors={
            codes[name]: ptp_device.CameraConnectionError("camera stopped answering")
            for name in behaviour.get("fail", [])
        },
        int_read_overrides={
            codes[name]: value for name, value in behaviour.get("read_overrides", {}).items()
        },
    )


def _replay(scenario: dict, settings, monkeypatch) -> dict:
    """Run one scenario against the current code and record what it did."""
    fields = dict(
        next(v for v in _RECIPES["vectors"] if v["name"] == scenario["recipe"])["recipe"]
    )
    fields["sensors"] = tuple(fields.get("sensors") or ())
    data = image_dataclasses.FujifilmRecipeData(**fields)

    for name, value in _PUSH["settings"].items():
        setattr(settings, name, value)
    settings.CAMERA_VERIFY_WRITES = bool(scenario["device"].get("verify", False))

    device = _device_for(scenario["device"])
    settings.PTP_DEVICE = lambda: device
    monkeypatch.setattr(recipe_queries, "recipe_from_db", lambda recipe: data)

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(round(seconds, 6)))

    error: dict | None = None
    try:
        push_recipe_uc.push_recipe_to_camera(None, slot_index=_PUSH["slot_index"])
    except push_recipe_uc.RecipeWriteError as exc:
        error = {"type": "RecipeWriteError", "failed_properties": list(exc.failed_properties)}
    except ptp_device.CameraConnectionError as exc:
        error = {"type": "CameraConnectionError", "message": str(exc)}
    except ptp_device.CameraWriteError as exc:
        error = {"type": "CameraWriteError", "code": exc.code}

    return {"writes": device.writes, "sleeps": sleeps, "reads": device.reads, "error": error}


class TestPushVectors:
    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["name"] for s in _SCENARIOS])
    def test_writes_match_the_frozen_sequence(self, scenario, settings, monkeypatch) -> None:
        result = _replay(scenario, settings, monkeypatch)

        assert result["writes"] == scenario["writes"], scenario["why"]

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["name"] for s in _SCENARIOS])
    def test_pauses_match_the_frozen_sequence(self, scenario, settings, monkeypatch) -> None:
        # The delays are distinct in this fixture, so this also says which pause
        # happened where. Pausing the right number of times in the wrong places
        # is a real bug and an identical-looking count otherwise.
        result = _replay(scenario, settings, monkeypatch)

        assert result["sleeps"] == scenario["sleeps"], scenario["why"]

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["name"] for s in _SCENARIOS])
    def test_outcome_matches_the_frozen_expectation(self, scenario, settings, monkeypatch) -> None:
        result = _replay(scenario, settings, monkeypatch)

        assert result["error"] == scenario["error"], scenario["why"]

    @pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["name"] for s in _SCENARIOS])
    def test_read_backs_match_the_frozen_sequence(self, scenario, settings, monkeypatch) -> None:
        result = _replay(scenario, settings, monkeypatch)

        assert result["reads"] == scenario["reads"], scenario["why"]


class TestPushVectorsCoverage:
    def test_covers_a_clean_push(self) -> None:
        assert any(s["error"] is None for s in _SCENARIOS)

    def test_covers_a_refusal_the_sequence_survives(self) -> None:
        # The camera declines one property and stays reachable, so every later
        # property must still be written.
        refused = next(s for s in _SCENARIOS if s["name"] == "one_property_refused")
        clean = next(s for s in _SCENARIOS if s["name"] == "clean_push")

        assert len(refused["writes"]) == len(clean["writes"])
        assert refused["error"]["type"] == "RecipeWriteError"

    def test_covers_a_camera_that_vanishes(self) -> None:
        # The sequence must stop, not work through the rest.
        vanished = next(s for s in _SCENARIOS if s["name"] == "camera_vanishes_midway")
        clean = next(s for s in _SCENARIOS if s["name"] == "clean_push")

        assert len(vanished["writes"]) < len(clean["writes"])
        assert vanished["error"]["type"] == "CameraConnectionError"

    def test_covers_verification_finding_a_property_that_did_not_stick(self) -> None:
        drift = next(s for s in _SCENARIOS if s["name"] == "verification_catches_drift")

        assert drift["reads"]
        assert drift["error"]["failed_properties"] == ["Sharpness"]

    def test_covers_the_grain_sentinel_being_left_unverified(self) -> None:
        # Its read-back never matches, so verifying it would fail every push
        # with grain off.
        with_grain = next(s for s in _SCENARIOS if s["name"] == "verification_clean")
        grain_off = next(
            s for s in _SCENARIOS if s["name"] == "verification_skips_the_grain_sentinel"
        )

        assert len(grain_off["reads"]) == len(with_grain["reads"]) - 1
        assert constants.CUSTOM_SLOT_CODES["GrainEffect"] not in grain_off["reads"]

    def test_uses_distinct_delays_so_a_sleep_says_which_pause_it_was(self) -> None:
        delays = [v for k, v in _PUSH["settings"].items() if k.endswith("_DELAY_S")]

        assert len(delays) == len(set(delays))
