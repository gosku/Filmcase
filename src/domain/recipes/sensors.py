"""
Domain helpers for the sensor set on a :class:`src.data.models.FujifilmRecipe`.
"""

from collections.abc import Iterable

_SIGNATURE_SEPARATOR = ","


def compute_sensor_signature(sensor_names: Iterable[str]) -> str:
    """
    Return the canonical signature string for *sensor_names*.

    The signature is the lowercased, sorted, comma-joined sensor names. Equal
    sets yield equal signatures regardless of input order or casing. An empty
    iterable returns the empty string — that is the signature used by recipes
    with no sensors attached.

    The result is stored on ``FujifilmRecipe.sensor_signature`` and included
    in the recipe's ``UniqueConstraint`` so that recipes with identical
    settings but different sensor sets can coexist while still being
    deduplicated when their sensor sets match.
    """
    normalised = sorted({name.lower() for name in sensor_names})
    return _SIGNATURE_SEPARATOR.join(normalised)
