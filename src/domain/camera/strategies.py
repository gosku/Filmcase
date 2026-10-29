"""
Per-model camera strategies: the middle layer between the camera use cases and
the PTP primitives.

A CameraStrategy owns the model-specific algorithm for reading slots, validating
a recipe, and pushing a recipe.  A use case resolves a strategy from the camera
model (via :func:`get_strategy`) and delegates to it, staying thin: it handles
only the connection lifecycle and error translation.

Today there is one strategy, PerPropertyStrategy, for bodies that expose the
custom-slot PTP property interface (X-S10, X-T3+).  The X-T2 backup-blob strategy
arrives in a follow-up; the Protocol then grows the methods it needs
(read_slot_recipe, validate_backup, collection push).  See
investigation/add_xt2_support/04_camera_strategy_architecture.md.
"""
from __future__ import annotations

import time
from typing import Callable
from typing import Protocol
from typing import TypeVar
from typing import runtime_checkable

import attrs

from src.data.camera import constants
from src.domain.camera import operations as camera_operations
from src.domain.camera import profiles
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries
from src.domain.camera import validation
from src.domain.images import dataclasses as image_dataclasses
from src.domain.settings import queries as settings_queries

_T = TypeVar("_T")

# Maps a PTP property code back to its readable name, for RecipeWriteError.
_CODE_TO_PROP_NAME: dict[int, str] = {
    constants.PROP_SLOT_NAME: "SlotName",
    **{code: name for name, code in constants.CUSTOM_SLOT_CODES.items()},
}


class RecipeWriteError(Exception):
    """
    Raised when one or more properties could not be written or verified.

    Importable from here (where push_recipe raises it) and re-exported by the
    push_recipe use case for its public contract.
    """

    def __init__(self, failed_properties: list[str]) -> None:
        self.failed_properties = failed_properties
        super().__init__(
            f"Recipe write incomplete: {len(failed_properties)} property/properties failed "
            f"({failed_properties})"
        )


@runtime_checkable
class CameraStrategy(Protocol):
    """
    The model-specific read/validate/push algorithm a use case delegates to.

    Implementations are pure: they receive an already-connected device and never
    manage the connection lifecycle themselves.
    """

    def read_slots(
        self, device: ptp_device.PTPDevice, *, slot_count: int
    ) -> list[camera_queries.SlotState]:
        """
        Read the name and film simulation of each custom slot (1..slot_count).
        """
        ...

    def validate_recipe(self, recipe: image_dataclasses.FujifilmRecipeData) -> None:
        """
        Validate a recipe against this model's capabilities.

        :raises RecipeValidationError: If a field is not acceptable to the model.
        """
        ...

    def push_recipe(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_index: int,
    ) -> None:
        """
        Write *recipe* to custom slot *slot_index* on the connected device.

        :raises RecipeValidationError: If the recipe is invalid for the model.
        :raises CameraConnectionError: If the camera becomes unreachable.
        :raises CameraWriteError: If the camera rejects a critical write.
        :raises RecipeWriteError: If one or more properties failed to write/verify.
        """
        ...


