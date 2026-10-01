"""
Recipe similarity metric (ADR 019).

Two recipes are compared field by field, each field yielding a distance in
``[0, 1]``. The distances are combined in two rounds: an *identity* score from
the fields that define the look, and an *extras* score from the modulator and
effect fields, combined as ``identity * (A + B * extras)`` so identity sets the
ceiling. The result is a similarity in ``[0, 1]`` where ``1.0`` means identical.

The module exposes both a pure-Python reference (`compute_similarity`, used as a
test oracle and for one-off pairs) and a database-side annotation
(`annotate_similarity`) that both public queries share so the heavy lifting
happens in Postgres rather than in Python.

All numeric values here are the starting constants documented in ADR 019.
"""

from __future__ import annotations

import functools
import math
import operator
import re
from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING

import attrs
from django.db.models import Case, F, FloatField, Q, Value, When
from django.db.models.expressions import Combinable, ExpressionWrapper
from django.db.models.functions import Abs, Cast, Sqrt

from src.data import models
from src.domain.recipes.constants import MONOCHROMATIC_FILM_SIMULATIONS

if TYPE_CHECKING:
    from django.db.models import QuerySet


# ---------------------------------------------------------------------------
# Round weights and the identity/extras split (ADR 019 section 6)
# ---------------------------------------------------------------------------

# Identity is the ceiling; extras can only move the score within the band it
# allows: final = identity * (A + B * extras), with A + B = 1. These are the
# defaults; live callers pass the runtime-tunable django-constance values
# (RECIPE_SIMILARITY_IDENTITY_WEIGHT / _EXTRAS_WEIGHT) so tests and the pure
# oracle stay database-free while production honours the settings.
A: float = 0.7
B: float = 0.3

FILM_SIM_WEIGHT: float = 2.0        # film_simulation counts double other identity fields
IDENTITY_FIELD_WEIGHT: float = 1.0
MODULATOR_WEIGHT: float = 2.0       # each modulator counts double each effect
EFFECT_WEIGHT: float = 1.0

# Distance used for a field that cannot be compared across the colour/B&W
# boundary (see the mixed-regime rule in ADR 019 section 5).
MAXED_DISTANCE: float = 1.0


# ---------------------------------------------------------------------------
# Per-field numeric spans (full defined range of each setting)
# ---------------------------------------------------------------------------

HIGHLIGHT_SPAN: float = 6.0     # -2.0 .. +4.0
SHADOW_SPAN: float = 6.0        # -2.0 .. +4.0
COLOR_SPAN: float = 8.0         # -4 .. +4
SHARPNESS_SPAN: float = 8.0     # -4 .. +4
NOISE_REDUCTION_SPAN: float = 8.0   # -4 .. +4
CLARITY_SPAN: float = 10.0      # -5 .. +5
MONOCHROMATIC_SPAN: float = 36.0    # -18 .. +18

# White balance red/blue shift: a 2D point in [-9, +9]^2, normalized by the
# longest possible difference vector.
WB_SHIFT_SPAN: float = math.hypot(18.0, 18.0)


# ---------------------------------------------------------------------------
# Ordered categorical ladders (ADR 019 section 4.2)
# ---------------------------------------------------------------------------

# The empty string is DR left unset because D-Range Priority is active; it is
# skipped, never placed on the ladder. DR800 is not a recipe parameter (the
# camera reaches it only by constraining other settings), so it is not modelled.
DR_LADDER: dict[str, float] = {
    "DR100": 0.0,
    "DR-Auto": 0.5,
    "DR200": 1.0,
    "DR400": 2.0,
}
DR_SPAN: float = 2.0

DRP_LADDER: dict[str, float] = {"Off": 0.0, "Weak": 1.0, "Auto": 1.5, "Strong": 2.0}
DRP_SPAN: float = 2.0

# Off / Weak / Strong, shared by colour-chrome effect, colour-chrome FX blue and
# grain roughness.
TRISTATE_LADDER: dict[str, float] = {"Off": 0.0, "Weak": 1.0, "Strong": 2.0}
TRISTATE_SPAN: float = 2.0

