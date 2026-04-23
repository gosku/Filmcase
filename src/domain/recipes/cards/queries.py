from __future__ import annotations

import json

import attrs
import cv2
import cv2.typing

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import constants as recipe_constants
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes.cards import dataclasses as card_dataclasses
from src.domain.recipes.cards import templates as card_templates


@attrs.frozen
class FieldLine:
    label: str
    value: str


_LONG_LABELS: dict[str, str] = {
    "film_simulation": "Film Simulation",
    "dynamic_range": "Dynamic Range",
    "d_range_priority": "D-Range Priority",
    "grain_roughness": "Grain",
    "grain_size": "Grain Size",
    "color_chrome_effect": "Color Chrome",
    "color_chrome_fx_blue": "CC FX Blue",
    "white_balance": "White Balance",
    "white_balance_red": "WB Red",
    "white_balance_blue": "WB Blue",
    "highlight": "Highlight",
    "shadow": "Shadow",
    "color": "Color",
    "sharpness": "Sharpness",
    "high_iso_nr": "High ISO NR",
    "clarity": "Clarity",
    "monochromatic_color_warm_cool": "BW Warm/Cool",
    "monochromatic_color_magenta_green": "BW Mag/Green",
}

_SHORT_LABELS: dict[str, str] = {
    "film_simulation": "Film Sim",
    "dynamic_range": "DR",
    "d_range_priority": "D-Range",
    "grain_roughness": "Grain",
    "grain_size": "Grain Size",
    "color_chrome_effect": "CC",
    "color_chrome_fx_blue": "CC Blue",
    "white_balance": "WB",
    "white_balance_red": "WB Red",
    "white_balance_blue": "WB Blue",
    "highlight": "HL",
    "shadow": "SH",
    "color": "Color",
    "sharpness": "Sharp",
    "high_iso_nr": "NR",
    "clarity": "Clarity",
    "monochromatic_color_warm_cool": "BW W/C",
    "monochromatic_color_magenta_green": "BW M/G",
}

# Fields that only apply to colour (non-monochromatic) film simulations.
_COLOR_ONLY_FIELDS: frozenset[str] = frozenset({
    "color",
    "color_chrome_effect",
    "color_chrome_fx_blue",
})

# Fields that only apply to monochromatic film simulations.
_MONOCHROME_ONLY_FIELDS: frozenset[str] = frozenset({
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
})

# Fields where string value "Off" signals the paired field should be hidden.
_GRAIN_ROUGHNESS_FIELD = "grain_roughness"
_GRAIN_SIZE_FIELD = "grain_size"

# Ordered list of fields to include in card display and JSON payload.
# Order matches the recipe detail view.
_DISPLAY_FIELDS: tuple[str, ...] = (
    "film_simulation",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
    "grain_roughness",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "white_balance_red",
    "white_balance_blue",
    "dynamic_range",
    "d_range_priority",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
)


def _get_raw_value(recipe: models.FujifilmRecipe, field: str) -> object:
    return getattr(recipe, field)


def _format_value(field: str, raw: object) -> str:
    if field in recipe_queries.DECIMAL_FIELDS:
        return recipe_queries.decimal_str(raw)
    return str(raw)


def _is_applicable(recipe: models.FujifilmRecipe, field: str) -> bool:
    """Return False when a field is semantically inapplicable for this recipe."""
    is_monochromatic = recipe.film_simulation in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS
    if field in _COLOR_ONLY_FIELDS and is_monochromatic:
        return False
    if field in _MONOCHROME_ONLY_FIELDS and not is_monochromatic:
        return False
    if field == _GRAIN_SIZE_FIELD and recipe.grain_roughness == "Off":
        return False
    return True


def get_recipe_as_json(*, recipe: models.FujifilmRecipe) -> str:
    """Return a minified JSON string encoding the recipe (used as QR payload).

    Uses short snake_case keys. Fields that are None and semantically inapplicable
    for the current film simulation are omitted. Values of 0 or other defaults are
    always included. The recipe name is included only when non-empty, so nameless
    recipes produce byte-identical payloads to before this key existed.
    """
    payload: dict[str, object] = {"v": 1}
    if recipe.name:
        payload["name"] = recipe.name
    for field in _DISPLAY_FIELDS:
        if not _is_applicable(recipe, field):
            continue
        raw = _get_raw_value(recipe, field)
        if raw is None:
            continue
        if field in recipe_queries.DECIMAL_FIELDS:
            payload[field] = float(raw) if float(raw) != int(float(raw)) else int(float(raw))  # type: ignore[arg-type]
        else:
            payload[field] = raw
    return json.dumps(payload, separators=(",", ":"))


