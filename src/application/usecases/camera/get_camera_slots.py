"""
Application-layer use case for reading all custom slot states from a camera.

Orchestrates the full lifecycle: connect → read slots → disconnect.
Implements retry logic with exponential back-off for transient transport failures.

The concrete device class is read from settings.PTP_DEVICE, which may be either
a dotted-path string (e.g. "src.domain.camera.ptp_usb_device.PTPUSBDevice") or
a callable (class or factory function) that returns an unconnected PTPDevice.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from src.data.camera import constants

from src.domain.camera import device_config
from src.domain.camera import ptp_device
from src.domain.settings import queries as settings_queries
from src.domain.camera import queries as camera_queries

_T = TypeVar("_T")


def get_camera_slots() -> list[camera_queries.SlotState]:
    """
    Connect to the camera, read all custom slot states, and disconnect.

    The device class is taken from settings.PTP_DEVICE (via device_config).

    Returns:
        List of SlotState, one per slot, in slot order (index 1..N).
        Returns an empty list for cameras with no custom slots.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    _, states = _read_model_and_slots()
    return states


def get_camera_model_and_slots() -> tuple[str, list[camera_queries.SlotState]]:
    """
    Connect to the camera, read its model name and all custom slot states, then
    disconnect.

    Same lifecycle and error contract as :func:`get_camera_slots`; used where the
    caller also needs to show which camera it is talking to (e.g. the collection
    push modal header). Reading the model costs nothing extra on the open
    connection.

    Returns:
        A ``(camera_name, slots)`` pair. ``slots`` is empty for a camera with no
        custom slots.

    Raises:
        CameraConnectionError: If the camera is unreachable or a read fails after
                               all retries.
        CameraWriteError:      If the camera rejects a slot cursor write.
    """
    return _read_model_and_slots()


def _read_model_and_slots() -> tuple[str, list[camera_queries.SlotState]]:
    device = device_config.get_device()
    device.connect()
    try:
        camera_name = device.camera_name
        slot_count = camera_queries.custom_slot_count(camera_name)
        states: list[camera_queries.SlotState] = []
        for idx in range(1, slot_count + 1):
            if idx > 1:
                time.sleep(settings_queries.get_camera_inter_slot_delay_s())
            _set_cursor_with_retry(device, idx)
            time.sleep(settings_queries.get_camera_post_cursor_delay_s())
            name = _read_str_with_retry(device, constants.PROP_SLOT_NAME)
            film_sim = _read_int_with_retry(device, constants.CUSTOM_SLOT_CODES["FilmSimulation"])
            states.append(camera_queries.SlotState(index=idx, name=name, film_sim_ptp=film_sim))
        return camera_name, states
    finally:
        device.disconnect()


def _retry(fn: Callable[[], _T]) -> _T:
    """
    Call *fn* up to CAMERA_MAX_RETRIES times, sleeping with exponential
    back-off between attempts.  Only retries on CameraConnectionError.
    Any other exception (e.g. CameraWriteError) propagates immediately.
    """
    last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError("no retries attempted")
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

    Raises:
        CameraConnectionError: If the cursor write fails after all retries.
        CameraWriteError:      If the camera rejects the cursor write (non-zero rc).
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