GRAIN_SIZE_LADDER: dict[str, float] = {"Off": 0.0, "Small": 1.0, "Large": 2.0}
# Grain is one 2D field (roughness, size), Off = (0, 0).
GRAIN_SPAN: float = math.hypot(2.0, 2.0)


# ---------------------------------------------------------------------------
# White balance (ADR 019 section 4.3)
# ---------------------------------------------------------------------------

# Nominal colour temperature for the temperature-bearing presets.
WB_NOMINAL_KELVIN: dict[str, int] = {
    "Incandescent": 3200,
    "Daylight": 5500,
    "Daylight Fluorescent": 6500,
}
# Scene-adaptive modes with no fixed temperature.
WB_CATEGORICAL: frozenset[str] = frozenset({"Auto", "Auto (white priority)"})
# Fuji's Kelvin range 2500..10000K spans 400..100 mired.
MIRED_SPAN: float = 300.0
# Penalty for Auto vs any temperature mode (or two different Auto modes).
WB_AUTO_PENALTY: float = 0.5

_KELVIN_RE = re.compile(r"^(\d+)K$")


# ---------------------------------------------------------------------------
# Film simulation feature space (ADR 019 section 4.5)
# ---------------------------------------------------------------------------

# Raw 1-based cell indices from Fujifilm's per-sim charts:
# (color, highlight, shadow, characteristics). Color is None for B&W sims.
_FILM_SIM_AXIS_MAX: tuple[int, int, int, int] = (14, 10, 10, 5)
_FILM_SIM_RAW: dict[str, tuple[int | None, int, int, int]] = {
    "Provia": (8, 6, 6, 1),
    "Velvia": (11, 10, 10, 4),
    "Astia": (7, 5, 7, 2),
    "Classic Chrome": (5, 7, 9, 4),
    "Classic Negative": (4, 10, 7, 5),
    "Nostalgic Negative": (6, 4, 4, 5),
    "Reala Ace": (7, 8, 5, 3),
    "Eterna": (5, 2, 2, 1),
    "Eterna Bleach Bypass": (1, 10, 7, 5),
    "Pro Neg. Hi": (7, 9, 9, 1),
    "Pro Neg. Std": (6, 6, 4, 1),
    "Acros STD": (None, 8, 8, 1),
    "Acros Yellow": (None, 8, 8, 2),
    "Acros Red": (None, 8, 8, 2),
    "Acros Green": (None, 8, 8, 3),
    "Monochrome STD": (None, 6, 6, 1),
    "Monochrome Yellow": (None, 6, 6, 2),
    "Monochrome Red": (None, 6, 6, 2),
    "Monochrome Green": (None, 6, 6, 3),
    "Sepia": (None, 6, 6, 1),
}

# Weight of each Fujifilm axis in the film-sim distance.
FILM_SIM_AXIS_WEIGHT: float = 1.0
# The binary colour/B&W axis, added only when comparing a colour sim to a B&W
# one. Heavy, so switching regime is on its own a large jump.
FILM_SIM_MONO_AXIS_WEIGHT: float = 3.0
# Sepia's warm toning is on none of the four axes, so it would otherwise be
# identical to Monochrome STD. A small dedicated toning axis, present only for
# pairs involving Sepia, separates it from the neutral B&W sims.
SEPIA_TONING_VALUE: float = 0.2
SEPIA_TONING_WEIGHT: float = 1.0
_SEPIA: str = "Sepia"


def _normalized_axis(index: int, axis_max: int) -> float:
    """Map a 1-based cell index to a position in ``[0, 1]``."""
    return (index - 1) / (axis_max - 1)


def _is_monochrome(film_simulation: str) -> bool:
    return film_simulation in MONOCHROMATIC_FILM_SIMULATIONS


