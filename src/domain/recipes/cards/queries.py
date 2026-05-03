from __future__ import annotations

import json

import attrs
import piexif  # type: ignore[import-untyped]
import zxingcpp  # type: ignore[import-not-found]
from PIL import Image as PILImage

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import constants as recipe_constants
from src.domain.recipes import normalization as recipe_normalization
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


_DRP_CONTROLLED_FIELDS: frozenset[str] = frozenset({
    "dynamic_range",
    "highlight",
    "shadow",
})


def _is_applicable(recipe: models.FujifilmRecipe, field: str) -> bool:
    """
    Return False when a field is semantically inapplicable for this recipe.
    """
    is_monochromatic = recipe.film_simulation in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS
    drp_active = recipe.d_range_priority != "Off"
    if field in _COLOR_ONLY_FIELDS and is_monochromatic:
        return False
    if field in _MONOCHROME_ONLY_FIELDS and not is_monochromatic:
        return False
    if field == _GRAIN_SIZE_FIELD and recipe.grain_roughness == "Off":
        return False
    if field in _DRP_CONTROLLED_FIELDS and drp_active:
        return False
    return True


def get_recipe_as_json(*, recipe: models.FujifilmRecipe) -> str:
    """
    Return a minified JSON string encoding the recipe (used as QR payload).

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
    """
    Return display lines for the recipe card formatted per template label style.

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
    """
    No decodable QR code was found in the image.
    """

    image_path: str = ""


@attrs.frozen
class InvalidQRRecipePayloadError(Exception):
    """
    QR decoded but the content is not a valid QRFujifilmRecipe payload.

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
    """
    Raise InvalidQRRecipePayloadError if any present field has the wrong type.

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


# Prefix written by piexif before the payload when embedding recipe JSON.
_EXIF_ASCII_PREFIX = b"ASCII\x00\x00\x00"


def _decode_qr(*, image_path: str) -> str:
    try:
        with PILImage.open(image_path) as pil_img:
            results = zxingcpp.read_barcodes(pil_img)
    except OSError:
        return ""
    return results[0].text if results else ""


def _read_exif_recipe(*, image_path: str) -> str:
    """
    Read the recipe JSON embedded in the EXIF UserComment field, or return an empty string.
    """
    try:
        exif = piexif.load(image_path)
    except Exception:  # noqa: BLE001 — piexif raises bare Exception on malformed files
        return ""
    user_comment = exif.get("Exif", {}).get(piexif.ExifIFD.UserComment, b"")
    if not isinstance(user_comment, bytes) or not user_comment.startswith(_EXIF_ASCII_PREFIX):
        return ""
    return user_comment[len(_EXIF_ASCII_PREFIX):].decode("ascii", errors="replace")


def get_qr_recipe_from_image(*, image_path: str) -> card_dataclasses.QRFujifilmRecipe:
    """
    Decode the QR code embedded in a recipe-card image into a QRFujifilmRecipe.

    :raises QRCodeNotFoundError: If the file cannot be opened as an image or no
        QR code can be decoded from it.
    :raises InvalidQRRecipePayloadError: If the decoded content is not a valid
        QRFujifilmRecipe payload (bad JSON, unsupported schema version, unknown
        fields, or type mismatches).
    """
    data = _decode_qr(image_path=image_path)
    if not data:
        data = _read_exif_recipe(image_path=image_path)
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
    """
    Translate a decoded QRFujifilmRecipe into a FujifilmRecipeData.

    Inverts the formatting decisions made by get_recipe_as_json and fills in
    canonical defaults for fields that the QR payload omits:
      - Decimal fields go from int/float back to signed string ("+1", "-1.5", "0").
      - color_chrome_effect/fx_blue default to "Off" when absent.
      - sharpness/high_iso_nr/clarity default to "0" when absent.
      - highlight/shadow default to "0" when absent.
      - color/monochromatic_color_* default to "0" when absent.
      - dynamic_range defaults to "" when absent.

    Inapplicable fields are then set to None by normalize_recipe_data():
      - grain_size when grain_roughness is "Off".
      - dynamic_range/highlight/shadow when DRP is active.
      - color for mono sims; mono color fields for colour sims.
    """
    return recipe_normalization.normalize_recipe_data(
        image_dataclasses.FujifilmRecipeData(
            name=qr_recipe.name or "",
            film_simulation=qr_recipe.film_simulation,
            grain_roughness=qr_recipe.grain_roughness,
            d_range_priority=qr_recipe.d_range_priority,
            white_balance=qr_recipe.white_balance,
            white_balance_red=qr_recipe.white_balance_red,
            white_balance_blue=qr_recipe.white_balance_blue,
            color_chrome_effect=qr_recipe.color_chrome_effect or "Off",
            color_chrome_fx_blue=qr_recipe.color_chrome_fx_blue or "Off",
            sharpness=_signed_decimal_or_none(qr_recipe.sharpness) or "0",
            high_iso_nr=_signed_decimal_or_none(qr_recipe.high_iso_nr) or "0",
            clarity=_signed_decimal_or_none(qr_recipe.clarity) or "0",
            dynamic_range=qr_recipe.dynamic_range if qr_recipe.dynamic_range is not None else "",
            grain_size=qr_recipe.grain_size,
            highlight=_signed_decimal_or_none(qr_recipe.highlight) or "0",
            shadow=_signed_decimal_or_none(qr_recipe.shadow) or "0",
            color=_signed_decimal_or_none(qr_recipe.color) or "0",
            monochromatic_color_warm_cool=_signed_decimal_or_none(qr_recipe.monochromatic_color_warm_cool) or "0",
            monochromatic_color_magenta_green=_signed_decimal_or_none(qr_recipe.monochromatic_color_magenta_green) or "0",
        )
    )
