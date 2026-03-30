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
from django.conf import settings as _settings

from src.domain.camera import device_config
from src.domain.camera import ptp_device
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
    device = device_config.get_device()
    device.connect()
    try:
        slot_count = camera_queries.custom_slot_count(device.camera_name)
        states: list[camera_queries.SlotState] = []
        for idx in range(1, slot_count + 1):
            if idx > 1:
                time.sleep(_settings.CAMERA_INTER_SLOT_DELAY_S)
            _set_cursor_with_retry(device, idx)
            time.sleep(_settings.CAMERA_POST_CURSOR_DELAY_S)
            name = _read_str_with_retry(device, constants.PROP_SLOT_NAME)
            film_sim = _read_int_with_retry(device, constants.CUSTOM_SLOT_CODES["FilmSimulation"])
            states.append(camera_queries.SlotState(index=idx, name=name, film_sim_ptp=film_sim))
        return states
    finally:
        device.disconnect()


def _retry(fn: Callable[[], _T]) -> _T:
    """
    Call *fn* up to _settings.CAMERA_MAX_RETRIES times, sleeping with exponential
    back-off between attempts.  Only retries on CameraConnectionError.
    Any other exception (e.g. CameraWriteError) propagates immediately.
    """
    last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError("no retries attempted")
    for attempt in range(1, _settings.CAMERA_MAX_RETRIES + 1):
        if attempt > 1:
            time.sleep(_settings.CAMERA_RETRY_BACKOFF_S * (2 ** (attempt - 2)))
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
    """Read a string property, retrying on transport failures."""
    return _retry(lambda: device.get_property_string(code))


def _read_int_with_retry(device: ptp_device.PTPDevice, code: int) -> int:
    """Read an integer property, retrying on transport failures."""
    return _retry(lambda: device.get_property_int(code))
