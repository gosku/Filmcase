"""
Application-layer use case for pushing a recipe to a Fujifilm camera.
"""
from __future__ import annotations

import time

from django.conf import settings

from src.data import models
from src.data.camera import constants
from src.domain.camera import device_config
from src.domain.camera import operations as camera_operations
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries
from src.domain.recipes import queries as recipe_queries

_CODE_TO_PROP_NAME: dict[int, str] = {
    constants.PROP_SLOT_NAME: "SlotName",
    **{code: name for name, code in constants.CUSTOM_SLOT_CODES.items()},
}


class RecipeWriteError(Exception):
    """Raised when one or more properties could not be written or verified."""

    def __init__(self, failed_properties: list[str]) -> None:
        self.failed_properties = failed_properties
        super().__init__(
            f"Recipe write incomplete: {len(failed_properties)} property/properties failed "
            f"({failed_properties})"
        )


def push_recipe_to_camera(
    recipe: models.FujifilmRecipe,
    *,
    slot_index: int,
) -> None:
    """
    Push a film simulation recipe to a custom C-slot on the connected camera.

    The device is obtained from device_config (settings.PTP_DEVICE).
    Connection and disconnection are managed internally.

    Args:
        recipe:      The recipe to write.  ``recipe.name`` must be a non-blank
                     string of at most 25 ASCII characters.
        slot_index:  1-based custom slot number (e.g. 1 for C1).

    Raises:
        RecipeValidationError: If any recipe field (including name) is invalid.
        CameraConnectionError: If the camera becomes unreachable during the
                               write sequence.
        CameraWriteError:      If the camera rejects a critical write.
        RecipeWriteError:      If one or more properties failed to write or verify.
                               ``exc.failed_properties`` lists the property names.
    """
    recipe_data = recipe_queries.recipe_from_db(recipe=recipe)
    device = device_config.get_device()
    device.connect()
    try:
        # --- Step 1: set slot cursor ---
        rc = device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot_index)
        if rc != 0:
            raise ptp_device.CameraConnectionError(
                f"Failed to set slot cursor to slot {slot_index} (rc={rc})"
            )

        time.sleep(settings.CAMERA_PRE_WRITE_DELAY_S)

        # --- Step 2: validate recipe and translate to PTP values ---
        # Validation happens here, before any writes, so an invalid recipe never
        # touches the camera.
        ptp_items = camera_queries.recipe_to_ptp_values(recipe_data).items()

        # --- Step 3: write all properties (slot name first, then recipe properties) ---
        failed_codes: list[int] = [constants.PROP_SLOT_NAME, *(code for code, _ in ptp_items)]
        written: list[tuple[int, str | int]] = []  # (code, value) pairs that reported success

        # Build the unified write sequence.  The slot name is a string property
        # and is written first; recipe properties are all integers.
        all_writes: list[tuple[int, str | int]] = [
            (constants.PROP_SLOT_NAME, recipe_data.name),
            *ptp_items,
        ]

        for code, value in all_writes:
            time.sleep(settings.CAMERA_PRE_WRITE_DELAY_S)   # 50 ms before write

            try:
                camera_operations.set_prop_with_retry(device, code, value)
            except ptp_device.CameraConnectionError:
                raise  # camera is gone; abort the entire write sequence
            except ptp_device.CameraWriteError:
                pass  # camera rejected this property; continue with the rest
            else:
                failed_codes.remove(code)
                written.append((code, value))

            time.sleep(settings.CAMERA_POST_WRITE_DELAY_S)  # 200 ms after write

        # --- Step 4: verify written properties ---
        if settings.CAMERA_VERIFY_WRITES:
            # GrainEffect Off is written as sentinel 1; the camera normalises it to
            # 6 or 7 (retaining the last-remembered grain size), so the read-back
            # never matches the written value. Skip verification for that case.
            grain_code = constants.CUSTOM_SLOT_CODES["GrainEffect"]
            verifiable = [(c, v) for c, v in written if not (c == grain_code and v == 1)]
            verification_failures = camera_operations.verify_written_properties(device, verifiable)
            failed_codes.extend(verification_failures)

        if failed_codes:
            failed_properties = [_CODE_TO_PROP_NAME.get(c, hex(c)) for c in failed_codes]
            raise RecipeWriteError(failed_properties)
    finally:
        device.disconnect()
