"""
Regenerate push_vectors.json, the golden push sequences shared by the Python and
JavaScript implementations of push_recipe_to_camera.

    FILMCASE_ENV_FILE=/dev/null .venv/bin/python tests/fixtures/camera/generate_push_vectors.py

The other fixtures pin the pieces: how a packet is framed, what a recipe
converts to, which recipes are rejected. This pins the sequence they are used
in, which is where a port is most likely to differ while every component still
looks correct.

Each scenario records three things:

  writes  every (code, value) sent, in order, including ones the camera refused
  sleeps  every pause taken, in order
  error   what the use case raised, if anything

The delays are deliberately distinct rather than all 0.05, so the recorded sleep
sequence says which pause happened where. A run that pauses the right number of
times in the wrong places is a real bug and an identical-looking list otherwise.

Regenerate deliberately. A diff here means the order of operations against the
camera changed.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.config.settings")

import django  # noqa: E402

django.setup()

import structlog  # noqa: E402
from django.conf import settings  # noqa: E402

from src.application.usecases.camera import push_recipe as push_recipe_uc  # noqa: E402
from src.domain.camera import ptp_device  # noqa: E402
from src.domain.images import dataclasses as image_dataclasses  # noqa: E402
from src.domain.recipes import queries as recipe_queries  # noqa: E402
from tests.fakes import FakePTPDevice  # noqa: E402

HERE = pathlib.Path(__file__).parent
OUT = HERE / "push_vectors.json"
RECIPES = json.loads((HERE / "recipe_ptp_vectors.json").read_text())

# Distinct so a recorded sleep identifies which setting produced it.
PUSH_SETTINGS: dict[str, object] = {
    "CAMERA_PRE_WRITE_DELAY_S": 0.011,
    "CAMERA_POST_WRITE_DELAY_S": 0.022,
    "CAMERA_POST_CURSOR_DELAY_S": 0.033,
    "CAMERA_INTER_SLOT_DELAY_S": 0.044,
    "CAMERA_POST_READ_DELAY_S": 0.055,
    "CAMERA_MAX_RETRIES": 3,
    "CAMERA_RETRY_BACKOFF_S": 0.066,
}

# name, why, recipe vector to push, device behaviour
SCENARIOS: list[tuple[str, str, str, dict[str, object]]] = [
    (
        "clean_push",
        "An everyday recipe with nothing going wrong. Pins the whole sequence: "
        "cursor, slot name, then each property with its pauses.",
        "named_white_balance",
        {},
    ),
    (
        "kelvin_push",
        "A Kelvin white balance with shifts, so the ordering rule is part of the "
        "recorded sequence rather than only of the conversion.",
        "kelvin_white_balance_with_shifts",
        {},
    ),
    (
        "monochrome_push",
        "Colour drops out and the toning axes appear, so the write count differs.",
        "monochrome_swaps_colour_for_toning",
        {},
    ),
    (
        "grain_off_push",
        "Grain written as the sentinel.",
        "grain_off_uses_the_sentinel",
        {},
    ),
    (
        "drange_priority_push",
        "D-Range Priority suppresses three properties, the shortest sequence.",
        "drange_priority_suppresses_drange_mode",
        {},
    ),
    (
        "one_property_refused",
        "The camera declines one property and stays reachable. Every later "
        "property must still be written, and the failure named at the end.",
        "named_white_balance",
        {"reject": {"FilmSimulation": 0x2005}},
    ),
    (
        "two_properties_refused",
        "Both refusals reported, in the order they were attempted.",
        "named_white_balance",
        {"reject": {"FilmSimulation": 0x2005, "Sharpness": 0x2005}},
    ),
    (
        "slot_name_refused",
        "A refused slot name is reported by name, not as a hex code.",
        "named_white_balance",
        {"reject_slot_name": 0x2005},
    ),
    (
        "camera_vanishes_midway",
        "The camera stops answering. The sequence stops rather than spending "
        "three retries each on every remaining property.",
        "named_white_balance",
        {"fail": ["FilmSimulation"]},
    ),
    (
        "cursor_refused",
        "The cursor will not move, so nothing is written at all.",
        "named_white_balance",
        {"reject_cursor": 0x2005},
    ),
    (
        "verification_clean",
        "Read-back enabled and every value stuck.",
        "named_white_balance",
        {"verify": True},
    ),
    (
        "verification_catches_drift",
        "A write reported success and did not take. Only read-back notices.",
        "named_white_balance",
        {"verify": True, "read_overrides": {"Sharpness": 999}},
    ),
    (
        "verification_skips_the_grain_sentinel",
        "Grain Off is normalised by the camera, so its read-back never matches "
        "and verifying it would fail every push with grain off.",
        "grain_off_uses_the_sentinel",
        {"verify": True},
    ),
]


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


def _codes() -> dict[str, int]:
    from src.data.camera import constants

    return dict(constants.CUSTOM_SLOT_CODES)


def _build_device(behaviour: dict[str, object]) -> _Recording:
    from src.data.camera import constants

    codes = _codes()
    reject = {codes[name]: rc for name, rc in behaviour.get("reject", {}).items()}
    if "reject_cursor" in behaviour:
        reject[constants.PROP_SLOT_CURSOR] = behaviour["reject_cursor"]
    if "reject_slot_name" in behaviour:
        reject[constants.PROP_SLOT_NAME] = behaviour["reject_slot_name"]
    errors = {
        codes[name]: ptp_device.CameraConnectionError("camera stopped answering")
        for name in behaviour.get("fail", [])
    }
    overrides = {codes[name]: v for name, v in behaviour.get("read_overrides", {}).items()}
    return _Recording(
        set_rejection_codes=reject,
        set_errors=errors,
        int_read_overrides=overrides,
    )


def _run(recipe_name: str, behaviour: dict[str, object]) -> dict[str, object]:
    fields = dict(next(v for v in RECIPES["vectors"] if v["name"] == recipe_name)["recipe"])
    fields["sensors"] = tuple(fields.get("sensors") or ())
    data = image_dataclasses.FujifilmRecipeData(**fields)

    for name, value in PUSH_SETTINGS.items():
        setattr(settings, name, value)
    settings.CAMERA_VERIFY_WRITES = bool(behaviour.get("verify", False))

    device = _build_device(behaviour)
    settings.PTP_DEVICE = lambda: device
    recipe_queries.recipe_from_db = lambda recipe: data  # type: ignore[assignment]

    sleeps: list[float] = []
    real_sleep = time.sleep
    time.sleep = lambda seconds: sleeps.append(round(seconds, 6))  # type: ignore[assignment]
    error: dict[str, object] | None = None
    try:
        push_recipe_uc.push_recipe_to_camera(None, slot_index=2)  # type: ignore[arg-type]
    except push_recipe_uc.RecipeWriteError as exc:
        error = {"type": "RecipeWriteError", "failed_properties": list(exc.failed_properties)}
    except ptp_device.CameraConnectionError as exc:
        error = {"type": "CameraConnectionError", "message": str(exc)}
    except ptp_device.CameraWriteError as exc:
        error = {"type": "CameraWriteError", "code": exc.code}
    finally:
        time.sleep = real_sleep  # type: ignore[assignment]

    return {
        "writes": device.writes,
        "sleeps": sleeps,
        "reads": device.reads,
        "error": error,
    }


def build() -> dict[str, object]:
    return {
        "comment": (
            "Golden push sequences shared by the Python and JavaScript implementations "
            "of push_recipe_to_camera. Both suites replay these, so the order of "
            "operations against the camera cannot change on one side alone. The delays "
            "are deliberately distinct so a recorded sleep says which pause it was. "
            "Regenerate with tests/fixtures/camera/generate_push_vectors.py."
        ),
        "settings": PUSH_SETTINGS,
        "slot_index": 2,
        "scenarios": [
            {"name": name, "why": why, "recipe": recipe, "device": behaviour, **_run(recipe, behaviour)}
            for name, why, recipe, behaviour in SCENARIOS
        ],
    }


if __name__ == "__main__":
    structlog.configure(processors=[lambda *a: (_ for _ in ()).throw(structlog.DropEvent)])
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {OUT}")