def film_simulation_distance(a: str, b: str) -> float:
    """
    Return the ``[0, 1]`` distance between two film simulations.

    Colour vs colour uses all four Fujifilm axes; B&W vs B&W drops the Color
    axis; colour vs B&W drops Color and adds the heavy binary monochrome axis.
    Sepia carries a small extra toning axis so it is not coincident with the
    neutral B&W sims.
    """
    raw_a = _FILM_SIM_RAW[a]
    raw_b = _FILM_SIM_RAW[b]
    mono_a = _is_monochrome(a)
    mono_b = _is_monochrome(b)

    # (difference, weight) pairs feeding the weighted Euclidean distance.
    terms: list[tuple[float, float]] = []

    # Color axis only when both are colour sims.
    if not mono_a and not mono_b:
        color_a = raw_a[0]
        color_b = raw_b[0]
        assert color_a is not None and color_b is not None
        terms.append((
            _normalized_axis(color_a, _FILM_SIM_AXIS_MAX[0])
            - _normalized_axis(color_b, _FILM_SIM_AXIS_MAX[0]),
            FILM_SIM_AXIS_WEIGHT,
        ))

    # Highlight, Shadow, Characteristics always apply (never None for any sim).
    for axis in (1, 2, 3):
        index_a = raw_a[axis]
        index_b = raw_b[axis]
        assert index_a is not None and index_b is not None
        terms.append((
            _normalized_axis(index_a, _FILM_SIM_AXIS_MAX[axis])
            - _normalized_axis(index_b, _FILM_SIM_AXIS_MAX[axis]),
            FILM_SIM_AXIS_WEIGHT,
        ))

    # Binary monochrome axis only when one sim is colour and the other B&W.
    if mono_a != mono_b:
        terms.append((1.0, FILM_SIM_MONO_AXIS_WEIGHT))

    # Sepia toning axis only for pairs involving Sepia.
    if a == _SEPIA or b == _SEPIA:
        toning_a = SEPIA_TONING_VALUE if a == _SEPIA else 0.0
        toning_b = SEPIA_TONING_VALUE if b == _SEPIA else 0.0
        terms.append((toning_a - toning_b, SEPIA_TONING_WEIGHT))

    numerator = sum(weight * diff * diff for diff, weight in terms)
    denominator = sum(weight for _, weight in terms)
    return math.sqrt(numerator) / math.sqrt(denominator)


def _parse_white_balance(value: str) -> tuple[str, float]:
    """
    Classify a stored white balance value.

    Returns ``("temp", kelvin)`` for a temperature-bearing mode or explicit
    Kelvin string, or ``("categorical", 0.0)`` for a scene-adaptive Auto mode.
    Unknown values are treated as categorical so they fall back to the penalty.
    """
    match = _KELVIN_RE.match(value)
    if match is not None:
        return "temp", float(match.group(1))
    if value in WB_NOMINAL_KELVIN:
        return "temp", float(WB_NOMINAL_KELVIN[value])
    return "categorical", 0.0


def white_balance_distance(a: str, b: str) -> float:
    """
    Return the ``[0, 1]`` distance between two white balance modes.

    Two temperature modes are compared in mired space; anything involving an
    Auto mode falls back to a fixed penalty, and identical modes are 0.
    """
    kind_a, kelvin_a = _parse_white_balance(a)
    kind_b, kelvin_b = _parse_white_balance(b)
    if kind_a == "temp" and kind_b == "temp":
        mired_a = 1_000_000.0 / kelvin_a
        mired_b = 1_000_000.0 / kelvin_b
        return min(1.0, abs(mired_a - mired_b) / MIRED_SPAN)
    if a == b:
        return 0.0
    return WB_AUTO_PENALTY


# ---------------------------------------------------------------------------
# Pure-Python reference implementation (test oracle / one-off pairs)
# ---------------------------------------------------------------------------

def _numeric_distance(a: Decimal | float | None, b: Decimal | float | None, span: float) -> float | None:
    """Scaled absolute difference, or None when either value is absent."""
    if a is None or b is None:
        return None
    return abs(float(a) - float(b)) / span


