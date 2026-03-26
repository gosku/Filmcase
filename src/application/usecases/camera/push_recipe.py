"""
Application-layer use case for pushing a recipe to a Fujifilm camera.

This is the intended entry point for callers outside the domain layer.
Unlike the domain operation, slot_name is required and must be non-blank.
"""
from __future__ import annotations

from src.domain.camera import operations
from src.domain.camera.ptp_device import PTPDevice
from src.domain.images.dataclasses import RECIPE_NAME_MAX_LEN, FujifilmRecipeData


def push_recipe_to_camera(
    device: PTPDevice,
    recipe: FujifilmRecipeData,
    *,
    slot_index: int,
    slot_name: str,
) -> list[int]:
    """
    Push a film simulation recipe to a custom C-slot on the connected camera.

    Args:
        device:      A connected PTPDevice instance.
        recipe:      The recipe to write.
        slot_index:  1-based custom slot number (e.g. 1 for C1).
        slot_name:   Display name for the slot.  Required; must be a non-blank
                     string of at most 25 ASCII characters.

    Returns:
        A list of PTP property codes for which the write failed.  An empty
        list means all writes succeeded.

    Raises:
        ValueError: If slot_name is blank, too long, or contains non-ASCII characters.
        CameraConnectionError: If the camera becomes unreachable during the
                               write sequence.
    """
    if not slot_name or not slot_name.strip():
        raise ValueError("slot_name must be a non-blank string")
    if len(slot_name) > RECIPE_NAME_MAX_LEN:
        raise ValueError(
            f"slot_name must be ≤{RECIPE_NAME_MAX_LEN} characters, got {len(slot_name)}"
        )
    if not slot_name.isascii():
        raise ValueError(f"slot_name must contain only ASCII characters, got {slot_name!r}")

    return operations.push_recipe(device, recipe, slot_index=slot_index, slot_name=slot_name)
