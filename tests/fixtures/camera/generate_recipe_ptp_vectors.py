"""
Regenerate recipe_ptp_vectors.json, the golden vectors shared by the Python and
JavaScript implementations of recipe -> PTP value conversion.

    FILMCASE_ENV_FILE=/dev/null .venv/bin/python tests/fixtures/camera/generate_recipe_ptp_vectors.py

Regenerate deliberately, never to make a failing test pass. A diff in the output
means the bytes sent to the camera changed, so read it before committing it: the
values in the current file were checked by hand against docs/ptp_encodings.md.

Each case overrides only the fields it is about, so a diff stays readable and a
new case is a few lines.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.config.settings")

import django  # noqa: E402

django.setup()

import attrs  # noqa: E402

from src.domain.camera import queries as camera_queries  # noqa: E402
from src.domain.camera import validation as camera_validation  # noqa: E402
from src.domain.images import dataclasses as image_dataclasses  # noqa: E402
from src.domain.recipes import normalization  # noqa: E402

OUT = pathlib.Path(__file__).with_name("recipe_ptp_vectors.json")

# A plausible everyday recipe. Each case overrides only what it is about.
BASE: dict[str, object] = dict(
    name="Base Recipe",
    film_simulation="Classic Chrome",
    d_range_priority="Off",
    dynamic_range="DR200",
    grain_roughness="Weak",
    grain_size="Small",
    color_chrome_effect="Strong",
    color_chrome_fx_blue="Weak",
    white_balance="Daylight",
    white_balance_red=0,
    white_balance_blue=0,
    sharpness="0",
    high_iso_nr="0",
    clarity="0",
    highlight="0",
    shadow="0",
    color="0",
)

CASES: list[tuple[str, str, dict[str, object]]] = [
    (
        "named_white_balance",
        "An everyday recipe with a named white balance and no Kelvin value.",
        {},
    ),
    (
        "kelvin_white_balance_with_shifts",
        "Kelvin WB with red and blue shifts. Pins the ordering rule: "
        "WhiteBalanceColorTemperature must be written before the two shifts, or the "
        "camera zeroes them when the temperature lands.",
        {"white_balance": "6500K", "white_balance_red": -2, "white_balance_blue": 3},
    ),
    (
        "grain_off_uses_the_sentinel",
        "Grain Off is written as the sentinel, not as the value the read table would "
        "invert to, because the camera picks the size it last remembered.",
        {"grain_roughness": "Off", "grain_size": None},
    ),
    (
        "grain_strong_large",
        "The other end of the grain table.",
        {"grain_roughness": "Strong", "grain_size": "Large"},
    ),
    (
        "drange_priority_suppresses_drange_mode",
        "With D-Range Priority active the camera owns the tone curve, so DRangeMode, "
        "HighLightTone and ShadowTone are not written at all.",
        {"d_range_priority": "Strong", "dynamic_range": "DR400"},
    ),
    (
        "drange_mode_written_when_priority_off",
        "With priority off, DRangeMode carries the dynamic range.",
        {"d_range_priority": "Off", "dynamic_range": "DR400"},
    ),
    (
        "monochrome_swaps_colour_for_toning",
        "A monochrome simulation drops ColorMode and gains the two toning axes.",
        {
            "film_simulation": "Acros STD",
            "color": None,
            "monochromatic_color_warm_cool": "+3",
            "monochromatic_color_magenta_green": "-2",
        },
    ),
    (
        "half_step_tone_curves",
        "Highlight and shadow allow half steps, so they scale with round() rather "
        "than truncation.",
        {"highlight": "+1.5", "shadow": "-1.5"},
    ),
    (
        "noise_reduction_maximum",
        "The NR table is non-linear; this is its top entry.",
        {"high_iso_nr": "+4"},
    ),
    (
        "noise_reduction_minimum",
        "The NR table is non-linear; this is its bottom entry.",
        {"high_iso_nr": "-4"},
    ),
    (
        "negative_scaled_fields",
        "Negative values go on the wire as int32 two's complement and read back "
        "masked to 16 bits.",
        {"color": "-4", "sharpness": "-4", "clarity": "-5", "highlight": "-2"},
    ),
    (
        "extremes_of_the_shift_range",
        "White balance shifts pass through unscaled.",
        {"white_balance": "2500K", "white_balance_red": -9, "white_balance_blue": 9},
    ),
]


# Cases for the accept/reject table both validators must agree on. Only the
# overrides are listed; each is applied to BASE. The point is the fields a port
# is most likely to get wrong: "1.5" where an integer is required, an empty
# string where a decimal is, and the grain rules, which cannot be read off the
# encoding table.
VALIDATION_CASES: list[tuple[str, dict[str, object]]] = [
    ("baseline", {}),
    ("blank_name", {"name": ""}),
    ("whitespace_name", {"name": "   "}),
    ("unknown_film_simulation", {"film_simulation": "Velvia 100F"}),
    ("kelvin_white_balance", {"white_balance": "6500K"}),
    ("kelvin_without_the_k", {"white_balance": "6500"}),
    ("non_numeric_kelvin", {"white_balance": "warmK"}),
    ("unknown_white_balance", {"white_balance": "Tungsten"}),
    ("dynamic_range_absent", {"dynamic_range": None}),
    ("dynamic_range_empty", {"dynamic_range": ""}),
    ("dynamic_range_na", {"dynamic_range": "N/A"}),
    ("dynamic_range_unknown", {"dynamic_range": "DR800"}),
    ("drange_priority_empty", {"d_range_priority": ""}),
    ("drange_priority_na", {"d_range_priority": "N/A"}),
    ("drange_priority_unknown", {"d_range_priority": "Maximum"}),
    ("grain_off_without_size", {"grain_roughness": "Off", "grain_size": None}),
    ("grain_off_size_off", {"grain_roughness": "Off", "grain_size": "Off"}),
    ("grain_off_size_large", {"grain_roughness": "Off", "grain_size": "Large"}),
    ("grain_on_without_size", {"grain_roughness": "Weak", "grain_size": None}),
    ("grain_on_empty_size", {"grain_roughness": "Weak", "grain_size": ""}),
    ("grain_on_size_off", {"grain_roughness": "Strong", "grain_size": "Off"}),
    ("grain_unknown_roughness", {"grain_roughness": "Heavy", "grain_size": "Large"}),
    ("colour_chrome_empty", {"color_chrome_effect": ""}),
    ("colour_chrome_na", {"color_chrome_effect": "N/A"}),
    ("colour_chrome_unknown", {"color_chrome_effect": "Vivid"}),
    ("colour_chrome_fx_unknown", {"color_chrome_fx_blue": "Vivid"}),
    ("noise_reduction_top", {"high_iso_nr": "4"}),
    ("noise_reduction_bottom", {"high_iso_nr": "-4"}),
    ("noise_reduction_off_table", {"high_iso_nr": "5"}),
    ("noise_reduction_half_step", {"high_iso_nr": "1.5"}),
    ("noise_reduction_empty", {"high_iso_nr": ""}),
    ("noise_reduction_na", {"high_iso_nr": "N/A"}),
    ("colour_half_step", {"color": "1.5"}),
    ("colour_text", {"color": "high"}),
    ("colour_signed", {"color": "+2"}),
    ("colour_empty", {"color": ""}),
    ("colour_na", {"color": "N/A"}),
    ("sharpness_half_step", {"sharpness": "1.5"}),
    ("clarity_half_step", {"clarity": "-2.5"}),
    ("clarity_surrounded_by_spaces", {"clarity": " 2 "}),
    ("highlight_half_step", {"highlight": "+1.5"}),
    ("highlight_text", {"highlight": "bright"}),
    ("highlight_empty", {"highlight": ""}),
    ("highlight_absent", {"highlight": None}),
    ("shadow_half_step", {"shadow": "-1.5"}),
    ("mono_warm_cool", {"monochromatic_color_warm_cool": "+3"}),
    ("mono_magenta_green_text", {"monochromatic_color_magenta_green": "green"}),
]


def _validation_outcome(fields: dict[str, object]) -> str:
    """Return "ok" or "reject:<field>" for one case."""
    # The attrs name validator is bypassed so both sides exercise the same
    # function: the browser receives plain JSON and has no constructor checks,
    # so validate_recipe_for_camera is the only thing standing between a bad
    # name and the camera there.
    recipe = image_dataclasses.FujifilmRecipeData(**{**fields, "name": "placeholder"})
    object.__setattr__(recipe, "name", fields["name"])
    try:
        camera_validation.validate_recipe_for_camera(recipe)
    except camera_validation.RecipeValidationError as error:
        return f"reject:{error.field}"
    return "ok"


def build() -> dict[str, object]:
    vectors = []
    for name, why, overrides in CASES:
        fields = {**BASE, **overrides}
        recipe = image_dataclasses.FujifilmRecipeData(**fields)  # type: ignore[arg-type]
        # Normalized, because that is what the payload endpoint serves and
        # therefore what the client's conversion actually receives.
        recipe = normalization.normalize_recipe_data(recipe)
        items = camera_queries.recipe_to_ptp_values(recipe).items()
        vectors.append(
            {
                "name": name,
                "why": why,
                "recipe": json.loads(json.dumps(attrs.asdict(recipe))),
                "expected_items": [[code, value] for code, value in items],
            }
        )
    return {
        "comment": (
            "Golden vectors shared by the Python and JavaScript implementations of "
            "recipe -> PTP value conversion. Both suites assert against this file, so "
            "the two ports cannot drift apart silently. Regenerate with "
            "tests/fixtures/camera/generate_recipe_ptp_vectors.py, deliberately, never "
            "to make a failing test pass: a diff here means the wire format changed."
        ),
        "encodings": json.loads(
            json.dumps(attrs.asdict(camera_queries.client_camera_encodings()))
        ),
        "vectors": vectors,
        "validation_vectors": [
            {
                "name": name,
                "overrides": json.loads(json.dumps(overrides)),
                "expected": _validation_outcome({**BASE, **overrides}),
            }
            for name, overrides in VALIDATION_CASES
        ],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {OUT}")
