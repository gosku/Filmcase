"""
Per-model camera capability descriptors.

A CameraProfile is pure data describing what one camera model can accept and
which transport strategy drives it.  Capability differences between models live
here as data, so the validation and strategy code reads from one description
rather than branching on the model name.

Two profiles exist: the per-property one shared by the X-S10 and every other
body that exposes the custom-slot PTP property interface, and the X-T2
backup-blob profile.  A per-model registry keyed on the camera name resolves one
or the other, defaulting to per-property for any unmapped model.

Profiles are keyed per model, not per sensor: two bodies on the same sensor can
differ (e.g. the X-T4 has more film simulations than the X-T3).
"""
from __future__ import annotations

import enum
from collections.abc import Set

import attrs

from src.data.camera import constants
from src.data.camera import constants_xt2


class CameraInterface(enum.Enum):
    """
    The slot-access mechanism a camera model exposes.

    PER_PROPERTY: the custom-slot PTP property interface (X-S10, X-T3+): a slot
    cursor selects a slot and each recipe field is its own device property.

    BACKUP_BLOB: no per-slot interface (X-T2 and older); recipes live inside the
    settings backup blob, read and written whole.
    """

    PER_PROPERTY = "per_property"
    BACKUP_BLOB = "backup_blob"


@attrs.frozen
class CameraProfile:
    """
    What one camera model can accept, plus which strategy drives it.

    The ``supported_*`` sets are the camera-acceptable values for each recipe
    field; model-relative recipe validation reads from them.  ``interface``
    selects the strategy that reads and writes slots.
    """

    interface: CameraInterface
    supported_film_simulations: Set[str]
    supported_white_balance_modes: Set[str]
    supported_dynamic_ranges: Set[str]
    supported_dr_priorities: Set[str]
    supported_color_chrome_effects: Set[str]
    supported_color_chrome_fx_blues: Set[str]
    supported_grain_roughnesses: Set[str]
    # Grain size depends on roughness: the sizes allowed when roughness is Off
    # differ from those allowed when it is Weak/Strong.
    grain_sizes_when_off: Set[str]
    grain_sizes_when_on: Set[str]
    supported_high_iso_nr_values: Set[int]


# The per-property profile: every value the custom-slot PTP interface accepts,
# built from the write-side constants.  This is the X-S10 / X-T3+ profile and,
# in PR 1, the default for every model (there is no second profile yet).
PER_PROPERTY_PROFILE: CameraProfile = CameraProfile(
    interface=CameraInterface.PER_PROPERTY,
    supported_film_simulations=frozenset(constants.FILM_SIMULATION_TO_PTP),
    supported_white_balance_modes=frozenset(constants.WHITE_BALANCE_TO_PTP),
    supported_dynamic_ranges=frozenset(constants.DRANGE_MODE_TO_PTP),
    supported_dr_priorities=frozenset(constants.CUSTOM_SLOT_DR_PRIORITY_DECODE.values()),
    supported_color_chrome_effects=frozenset(constants.CUSTOM_SLOT_CCE_PTP.values()),
    supported_color_chrome_fx_blues=frozenset(constants.CUSTOM_SLOT_CFX_PTP.values()),
    supported_grain_roughnesses=frozenset(("Off", "Weak", "Strong")),
    grain_sizes_when_off=frozenset(("Off", "Small", "Large")),
    grain_sizes_when_on=frozenset(("Small", "Large")),
    supported_high_iso_nr_values=frozenset(constants.CUSTOM_SLOT_NR_DECODE.values()),
)


# The X-T2 backup-blob profile. Capability sets are derived from constants_xt2
# so they cannot drift from the codec's own maps. Recipe validation for this
# model is the bespoke map_recipe (which drops unsupported fields and reports
# them), not validate_recipe_for_profile, so these sets are a descriptor of what
# the model accepts rather than the validation input the per-property path uses.
XT2_PROFILE: CameraProfile = CameraProfile(
    interface=CameraInterface.BACKUP_BLOB,
    supported_film_simulations=frozenset(constants_xt2.FILM_SIMULATION_BY_BYTE.values()),
    supported_white_balance_modes=frozenset(constants_xt2.WHITE_BALANCE_BY_SELECTOR.values()),
    supported_dynamic_ranges=frozenset(constants_xt2.DYNAMIC_RANGE_BY_BYTE.values()),
    supported_dr_priorities=frozenset(("Off",)),           # no D-Range Priority on the X-T2
    supported_color_chrome_effects=frozenset(("Off",)),    # no Color Chrome Effect
    supported_color_chrome_fx_blues=frozenset(("Off",)),   # no Color Chrome FX Blue
    supported_grain_roughnesses=frozenset(constants_xt2.GRAIN_ROUGHNESS_BY_BYTE.values()),
    grain_sizes_when_off=frozenset(),                      # grain has no size on the X-T2
    grain_sizes_when_on=frozenset(),
    supported_high_iso_nr_values=frozenset(range(-4, 5)),
)

# Models whose profile is not the per-property default. Keyed per model, not per
# sensor: the X-T2 field map is X-T2 specific, so only the X-T2 opts into it.
_PROFILES_BY_MODEL: dict[str, CameraProfile] = {
    "X-T2": XT2_PROFILE,
}


def get_profile(camera_model: str) -> CameraProfile:
    """
    Return the capability profile for a camera model.

    An explicit allow-list: only models listed here get a non-default profile.
    Every other model, known or unknown, falls back to the per-property profile,
    which is the safer default even for bodies whose constants differ slightly
    (e.g. an X-T3 lacking Classic Negative); the backup-blob path is opt-in per
    model because its byte layout is X-T2 specific.
    """
    return _PROFILES_BY_MODEL.get(camera_model, PER_PROPERTY_PROFILE)


# The interface a model with no explicit profile resolves to; served to the
# client so its getStrategy falls back exactly as get_profile does here.
DEFAULT_INTERFACE: str = PER_PROPERTY_PROFILE.interface.value


def interface_by_model() -> dict[str, str]:
    """
    Map each explicitly-profiled model to its interface value.

    For the client config: the browser resolves a strategy from the camera model
    the same way :func:`get_profile` does, so it is served this allow-list plus
    :data:`DEFAULT_INTERFACE` for everything not in it.
    """
    return {model: profile.interface.value for model, profile in _PROFILES_BY_MODEL.items()}