def _accumulate(
    contributions: list[tuple[float, float]],
    distance: float | None,
    weight: float,
) -> None:
    """Record a (weight*distance, weight) pair, skipping absent fields."""
    if distance is None:
        return
    contributions.append((weight * distance, weight))


def _score(contributions: list[tuple[float, float]]) -> float:
    numerator = sum(num for num, _ in contributions)
    denominator = sum(weight for _, weight in contributions)
    return 1.0 - numerator / denominator


@attrs.frozen
class SimilarityBreakdown:
    """
    The similarity score and the two round scores it is built from.

    ``similarity`` is ``identity_score * (identity_weight + extras_weight *
    extras_score)``. The round scores are exposed so callers can show how
    identity and extras each contributed (the graph comparison panel does).
    """

    similarity: float
    identity_score: float
    extras_score: float


def compute_similarity_breakdown(
    *,
    a: models.FujifilmRecipe,
    b: models.FujifilmRecipe,
    identity_weight: float = A,
    extras_weight: float = B,
) -> SimilarityBreakdown:
    """
    Return the similarity between two recipes with its identity/extras rounds.

    This is the reference implementation. `annotate_similarity` computes the
    same value in the database; the two are cross-checked in the tests.
    """
    identity: list[tuple[float, float]] = []
    _accumulate(identity, film_simulation_distance(a.film_simulation, b.film_simulation), FILM_SIM_WEIGHT)
    _accumulate(identity, white_balance_distance(a.white_balance, b.white_balance), IDENTITY_FIELD_WEIGHT)
    wb_shift = math.hypot(
        a.white_balance_red - b.white_balance_red,
        a.white_balance_blue - b.white_balance_blue,
    ) / WB_SHIFT_SPAN
    _accumulate(identity, wb_shift, IDENTITY_FIELD_WEIGHT)
    _accumulate(identity, _numeric_distance(a.highlight, b.highlight, HIGHLIGHT_SPAN), IDENTITY_FIELD_WEIGHT)
    _accumulate(identity, _numeric_distance(a.shadow, b.shadow, SHADOW_SPAN), IDENTITY_FIELD_WEIGHT)

    mono_a = _is_monochrome(a.film_simulation)
    mono_b = _is_monochrome(b.film_simulation)
    if not mono_a and not mono_b:
        _accumulate(identity, _numeric_distance(a.color, b.color, COLOR_SPAN), IDENTITY_FIELD_WEIGHT)
    elif mono_a and mono_b:
        _accumulate(
            identity,
            _numeric_distance(a.monochromatic_color_warm_cool, b.monochromatic_color_warm_cool, MONOCHROMATIC_SPAN),
            IDENTITY_FIELD_WEIGHT,
        )
        _accumulate(
            identity,
            _numeric_distance(a.monochromatic_color_magenta_green, b.monochromatic_color_magenta_green, MONOCHROMATIC_SPAN),
            IDENTITY_FIELD_WEIGHT,
        )
    else:
        # Colour vs B&W: the chroma/toning fields cannot be compared, so each is
        # a maximal difference registering the colour/B&W mismatch directly.
        _accumulate(identity, MAXED_DISTANCE, IDENTITY_FIELD_WEIGHT)
        _accumulate(identity, MAXED_DISTANCE, IDENTITY_FIELD_WEIGHT)
        _accumulate(identity, MAXED_DISTANCE, IDENTITY_FIELD_WEIGHT)
    identity_score = _score(identity)

    extras: list[tuple[float, float]] = []
    if a.dynamic_range and b.dynamic_range:
        dr = abs(DR_LADDER[a.dynamic_range] - DR_LADDER[b.dynamic_range]) / DR_SPAN
        _accumulate(extras, dr, MODULATOR_WEIGHT)
    drp = abs(DRP_LADDER[a.d_range_priority] - DRP_LADDER[b.d_range_priority]) / DRP_SPAN
    _accumulate(extras, drp, MODULATOR_WEIGHT)
    for field in ("color_chrome_effect", "color_chrome_fx_blue"):
        tri = abs(TRISTATE_LADDER[getattr(a, field)] - TRISTATE_LADDER[getattr(b, field)]) / TRISTATE_SPAN
        _accumulate(extras, tri, MODULATOR_WEIGHT)
    _accumulate(extras, _numeric_distance(a.clarity, b.clarity, CLARITY_SPAN), MODULATOR_WEIGHT)
    _accumulate(extras, _numeric_distance(a.sharpness, b.sharpness, SHARPNESS_SPAN), EFFECT_WEIGHT)
    _accumulate(extras, _numeric_distance(a.high_iso_nr, b.high_iso_nr, NOISE_REDUCTION_SPAN), EFFECT_WEIGHT)
    grain = math.hypot(
        TRISTATE_LADDER[a.grain_roughness] - TRISTATE_LADDER[b.grain_roughness],
        GRAIN_SIZE_LADDER[a.grain_size] - GRAIN_SIZE_LADDER[b.grain_size],
    ) / GRAIN_SPAN
    _accumulate(extras, grain, EFFECT_WEIGHT)
    extras_score = _score(extras)

    similarity = identity_score * (identity_weight + extras_weight * extras_score)
    return SimilarityBreakdown(
        similarity=similarity,
        identity_score=identity_score,
        extras_score=extras_score,
    )