def get_recipe_cover_lines(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
) -> tuple[FieldLine, ...]:
    """Return display lines for the recipe card formatted per template label style.

    Inapplicable fields (same rules as get_recipe_as_json) and null values are omitted.
    """
    labels = _LONG_LABELS if template.label_style == "long" else _SHORT_LABELS
    lines: list[FieldLine] = []
    for field in _DISPLAY_FIELDS:
        if not _is_applicable(recipe, field):
            continue
        raw = _get_raw_value(recipe, field)
        if raw is None:
            continue
        value = _format_value(field, raw)
        lines.append(FieldLine(label=labels[field], value=value))
    return tuple(lines)


@attrs.frozen
class QRCodeNotFoundError(Exception):
    """No decodable QR code was found in the image."""

    image_path: str = ""


@attrs.frozen
class InvalidQRRecipePayloadError(Exception):
    """QR decoded but the content is not a valid QRFujifilmRecipe payload.

    ``reason`` is one of:
      - ``"invalid_json"`` — decoded string is not valid JSON.
      - ``"unsupported_version"`` — ``v`` field is missing or != 1.
      - ``"unknown_fields"`` — payload contains keys outside the known schema.
      - ``"type_mismatch"`` — a field's value has the wrong type, or a
        required field is missing.
    """

    image_path: str = ""
    reason: str = ""


_SUPPORTED_QR_SCHEMA_VERSION = 1

_QR_STR_FIELDS: frozenset[str] = frozenset({
    "film_simulation",
    "grain_roughness",
    "d_range_priority",
    "white_balance",
    "name",
    "dynamic_range",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
})
_QR_INT_FIELDS: frozenset[str] = frozenset({
    "white_balance_red",
    "white_balance_blue",
})
_QR_DECIMAL_FIELDS: frozenset[str] = frozenset({
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
})
_QR_KNOWN_KEYS: frozenset[str] = (
    frozenset({"v"}) | _QR_STR_FIELDS | _QR_INT_FIELDS | _QR_DECIMAL_FIELDS
)


def _check_payload_types(payload: dict[str, object], *, image_path: str) -> None:
    """Raise InvalidQRRecipePayloadError if any present field has the wrong type.

    ``bool`` is explicitly rejected for int/decimal fields because Python treats
    ``bool`` as a subclass of ``int``, which would otherwise let ``true``/``false``
    slip through.
    """
    for key, value in payload.items():
        if key == "v":
            continue
        if key in _QR_STR_FIELDS and not isinstance(value, str):
            raise InvalidQRRecipePayloadError(image_path=image_path, reason="type_mismatch")
        if key in _QR_INT_FIELDS and (isinstance(value, bool) or not isinstance(value, int)):
            raise InvalidQRRecipePayloadError(image_path=image_path, reason="type_mismatch")
        if key in _QR_DECIMAL_FIELDS and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise InvalidQRRecipePayloadError(image_path=image_path, reason="type_mismatch")


# The QR on a 1080-px recipe card is only 200 px wide — small enough that
# cv2.QRCodeDetector.detectAndDecode() routinely fails to decode it in one pass.
# Running detect() first to locate the QR, then cropping + upscaling that region
# for decoding is reliable across both templates.
_QR_CROP_PADDING_PX = 20
_QR_DECODE_UPSCALE = 3


def _decode_qr(img: cv2.typing.MatLike) -> str:
    detector = cv2.QRCodeDetector()
    data, _bbox, _rectified = detector.detectAndDecode(img)
    if data:
        return str(data)

    retval, pts = detector.detect(img)
    if not retval or pts is None:
        return ""

    pts_int = pts.reshape(-1, 2).astype(int)
    x0 = max(0, int(pts_int[:, 0].min()) - _QR_CROP_PADDING_PX)
    y0 = max(0, int(pts_int[:, 1].min()) - _QR_CROP_PADDING_PX)
    h, w = img.shape[:2]
    x1 = min(w, int(pts_int[:, 0].max()) + _QR_CROP_PADDING_PX)
    y1 = min(h, int(pts_int[:, 1].max()) + _QR_CROP_PADDING_PX)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return ""
    upscaled = cv2.resize(
        crop,
        (crop.shape[1] * _QR_DECODE_UPSCALE, crop.shape[0] * _QR_DECODE_UPSCALE),
        interpolation=cv2.INTER_CUBIC,
    )
    data, _bbox, _rectified = detector.detectAndDecode(upscaled)
    return str(data)


