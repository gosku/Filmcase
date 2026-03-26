"""
Application-layer use case for pushing a recipe to a Fujifilm camera.
"""
from __future__ import annotations

import time

from src.data.camera import constants
from src.domain.camera.operations import (
    POST_WRITE_DELAY_S,
    PRE_WRITE_DELAY_S,
    set_prop_with_retry,
    verify_written_properties,
)
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError, PTPDevice
from src.domain.camera.queries import recipe_to_ptp_values
from src.domain.images.dataclasses import FujifilmRecipeData


def push_recipe_to_camera(
    device: PTPDevice,
    recipe: FujifilmRecipeData,
    *,
    slot_index: int,
) -> list[int]:
    """
    Push a film simulation recipe to a custom C-slot on the connected camera.

    The recipe's ``name`` field is used as the slot display name and must be
    non-blank (validated via recipe_to_ptp_values → validate_recipe_for_camera).

    Args:
        device:      A connected PTPDevice instance.
        recipe:      The recipe to write.  ``recipe.name`` must be a non-blank
                     string of at most 25 ASCII characters.
        slot_index:  1-based custom slot number (e.g. 1 for C1).

    Returns:
        A list of PTP property codes for which the write failed.  An empty
        list means all writes succeeded.

    Raises:
        RecipeValidationError: If any recipe field (including name) is invalid.
        CameraConnectionError: If the camera becomes unreachable during the
                               write sequence.
    """
    # --- Step 1: set slot cursor ---
    rc = device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot_index)
    if rc != 0:
        raise CameraConnectionError(
            f"Failed to set slot cursor to slot {slot_index} (rc={rc})"
        )

    time.sleep(PRE_WRITE_DELAY_S)

    # --- Step 2: validate recipe and translate to PTP values ---
    # Validation happens here, before any writes, so an invalid recipe never
    # touches the camera.
    ptp_items = recipe_to_ptp_values(recipe).items()

    # --- Step 3: write all properties (slot name first, then recipe properties) ---
    failed_codes: list[int] = [constants.PROP_SLOT_NAME, *(code for code, _ in ptp_items)]
    written: list[tuple[int, str | int]] = []  # (code, value) pairs that reported success

    # Build the unified write sequence.  The slot name is a string property
    # and is written first; recipe properties are all integers.
    all_writes: list[tuple[int, str | int]] = [
        (constants.PROP_SLOT_NAME, recipe.name),
        *ptp_items,
    ]

    for code, value in all_writes:
        time.sleep(PRE_WRITE_DELAY_S)   # 50 ms before write

        try:
            set_prop_with_retry(device, code, value)
        except CameraConnectionError:
            raise  # camera is gone; abort the entire write sequence
        except CameraWriteError:
            pass  # camera rejected this property; continue with the rest
        else:
            failed_codes.remove(code)
            written.append((code, value))

        time.sleep(POST_WRITE_DELAY_S)  # 200 ms after write

    # --- Step 4: verify written properties ---
    verification_failures = verify_written_properties(device, written)
    failed_codes.extend(verification_failures)

    return failed_codes