def compute_similarity(
    *,
    a: models.FujifilmRecipe,
    b: models.FujifilmRecipe,
    identity_weight: float = A,
    extras_weight: float = B,
) -> float:
    """
    Return the similarity in ``[0, 1]`` between two recipes (``1.0`` identical).

    Thin wrapper over `compute_similarity_breakdown` for callers that only need
    the final score.
    """
    return compute_similarity_breakdown(
        a=a,
        b=b,
        identity_weight=identity_weight,
        extras_weight=extras_weight,
    ).similarity


# ---------------------------------------------------------------------------
# Plain-language closeness label
# ---------------------------------------------------------------------------

# Thresholds (inclusive lower bound) mapping a similarity in [0, 1] to a word,
# checked high to low. Anything below the lowest falls back to the default.
_CLOSENESS_LABELS: tuple[tuple[float, str], ...] = (
    (0.90, "Very close"),
    (0.70, "Close"),
    (0.50, "Similar"),
)
_CLOSENESS_DEFAULT: str = "Loosely related"


def closeness_label(similarity: float) -> str:
    """Return a plain-language word for a ``[0, 1]`` similarity (e.g. "Very close")."""
    for threshold, label in _CLOSENESS_LABELS:
        if similarity >= threshold:
            return label
    return _CLOSENESS_DEFAULT


# ---------------------------------------------------------------------------
# Database-side annotation (shared by both public queries)
# ---------------------------------------------------------------------------

def _f(value: float) -> Value:
    return Value(float(value), output_field=FloatField())


def _wrap(expression: Combinable) -> Combinable:
    return ExpressionWrapper(expression, output_field=FloatField())


def _sum(terms: Iterable[Combinable]) -> Combinable:
    return functools.reduce(operator.add, terms)


def _mapping_case(field: str, value_to_distance: dict[str, float], default: float) -> Case:
    """A CASE mapping each stored value of *field* to a precomputed distance."""
    whens = [When(**{field: value}, then=_f(distance)) for value, distance in value_to_distance.items()]
    return Case(*whens, default=_f(default), output_field=FloatField())


def _numeric_terms(field: str, reference_value: Decimal | None, span: float, weight: float) -> tuple[Combinable, Combinable] | None:
    """
    (numerator, denominator) expressions for a nullable numeric field.

    Returns None when the reference itself has no value, so the field is dropped
    from both sums entirely.
    """
    if reference_value is None:
        return None
    distance = _wrap(Abs(Cast(F(field), output_field=FloatField()) - _f(float(reference_value))) / _f(span))
    numerator = Case(
        When(**{f"{field}__isnull": True}, then=_f(0.0)),
        default=_wrap(_f(weight) * distance),
        output_field=FloatField(),
    )
    denominator = Case(
        When(**{f"{field}__isnull": True}, then=_f(0.0)),
        default=_f(weight),
        output_field=FloatField(),
    )
    return numerator, denominator


