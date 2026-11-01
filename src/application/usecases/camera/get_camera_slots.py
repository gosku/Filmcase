"""
Application-layer use case for reading all custom slot states from a camera.

Orchestrates the connection lifecycle (connect -> read -> disconnect) and resolves
the per-model strategy that performs the read. The read algorithm itself,
including its retry behaviour, lives in the strategy.

When a target recipe is given, the read also reports whether that recipe could be
pushed into each slot and which of its fields the model would drop, so a picker
can grey out conflicting slots and warn before a push. Without a target it reads
the slots alone, exactly as before.

The concrete device class is read from settings.PTP_DEVICE via device_config.
"""
from __future__ import annotations

import attrs

from src.data import models
from src.domain.camera import device_config
from src.domain.camera import queries as camera_queries
from src.domain.camera import strategies
from src.domain.recipes import queries as recipe_queries


@attrs.frozen
class CameraSlots:
    """
    A camera's custom slots, with optional push feasibility for a target recipe.

    ``feasibility`` and ``dropped_fields`` are populated only when a target recipe
    is passed to the read; otherwise ``feasibility`` is empty and
    ``dropped_fields`` is ``()``, and the picker renders every slot normally.
    """

    camera_model: str
    slots: list[camera_queries.SlotState]
    feasibility: list[strategies.SlotFeasibility]
    dropped_fields: tuple[str, ...]


def get_camera_slots(
    *,
    camera_model: str | None = None,
    recipe: models.FujifilmRecipe | None = None,
) -> CameraSlots:
    """
    Connect to the camera, read all custom slot states, and disconnect.

    Args:
        camera_model: The camera model, when the caller already learned it (e.g.
                      from an earlier read), so the strategy can be resolved
                      without rediscovering it. When None, the model is read from
                      the connected device.
        recipe:       When given, the read also computes per-slot push feasibility
                      for this recipe and the fields the model would drop.

    Returns:
        A CameraSlots. ``slots`` is in slot order (index 1..N) and empty for a
        camera with no custom slots.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    return _read_model_and_slots(camera_model, recipe)


def get_camera_model_and_slots(
    *,
    camera_model: str | None = None,
    recipe: models.FujifilmRecipe | None = None,
) -> CameraSlots:
    """
    Connect to the camera, read its model name and all custom slot states, then
    disconnect.

    Same lifecycle, feasibility behaviour and error contract as
    :func:`get_camera_slots`; used where the caller also headlines which camera it
    is talking to (e.g. the collection push modal). Reading the model costs
    nothing extra on the open connection.

    Args:
        camera_model: See :func:`get_camera_slots`.
        recipe:       See :func:`get_camera_slots`.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    return _read_model_and_slots(camera_model, recipe)


def _read_model_and_slots(
    camera_model: str | None, recipe: models.FujifilmRecipe | None
) -> CameraSlots:
    device = device_config.get_device()
    device.connect()
    try:
        camera_model = camera_model or device.camera_name
        strategy = strategies.get_strategy(camera_model)
        slot_count = camera_queries.custom_slot_count(camera_model)
        states = strategy.read_slots(device, slot_count=slot_count)
        if recipe is None:
            return CameraSlots(camera_model, states, [], ())
        recipe_data = recipe_queries.recipe_from_db(recipe=recipe)
        plan = strategy.plan_feasibility(device, recipe_data, slot_count=slot_count)
        return CameraSlots(camera_model, states, plan.slots, plan.dropped_fields)
    finally:
        device.disconnect()
