"""
Per-model camera strategies: the middle layer between the camera use cases and
the PTP primitives.

A CameraStrategy owns the model-specific algorithm for reading slots, validating
a recipe, and pushing a recipe.  A use case resolves a strategy from the camera
model (via :func:`get_strategy`) and delegates to it, staying thin: it handles
only the connection lifecycle and error translation.

Two strategies exist: PerPropertyStrategy for bodies with the custom-slot PTP
property interface (X-S10, X-T3+), and BackupBlobStrategy for bodies with no such
interface (X-T2 and older), whose recipes live in the settings backup blob read
and written whole.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Callable
from typing import Protocol
from typing import TypeAlias
from typing import TypeVar
from typing import runtime_checkable

import attrs

from src.data.camera import constants
from src.data.camera import constants_xt2
from src.domain.camera import xt2_backup
from src.domain.camera import operations as camera_operations
from src.domain.camera import profiles
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries
from src.domain.camera import validation
from src.domain.images import dataclasses as image_dataclasses
from src.domain.settings import queries as settings_queries

_T = TypeVar("_T")

# A recipe paired with the 1-based slot it will be written to, for a collection
# push.
CollectionAssignment: TypeAlias = tuple[int, image_dataclasses.FujifilmRecipeData]

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


class BackupValidationError(Exception):
    """
    Raised when the camera's backup blob does not strictly validate.

    Editing it by offset would be unsafe, so the push refuses before any write.
    """

    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__(f"Backup failed validation: {len(errors)} error(s)")


class PushNotFeasibleError(Exception):
    """
    Raised when a push cannot go ahead without retuning a kept slot's white
    balance (the X-T2 global-WB constraint).
    """

    def __init__(self, conflicts: tuple[str, ...]) -> None:
        self.conflicts = conflicts
        super().__init__("; ".join(conflicts) if conflicts else "Push not feasible")


@attrs.frozen
class SlotFeasibility:
    """Whether a given recipe can be pushed into one slot, for the picker UI."""

    slot_index: int        # 1-based
    feasible: bool
    reason: str            # empty when feasible


@attrs.frozen
class RecipeFeasibility:
    """
    How a recipe would push to a model, for the picker UI.

    ``slots`` is the per-slot grey-out verdict. ``dropped_fields`` names the
    recipe's fields the model silently drops (empty for a per-property body,
    which keeps every field); it is shown as a warning before the push, never a
    failure.
    """

    slots: list[SlotFeasibility]
    dropped_fields: tuple[str, ...]


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

    def push_collection(
        self, device: ptp_device.PTPDevice, assignments: Sequence[CollectionAssignment]
    ) -> None:
        """
        Write several recipes to their assigned slots.

        Per-property bodies write each slot in turn; the X-T2 edits one blob with
        all the assignments and restores once.

        :raises RecipeWriteError: If a write failed or did not verify.
        :raises CameraConnectionError / CameraWriteError: On transport failure.
        """
        ...

    def plan_feasibility(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_count: int,
    ) -> RecipeFeasibility:
        """
        How *recipe* would push to this model: the per-slot grey-out verdict and
        the fields the model drops.

        Per-property bodies are always feasible and drop nothing; the X-T2
        reflects the global-WB constraint so the picker can grey out conflicting
        slots, and reports the fields it lacks so the picker can warn.
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

    def push_collection(
        self, device: ptp_device.PTPDevice, assignments: Sequence[CollectionAssignment]
    ) -> None:
        # Each slot is independent on a per-property body, so writing them in
        # turn is the whole of it (the server analogue of the client's loop).
        for slot_index, recipe in assignments:
            self.push_recipe(device, recipe, slot_index=slot_index)

    def plan_feasibility(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_count: int,
    ) -> RecipeFeasibility:
        # No shared-WB constraint and nothing dropped on a per-property body:
        # every slot is feasible and every field is kept.
        slots = [SlotFeasibility(slot_index=idx, feasible=True, reason="") for idx in range(1, slot_count + 1)]
        return RecipeFeasibility(slots=slots, dropped_fields=())