def _ladder_distances(ladder: dict[str, float], span: float, reference_value: str) -> dict[str, float]:
    reference_position = ladder[reference_value]
    return {value: abs(position - reference_position) / span for value, position in ladder.items()}


def _color_mono_terms(reference: models.FujifilmRecipe) -> list[tuple[Combinable, Combinable]]:
    """
    Identity terms for `color` and the two toning fields, gated by regime.

    R1's regime is fixed, so this collapses to two branches on whether the
    candidate is colour or B&W. In the mixed case every one of these fields is
    a maximal difference.
    """
    is_mono_candidate = Q(film_simulation__in=MONOCHROMATIC_FILM_SIMULATIONS)
    weight = IDENTITY_FIELD_WEIGHT
    maxed = weight * MAXED_DISTANCE
    terms: list[tuple[Combinable, Combinable]] = []

    if not _is_monochrome(reference.film_simulation):
        # R1 is colour.
        if reference.color is None:
            color_num = Case(When(is_mono_candidate, then=_f(maxed)), default=_f(0.0), output_field=FloatField())
            color_den = Case(When(is_mono_candidate, then=_f(weight)), default=_f(0.0), output_field=FloatField())
        else:
            compare = _wrap(_f(weight) * Abs(Cast(F("color"), output_field=FloatField()) - _f(float(reference.color))) / _f(COLOR_SPAN))
            color_num = Case(
                When(is_mono_candidate, then=_f(maxed)),
                When(color__isnull=True, then=_f(0.0)),
                default=compare,
                output_field=FloatField(),
            )
            color_den = Case(
                When(is_mono_candidate, then=_f(weight)),
                When(color__isnull=True, then=_f(0.0)),
                default=_f(weight),
                output_field=FloatField(),
            )
        terms.append((color_num, color_den))
        # Toning fields: skipped for a colour candidate, maxed for a B&W one.
        toning_num = Case(When(is_mono_candidate, then=_f(maxed)), default=_f(0.0), output_field=FloatField())
        toning_den = Case(When(is_mono_candidate, then=_f(weight)), default=_f(0.0), output_field=FloatField())
        terms.append((toning_num, toning_den))
        terms.append((toning_num, toning_den))
        return terms

    # R1 is B&W.
    color_num = Case(When(is_mono_candidate, then=_f(0.0)), default=_f(maxed), output_field=FloatField())
    color_den = Case(When(is_mono_candidate, then=_f(0.0)), default=_f(weight), output_field=FloatField())
    terms.append((color_num, color_den))
    toning_fields: tuple[tuple[str, Decimal | None], ...] = (
        ("monochromatic_color_warm_cool", reference.monochromatic_color_warm_cool),
        ("monochromatic_color_magenta_green", reference.monochromatic_color_magenta_green),
    )
    for field, reference_value in toning_fields:
        if reference_value is None:
            num = Case(When(~is_mono_candidate, then=_f(maxed)), default=_f(0.0), output_field=FloatField())
            den = Case(When(~is_mono_candidate, then=_f(weight)), default=_f(0.0), output_field=FloatField())
        else:
            compare = _wrap(_f(weight) * Abs(Cast(F(field), output_field=FloatField()) - _f(float(reference_value))) / _f(MONOCHROMATIC_SPAN))
            num = Case(
                When(~is_mono_candidate, then=_f(maxed)),
                When(**{f"{field}__isnull": True}, then=_f(0.0)),
                default=compare,
                output_field=FloatField(),
            )
            den = Case(
                When(~is_mono_candidate, then=_f(weight)),
                When(**{f"{field}__isnull": True}, then=_f(0.0)),
                default=_f(weight),
                output_field=FloatField(),
            )
        terms.append((num, den))
    return terms