@attrs.frozen
class PerPropertyStrategy:
    """
    Strategy for bodies with the custom-slot PTP property interface (X-S10, X-T3+).

    Reads and writes each recipe field as its own device property, selecting the
    target slot via the slot cursor.
    """

    profile: profiles.CameraProfile

    def read_slots(
        self, device: ptp_device.PTPDevice, *, slot_count: int
    ) -> list[camera_queries.SlotState]:
        states: list[camera_queries.SlotState] = []
        for idx in range(1, slot_count + 1):
            if idx > 1:
                time.sleep(settings_queries.get_camera_inter_slot_delay_s())
            _set_cursor_with_retry(device, idx)
            time.sleep(settings_queries.get_camera_post_cursor_delay_s())
            name = _read_str_with_retry(device, constants.PROP_SLOT_NAME)
            film_sim = _read_int_with_retry(
                device, constants.CUSTOM_SLOT_CODES["FilmSimulation"]
            )
            states.append(
                camera_queries.SlotState(index=idx, name=name, film_sim_ptp=film_sim)
            )
        return states

    def validate_recipe(self, recipe: image_dataclasses.FujifilmRecipeData) -> None:
        validation.validate_recipe_for_profile(recipe, profile=self.profile)

    def push_recipe(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_index: int,
    ) -> None:
        # --- Step 1: set slot cursor (retried, mirroring the WebUSB port) ---
        try:
            camera_operations.set_cursor_with_retry(
                device, constants.PROP_SLOT_CURSOR, slot_index
            )
        except ptp_device.CameraWriteError as exc:
            # A refusal is reported as a connection failure, as the WebUSB port
            # also does: nothing has been written yet, so there is no partly
            # applied recipe to describe and the user only needs to know it did
            # not start.
            raise ptp_device.CameraConnectionError(
                f"Failed to set slot cursor to slot {slot_index} (rc={exc.rc})"
            ) from exc

        time.sleep(settings_queries.get_camera_pre_write_delay_s())

        # --- Step 2: validate recipe and translate to PTP values ---
        # Validation happens here, before any writes, so an invalid recipe never
        # touches the camera.
        ptp_items = camera_queries.recipe_to_ptp_values(recipe).items()

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
            time.sleep(settings_queries.get_camera_pre_write_delay_s())   # 50 ms before write

            try:
                camera_operations.set_prop_with_retry(device, code, value)
            except ptp_device.CameraConnectionError:
                raise  # camera is gone; abort the entire write sequence
            except ptp_device.CameraWriteError:
                pass  # camera rejected this property; continue with the rest
            else:
                failed_codes.remove(code)
                written.append((code, value))

            time.sleep(settings_queries.get_camera_post_write_delay_s())  # 200 ms after write

        # --- Step 4: verify written properties ---
        if settings_queries.get_camera_verify_writes():
            # GrainEffect Off is written as a sentinel; the camera normalises it to
            # 6 or 7 (retaining the last-remembered grain size), so the read-back
            # never matches the written value. Skip verification for that case.
            grain_code = constants.CUSTOM_SLOT_CODES["GrainEffect"]
            verifiable = [
                (c, v)
                for c, v in written
                if not (c == grain_code and v == camera_queries.GRAIN_OFF_SENTINEL)
            ]
            verification_failures = camera_operations.verify_written_properties(device, verifiable)
            failed_codes.extend(verification_failures)

        if failed_codes:
            failed_properties = [_CODE_TO_PROP_NAME.get(c, hex(c)) for c in failed_codes]
            raise RecipeWriteError(failed_properties)


def get_strategy(camera_name: str) -> CameraStrategy:
    """
    Return the strategy that drives a camera model.

    In PR 1 every model resolves to the per-property strategy (the only
    interface that exists yet); the X-T2 backup-blob strategy is selected here,
    on the profile's interface, when it lands.
    """
    profile = profiles.get_profile(camera_name)
    return PerPropertyStrategy(profile=profile)


# ---------------------------------------------------------------------------
# Per-property read retry helpers
#
# Only CameraConnectionError is retried; a CameraWriteError (e.g. the camera
# refusing a cursor move) propagates immediately.  Kept here with the strategy
# that uses them; they were lifted verbatim from the get_camera_slots use case.
# ---------------------------------------------------------------------------


def _retry(fn: Callable[[], _T]) -> _T:
    """
    Call *fn* up to CAMERA_MAX_RETRIES times, sleeping with exponential
    back-off between attempts.  Only retries on CameraConnectionError.
    Any other exception (e.g. CameraWriteError) propagates immediately.
    """
    last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError(
        "no retries attempted"
    )
    max_retries = settings_queries.get_camera_max_retries()
    retry_backoff_s = settings_queries.get_camera_retry_backoff_s()
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            time.sleep(retry_backoff_s * (2 ** (attempt - 2)))
        try:
            return fn()
        except ptp_device.CameraConnectionError as exc:
            last_err = exc
    raise last_err


def _set_cursor_with_retry(device: ptp_device.PTPDevice, slot_index: int) -> None:
    """
    Write the slot cursor, retrying on transport failures.

    :raises CameraConnectionError: If the cursor write fails after all retries.
    :raises CameraWriteError: If the camera rejects the cursor write (non-zero rc).
    """
    def _attempt() -> None:
        rc = device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot_index)
        if rc != 0:
            raise ptp_device.CameraWriteError(constants.PROP_SLOT_CURSOR, slot_index, rc)

    _retry(_attempt)


def _read_str_with_retry(device: ptp_device.PTPDevice, code: int) -> str:
    """
    Read a string property, retrying on transport failures.
    """
    return _retry(lambda: device.get_property_string(code))


def _read_int_with_retry(device: ptp_device.PTPDevice, code: int) -> int:
    """
    Read an integer property, retrying on transport failures.
    """
    return _retry(lambda: device.get_property_int(code))