def get_qr_recipe_from_image(*, image_path: str) -> card_dataclasses.QRFujifilmRecipe:
    """Decode the QR code embedded in a recipe-card image into a QRFujifilmRecipe.

    :raises QRCodeNotFoundError: If the file cannot be opened as an image or no
        QR code can be decoded from it.
    :raises InvalidQRRecipePayloadError: If the decoded content is not a valid
        QRFujifilmRecipe payload (bad JSON, unsupported schema version, unknown
        fields, or type mismatches).
    """
    img = cv2.imread(image_path)
    if img is None:
        raise QRCodeNotFoundError(image_path=image_path)

    data = _decode_qr(img)
    if not data:
        raise QRCodeNotFoundError(image_path=image_path)

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        raise InvalidQRRecipePayloadError(image_path=image_path, reason="invalid_json")
    if not isinstance(payload, dict):
        raise InvalidQRRecipePayloadError(image_path=image_path, reason="invalid_json")

    version = payload.get("v")
    if not isinstance(version, int) or isinstance(version, bool) or version != _SUPPORTED_QR_SCHEMA_VERSION:
        raise InvalidQRRecipePayloadError(image_path=image_path, reason="unsupported_version")

    unknown = set(payload.keys()) - _QR_KNOWN_KEYS
    if unknown:
        raise InvalidQRRecipePayloadError(image_path=image_path, reason="unknown_fields")

    _check_payload_types(payload, image_path=image_path)

    try:
        return card_dataclasses.QRFujifilmRecipe(**payload)
    except TypeError:
        # A required field is missing, or attrs rejected a value. Either way
        # the payload does not match the schema.
        raise InvalidQRRecipePayloadError(image_path=image_path, reason="type_mismatch")


def _signed_decimal_or_none(value: int | float | None) -> str | None:
    return None if value is None else recipe_queries.decimal_str(value)


def get_recipe_data_from_qr_recipe(
    *, qr_recipe: card_dataclasses.QRFujifilmRecipe,
) -> image_dataclasses.FujifilmRecipeData:
    """Translate a decoded QRFujifilmRecipe into a FujifilmRecipeData.

    Inverts the formatting decisions made by get_recipe_as_json:
      - Decimal fields go from int/float back to signed string ("+1", "-1.5",
        "0"), which is the form FujifilmRecipeData and the downstream
        get_or_create pipeline expect.
      - grain_size defaults to "Off" when absent and grain_roughness is "Off",
        matching the create-side default.
      - color_chrome_effect / color_chrome_fx_blue default to "" when absent
        (omitted for monochromatic simulations), matching how those fields
        are stored for monochrome recipes.
      - The recipe name is passed through when the payload includes it, and
        defaults to "" (FujifilmRecipeData's default) when absent.
    """
    grain_size = qr_recipe.grain_size
    if grain_size is None and qr_recipe.grain_roughness == "Off":
        grain_size = "Off"

    # sharpness / high_iso_nr / clarity are typed `str` on FujifilmRecipeData
    # because every existing producer (EXIF, DB) fills them. The QR payload
    # omits them when the DB value is NULL; downstream _parse_numeric handles
    # None, and attrs.frozen does not enforce types at runtime.
    return image_dataclasses.FujifilmRecipeData(
        name=qr_recipe.name or "",
        film_simulation=qr_recipe.film_simulation,
        grain_roughness=qr_recipe.grain_roughness,
        d_range_priority=qr_recipe.d_range_priority,
        white_balance=qr_recipe.white_balance,
        white_balance_red=qr_recipe.white_balance_red,
        white_balance_blue=qr_recipe.white_balance_blue,
        color_chrome_effect=qr_recipe.color_chrome_effect or "",
        color_chrome_fx_blue=qr_recipe.color_chrome_fx_blue or "",
        sharpness=_signed_decimal_or_none(qr_recipe.sharpness),  # type: ignore[arg-type]
        high_iso_nr=_signed_decimal_or_none(qr_recipe.high_iso_nr),  # type: ignore[arg-type]
        clarity=_signed_decimal_or_none(qr_recipe.clarity),  # type: ignore[arg-type]
        dynamic_range=qr_recipe.dynamic_range,
        grain_size=grain_size,
        highlight=_signed_decimal_or_none(qr_recipe.highlight),
        shadow=_signed_decimal_or_none(qr_recipe.shadow),
        color=_signed_decimal_or_none(qr_recipe.color),
        monochromatic_color_warm_cool=_signed_decimal_or_none(qr_recipe.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_signed_decimal_or_none(qr_recipe.monochromatic_color_magenta_green),
    )