def annotate_similarity(
    queryset: QuerySet[models.FujifilmRecipe],
    *,
    reference: models.FujifilmRecipe,
    identity_weight: float = A,
    extras_weight: float = B,
) -> QuerySet[models.FujifilmRecipe]:
    """
    Annotate each recipe in *queryset* with a ``similarity`` float in ``[0, 1]``
    measuring how similar it is to *reference* (``1.0`` identical).

    The whole score is computed in the database, so callers can order and slice
    without pulling every recipe into Python. *identity_weight* and
    *extras_weight* default to the module constants; live callers pass the
    runtime django-constance values so the DB result matches the Python oracle.
    """
    identity_num: list[Combinable] = []
    identity_den: list[Combinable] = []
    extras_num: list[Combinable] = []
    extras_den: list[Combinable] = []

    def add(target_num: list[Combinable], target_den: list[Combinable], terms: tuple[Combinable, Combinable] | None) -> None:
        if terms is not None:
            target_num.append(terms[0])
            target_den.append(terms[1])

    # --- Identity round ---
    film_distances = {sim: film_simulation_distance(reference.film_simulation, sim) for sim in _FILM_SIM_RAW}
    film_case = _mapping_case("film_simulation", film_distances, default=MAXED_DISTANCE)
    identity_num.append(_wrap(_f(FILM_SIM_WEIGHT) * film_case))
    identity_den.append(_f(FILM_SIM_WEIGHT))

    wb_values = models.FujifilmRecipe.objects.values_list("white_balance", flat=True).distinct()
    wb_distances = {value: white_balance_distance(reference.white_balance, value) for value in wb_values}
    wb_case = _mapping_case("white_balance", wb_distances, default=MAXED_DISTANCE)
    identity_num.append(_wrap(_f(IDENTITY_FIELD_WEIGHT) * wb_case))
    identity_den.append(_f(IDENTITY_FIELD_WEIGHT))

    delta_red = _wrap(Cast(F("white_balance_red"), output_field=FloatField()) - _f(reference.white_balance_red))
    delta_blue = _wrap(Cast(F("white_balance_blue"), output_field=FloatField()) - _f(reference.white_balance_blue))
    wb_shift = _wrap(Sqrt(delta_red * delta_red + delta_blue * delta_blue) / _f(WB_SHIFT_SPAN))
    identity_num.append(_wrap(_f(IDENTITY_FIELD_WEIGHT) * wb_shift))
    identity_den.append(_f(IDENTITY_FIELD_WEIGHT))

    add(identity_num, identity_den, _numeric_terms("highlight", reference.highlight, HIGHLIGHT_SPAN, IDENTITY_FIELD_WEIGHT))
    add(identity_num, identity_den, _numeric_terms("shadow", reference.shadow, SHADOW_SPAN, IDENTITY_FIELD_WEIGHT))
    for num, den in _color_mono_terms(reference):
        identity_num.append(num)
        identity_den.append(den)

    # --- Extras round ---
    if reference.dynamic_range:
        dr_distances = _ladder_distances(DR_LADDER, DR_SPAN, reference.dynamic_range)
        dr_num = Case(
            When(dynamic_range="", then=_f(0.0)),
            *[When(dynamic_range=value, then=_f(MODULATOR_WEIGHT * distance)) for value, distance in dr_distances.items()],
            default=_f(0.0),
            output_field=FloatField(),
        )
        dr_den = Case(When(dynamic_range="", then=_f(0.0)), default=_f(MODULATOR_WEIGHT), output_field=FloatField())
        extras_num.append(dr_num)
        extras_den.append(dr_den)

    for field, ladder, span in (
        ("d_range_priority", DRP_LADDER, DRP_SPAN),
        ("color_chrome_effect", TRISTATE_LADDER, TRISTATE_SPAN),
        ("color_chrome_fx_blue", TRISTATE_LADDER, TRISTATE_SPAN),
    ):
        distances = _ladder_distances(ladder, span, getattr(reference, field))
        extras_num.append(_wrap(_f(MODULATOR_WEIGHT) * _mapping_case(field, distances, default=0.0)))
        extras_den.append(_f(MODULATOR_WEIGHT))

    add(extras_num, extras_den, _numeric_terms("clarity", reference.clarity, CLARITY_SPAN, MODULATOR_WEIGHT))
    add(extras_num, extras_den, _numeric_terms("sharpness", reference.sharpness, SHARPNESS_SPAN, EFFECT_WEIGHT))
    add(extras_num, extras_den, _numeric_terms("high_iso_nr", reference.high_iso_nr, NOISE_REDUCTION_SPAN, EFFECT_WEIGHT))

    reference_rough = TRISTATE_LADDER[reference.grain_roughness]
    reference_size = GRAIN_SIZE_LADDER[reference.grain_size]
    rough_case = _mapping_case("grain_roughness", {v: p for v, p in TRISTATE_LADDER.items()}, default=0.0)
    size_case = _mapping_case("grain_size", {v: p for v, p in GRAIN_SIZE_LADDER.items()}, default=0.0)
    delta_rough = _wrap(rough_case - _f(reference_rough))
    delta_size = _wrap(size_case - _f(reference_size))
    grain = _wrap(Sqrt(delta_rough * delta_rough + delta_size * delta_size) / _f(GRAIN_SPAN))
    extras_num.append(_wrap(_f(EFFECT_WEIGHT) * grain))
    extras_den.append(_f(EFFECT_WEIGHT))

    identity_score = _wrap(_f(1.0) - _wrap(_sum(identity_num) / _sum(identity_den)))
    extras_score = _wrap(_f(1.0) - _wrap(_sum(extras_num) / _sum(extras_den)))
    similarity = _wrap(identity_score * (_f(identity_weight) + _f(extras_weight) * extras_score))

    return queryset.annotate(similarity=similarity)


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------

