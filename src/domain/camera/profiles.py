"""
Per-model camera capability descriptors.

A CameraProfile is pure data describing what one camera model can accept and
which transport strategy drives it.  Capability differences between models live
here as data, so the validation and strategy code reads from one description
rather than branching on the model name.

Today there is a single profile, the per-property one shared by the X-S10 and
every other body that exposes the custom-slot PTP property interface.  The X-T2
backup-blob profile, and a per-model registry keyed on the camera name, arrive
with the X-T2 strategy; see
investigation/add_xt2_support/04_camera_strategy_architecture.md.

Profiles are keyed per model, not per sensor: two bodies on the same sensor can
differ (e.g. the X-T4 has more film simulations than the X-T3).
"""
from __future__ import annotations

import enum
from collections.abc import Set

import attrs

from src.data.camera import constants


class CameraInterface(enum.Enum):
    """
    The slot-access mechanism a camera model exposes.

    PER_PROPERTY: the custom-slot PTP property interface (X-S10, X-T3+): a slot
    cursor selects a slot and each recipe field is its own device property.
    """

    PER_PROPERTY = "per_property"


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


def get_profile(camera_name: str) -> CameraProfile:
    """
    Return the capability profile for a camera model.

    In PR 1 every model, known or not, resolves to the per-property profile:
    the current code assumes the per-property interface for any connected
    camera, so this preserves that behaviour.  A per-model registry keyed on
    *camera_name* is introduced with the X-T2 backup-blob profile, which is the
    first profile that differs.
    """
    return PER_PROPERTY_PROFILE