@attrs.frozen
class BackupBlobStrategy:
    """
    Strategy for bodies with no per-slot interface (X-T2 and older).

    Reads, edits and restores the whole settings backup blob: the recipes live
    at fixed byte offsets inside it. The codec in src.domain.camera.xt2_backup
    does the pure byte work; this composes it over a connected device.
    """

    profile: profiles.CameraProfile

    def read_slots(
        self, device: ptp_device.PTPDevice, *, slot_count: int
    ) -> list[camera_queries.SlotState]:
        return xt2_backup.decode_slot_states(device.get_backup())

    def validate_recipe(self, recipe: image_dataclasses.FujifilmRecipeData) -> None:
        # map_recipe raises RecipeNotRepresentable on a value the X-T2 lacks; the
        # dropped-field report it also produces is surfaced at push time.
        xt2_backup.map_recipe(recipe)

    def push_recipe(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_index: int,
    ) -> None:
        blob = self._validated_backup(device)
        mapping = xt2_backup.map_recipe(recipe)
        feasibility = xt2_backup.check_feasibility(blob, slot_index - 1, mapping)
        if not feasibility.ok:
            raise PushNotFeasibleError(feasibility.conflicts)
        edited = xt2_backup.apply_recipe(blob, slot_index - 1, mapping)
        self._restore_and_verify(device, edited)

    def push_collection(
        self, device: ptp_device.PTPDevice, assignments: Sequence[CollectionAssignment]
    ) -> None:
        blob = self._validated_backup(device)
        mapped = [(slot_index - 1, xt2_backup.map_recipe(recipe)) for slot_index, recipe in assignments]
        feasibility = xt2_backup.check_collection_feasibility(blob, mapped)
        if not feasibility.ok:
            raise PushNotFeasibleError(feasibility.conflicts)
        edited = xt2_backup.apply_recipes(blob, mapped)
        self._restore_and_verify(device, edited)

    def plan_feasibility(
        self,
        device: ptp_device.PTPDevice,
        recipe: image_dataclasses.FujifilmRecipeData,
        *,
        slot_count: int,
    ) -> RecipeFeasibility:
        blob = device.get_backup()
        try:
            mapping = xt2_backup.map_recipe(recipe)
        except xt2_backup.RecipeNotRepresentable:
            # The recipe cannot be pushed at all, so no slot is feasible and there
            # is nothing to report as dropped. A recipe this camera has no film
            # simulation for needs no spelling out, so the picker greys every slot
            # with no note: the empty reason leaves nothing to show.
            slots = [SlotFeasibility(slot_index=idx, feasible=False, reason="")
                     for idx in range(1, slot_count + 1)]
            return RecipeFeasibility(slots=slots, dropped_fields=())
        slots = []
        for idx in range(1, slot_count + 1):
            feasibility = xt2_backup.check_feasibility(blob, idx - 1, mapping)
            slots.append(
                SlotFeasibility(
                    slot_index=idx,
                    feasible=feasibility.ok,
                    reason="" if feasibility.ok else "; ".join(feasibility.conflicts),
                )
            )
        return RecipeFeasibility(slots=slots, dropped_fields=mapping.dropped)

    def _validated_backup(self, device: ptp_device.PTPDevice) -> bytes:
        blob = device.get_backup()
        report = xt2_backup.validate_backup(blob)
        if not report.ok:
            raise BackupValidationError(report.errors)
        return blob

    def _restore_and_verify(self, device: ptp_device.PTPDevice, edited: bytes) -> None:
        verify = settings_queries.get_camera_verify_writes()
        try:
            device.restore_backup(edited)
        except ptp_device.RestoreAckTimeout:
            # The write may well have applied; only confirm by read-back. With
            # verification off there is no way to confirm, so surface the failure.
            if not verify:
                raise
        if verify:
            result = xt2_backup.verify_round_trip(device.get_backup(), edited)
            if not result.ok:
                raise RecipeWriteError(sorted(_affected_slot_labels(result.mismatches)))


def _affected_slot_labels(mismatches: tuple[int, ...]) -> set[str]:
    """Name the regions a round-trip mismatch touched, for RecipeWriteError."""
    labels: set[str] = set()
    slots_end = constants_xt2.SLOT0_OFFSET + constants_xt2.SLOT_SIZE * constants_xt2.SLOT_COUNT
    for offset in mismatches:
        if constants_xt2.SLOT0_OFFSET <= offset < slots_end:
            labels.add(f"C{(offset - constants_xt2.SLOT0_OFFSET) // constants_xt2.SLOT_SIZE + 1}")
        else:
            labels.add("header")
    return labels or {"backup"}


def get_strategy(camera_model: str) -> CameraStrategy:
    """
    Return the strategy that drives a camera model.

    Resolves the model's profile and returns the strategy for its interface:
    the per-property strategy for the custom-slot PTP interface, the backup-blob
    strategy for bodies whose recipes live in the settings backup (X-T2).
    """
    profile = profiles.get_profile(camera_model)
    if profile.interface is profiles.CameraInterface.BACKUP_BLOB:
        return BackupBlobStrategy(profile=profile)
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