def most_similar_recipes(
    *,
    recipe_id: int,
    limit: int | None = None,
) -> QuerySet[models.FujifilmRecipe]:
    """
    Return every other recipe annotated with ``similarity`` to *recipe_id*,
    ordered most similar first. Ties break on ``pk`` for a stable order.
    """
    reference = models.FujifilmRecipe.objects.get(pk=recipe_id)
    queryset = annotate_similarity(
        models.FujifilmRecipe.objects.exclude(pk=recipe_id),
        reference=reference,
    ).order_by("-similarity", "pk")
    if limit is not None:
        queryset = queryset[:limit]
    return queryset


def recipes_at_least_similar(
    *,
    reference: models.FujifilmRecipe,
    min_similarity: float,
    identity_weight: float = A,
    extras_weight: float = B,
) -> list[models.FujifilmRecipe]:
    """
    Return every recipe (other than *reference*) whose similarity to *reference*
    is at least *min_similarity*.

    The filter runs in the database via `annotate_similarity`, so the whole
    collection is never pulled into Python. This is the graph neighbourhood's
    candidate cut, replacing the Hamming max-distance filter.
    """
    queryset = annotate_similarity(
        models.FujifilmRecipe.objects.exclude(pk=reference.pk),
        reference=reference,
        identity_weight=identity_weight,
        extras_weight=extras_weight,
    ).filter(similarity__gte=min_similarity)  # type: ignore[misc]  # `similarity` is an annotation, not a model field
    return list(queryset)


def similarity_between(*, recipe_id_a: int, recipe_id_b: int) -> float:
    """
    Return the ``[0, 1]`` similarity between two recipes, computed in the
    database via the same annotation `most_similar_recipes` uses.
    """
    reference = models.FujifilmRecipe.objects.get(pk=recipe_id_a)
    row = annotate_similarity(
        models.FujifilmRecipe.objects.filter(pk=recipe_id_b),
        reference=reference,
    ).first()
    if row is None:
        raise models.FujifilmRecipe.DoesNotExist(recipe_id_b)
    return float(row.similarity)  # type: ignore[attr-defined]
