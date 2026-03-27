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

from src.data.camera import constants
from src.domain.camera.device_config import get_device
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError, PTPDevice
from src.domain.camera.queries import SlotState, custom_slot_count

_MAX_RETRIES = 3
_RETRY_BACKOFF_S = 0.2   # base back-off; doubles each attempt (0.2 s, 0.4 s)
_POST_CURSOR_DELAY_S = 0.05   # 50 ms after setting slot cursor
_INTER_SLOT_DELAY_S = 0.05    # 50 ms between slots


def get_camera_slots() -> list[SlotState]:
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
    device = get_device()
    device.connect()
    try:
        slot_count = custom_slot_count(device.camera_name)
        states: list[SlotState] = []
        for idx in range(1, slot_count + 1):
            if idx > 1:
                time.sleep(_INTER_SLOT_DELAY_S)
            _set_cursor_with_retry(device, idx)
            time.sleep(_POST_CURSOR_DELAY_S)
            name = _read_str_with_retry(device, constants.PROP_SLOT_NAME)
            film_sim = _read_int_with_retry(device, constants.CUSTOM_SLOT_CODES["FilmSimulation"])
            states.append(SlotState(index=idx, name=name, film_sim_ptp=film_sim))
        return states
    finally:
        device.disconnect()


def _set_cursor_with_retry(device: PTPDevice, slot_index: int) -> None:
    """
    Write the slot cursor, retrying on transport failures.

    Raises:
        CameraConnectionError: If the cursor write fails after all retries.
        CameraWriteError:      If the camera rejects the cursor write (non-zero rc).
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        if attempt > 1:
            time.sleep(_RETRY_BACKOFF_S * (2 ** (attempt - 2)))
        try:
            rc = device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot_index)
            if rc != 0:
                raise CameraWriteError(constants.PROP_SLOT_CURSOR, slot_index, rc)
            return
        except CameraConnectionError:
            if attempt == _MAX_RETRIES:
                raise


def _read_str_with_retry(device: PTPDevice, code: int) -> str:
    """
    Read a string property, retrying on transport failures.

    Raises:
        CameraConnectionError: If the read fails after all retries.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        if attempt > 1:
            time.sleep(_RETRY_BACKOFF_S * (2 ** (attempt - 2)))
        try:
            return device.get_property_string(code)
        except CameraConnectionError:
            if attempt == _MAX_RETRIES:
                raise


def _read_int_with_retry(device: PTPDevice, code: int) -> int:
    """
    Read an integer property, retrying on transport failures.

    Raises:
        CameraConnectionError: If the read fails after all retries.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        if attempt > 1:
            time.sleep(_RETRY_BACKOFF_S * (2 ** (attempt - 2)))
        try:
            return device.get_property_int(code)
        except CameraConnectionError:
            if attempt == _MAX_RETRIES:
                raise
