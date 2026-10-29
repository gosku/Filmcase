"""
Application-layer use case for reading all custom slot states from a camera.

Orchestrates the connection lifecycle (connect → read → disconnect) and resolves
the per-model strategy that performs the read.  The read algorithm itself,
including its retry behaviour, lives in the strategy.

The concrete device class is read from settings.PTP_DEVICE via device_config.
"""
from __future__ import annotations

from src.domain.camera import device_config
from src.domain.camera import queries as camera_queries
from src.domain.camera import strategies


def get_camera_slots(*, known_model: str | None = None) -> list[camera_queries.SlotState]:
    """
    Connect to the camera, read all custom slot states, and disconnect.

    Args:
        known_model: The camera model, when the caller already learned it (e.g.
                     from an earlier read), so the strategy can be resolved
                     without rediscovering it.  When None, the model is read
                     from the connected device.

    Returns:
        List of SlotState, one per slot, in slot order (index 1..N).
        Returns an empty list for cameras with no custom slots.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    _, states = _read_model_and_slots(known_model)
    return states


def get_camera_model_and_slots(
    *, known_model: str | None = None
) -> tuple[str, list[camera_queries.SlotState]]:
    """
    Connect to the camera, read its model name and all custom slot states, then
    disconnect.

    Same lifecycle and error contract as :func:`get_camera_slots`; used where the
    caller also needs to show which camera it is talking to (e.g. the collection
    push modal header).  Reading the model costs nothing extra on the open
    connection.

    Args:
        known_model: See :func:`get_camera_slots`.

    Returns:
        A ``(camera_name, slots)`` pair. ``slots`` is empty for a camera with no
        custom slots.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    return _read_model_and_slots(known_model)


def _read_model_and_slots(known_model: str | None) -> tuple[str, list[camera_queries.SlotState]]:
    device = device_config.get_device()
    device.connect()
    try:
        camera_name = known_model or device.camera_name
        strategy = strategies.get_strategy(camera_name)
        slot_count = camera_queries.custom_slot_count(camera_name)
        states = strategy.read_slots(device, slot_count=slot_count)
        return camera_name, states
    finally:
        device.disconnect()
