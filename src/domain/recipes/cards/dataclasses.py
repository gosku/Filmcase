from __future__ import annotations

from collections.abc import Iterable

import attrs


def _sensors_to_tuple(value: Iterable[str] | None) -> tuple[str, ...] | None:
    """
    Normalise the decoded ``sensors`` payload to an immutable tuple.

    JSON arrays decode to ``list``; this converter coerces to ``tuple`` so the
    dataclass stays fully immutable. ``None`` (absent in v=1 payloads) is
    passed through.
    """
    return None if value is None else tuple(value)


@attrs.frozen
class QRFujifilmRecipe:
    """
    Parsed recipe payload decoded from a recipe-card QR code.

    Mirrors the JSON payload produced by
    :func:`src.domain.recipes.cards.queries.get_recipe_as_json`. Field names
    match the payload keys exactly (long snake_case); decimal fields are
    typed ``int | float`` because the payload emits whole numbers as ``int``
    and half-step values as ``float``. Fields that the producer omits for
    the current film simulation (colour-only vs monochrome-only, plus
    ``grain_size`` when ``grain_roughness == "Off"``) are represented as
    ``None``.
    """

    v: int
    film_simulation: str
    grain_roughness: str
    d_range_priority: str
    white_balance: str
    white_balance_red: int
    white_balance_blue: int
    name: str | None = None
    dynamic_range: str | None = None
    grain_size: str | None = None
    color_chrome_effect: str | None = None
    color_chrome_fx_blue: str | None = None
    highlight: int | float | None = None
    shadow: int | float | None = None
    color: int | float | None = None
    sharpness: int | float | None = None
    high_iso_nr: int | float | None = None
    clarity: int | float | None = None
    monochromatic_color_warm_cool: int | float | None = None
    monochromatic_color_magenta_green: int | float | None = None
    # Introduced in payload schema v=2; see _sensors_to_tuple for the
    # list-to-tuple normalisation rationale.
    sensors: tuple[str, ...] | None = attrs.field(
        default=None,
        converter=_sensors_to_tuple,
    )
