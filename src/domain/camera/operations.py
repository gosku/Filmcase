"""
Domain-layer write helpers for Fujifilm PTP/USB camera communication.

Timing is controlled via the dynamic settings (CAMERA_PRE_WRITE_DELAY_S,
CAMERA_POST_WRITE_DELAY_S, CAMERA_MAX_RETRIES, CAMERA_RETRY_BACKOFF_S), read
through src.domain.settings.queries.

These helpers are consumed by the application-layer use case
push_recipe_to_camera.
"""

from __future__ import annotations

import logging
import time

from src.domain.camera import events
from src.domain.camera import ptp_device
from src.domain.settings import queries as settings_queries

logger = logging.getLogger(__name__)


def set_prop_with_retry(device: ptp_device.PTPDevice, code: int, value: str | int) -> None:
    """
    Write a single property, retrying on transport failures with exponential back-off.

    Accepts both string and integer values; dispatches to the appropriate
    device method based on type.

    Publishes camera.ptp_write.failed for every failed attempt and
    camera.ptp_write.succeeded when the write completes successfully.

    Raises:
        CameraWriteError: The camera actively rejected the write (non-zero rc).
                          No retry is attempted; the camera is still reachable.
        CameraConnectionError: Transport failed on every attempt.
    """
    prop_hex = f"0x{code:04X}"
    camera_connection_error = False
    write_failed = False
    failed_rc: int = 0
    max_retries = settings_queries.get_camera_max_retries()
    retry_backoff_s = settings_queries.get_camera_retry_backoff_s()

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            time.sleep(retry_backoff_s * (2 ** (attempt - 2)))

        camera_connection_error = False

        try:
            if isinstance(value, str):
                rc = device.set_property_string(code, value)
            else:
                rc = device.set_property_int(code, value)
        except ptp_device.CameraConnectionError as exc:
            camera_connection_error = True
            events.publish_event(
                event_type=events.PTP_WRITE_FAILED,
                description=(
                    f"{prop_hex} = {value!r}: {exc} "
                    f"(attempt {attempt}/{max_retries})"
                ),
            )
            continue

        if rc != 0 and not camera_connection_error:
            write_failed = True
            failed_rc = rc
            events.publish_event(
                event_type=events.PTP_WRITE_FAILED,
                description=f"{prop_hex} = {value!r}: camera rejected write (rc={rc:#x})",
            )
            break

        events.publish_event(
            event_type=events.PTP_WRITE_SUCCEEDED,
            description=f"{prop_hex} = {value!r}",
        )
        return

    if camera_connection_error:
        raise ptp_device.CameraConnectionError(
            f"Camera unreachable after {max_retries} attempts "
            f"writing {prop_hex} = {value!r}"
        )
    if write_failed:
        raise ptp_device.CameraWriteError(code, value, failed_rc)


def verify_written_properties(
    device: ptp_device.PTPDevice,
    written: list[tuple[int, str | int]],
) -> list[int]:
    """
    Read back each successfully written property and check its value.

    Returns a list of PTP codes where the read-back value did not match.
    """
    mismatched: list[int] = []
    for code, expected in written:
        time.sleep(settings_queries.get_camera_pre_write_delay_s())
        try:
            if isinstance(expected, str):
                actual: str | int = device.get_property_string(code)
                match = actual == expected
            else:
                actual = device.get_property_int(code)
                # Compare lower 16 bits — camera returns uint16; expected may be int16.
                match = (actual & 0xFFFF) == (expected & 0xFFFF)

            if not match:
                logger.warning(
                    "Verification failed for 0x%04X: wrote %r, read back %r",
                    code,
                    expected,
                    actual,
                )
                mismatched.append(code)
        except ptp_device.CameraConnectionError:
            logger.warning(
                "Verification read failed for 0x%04X (camera error)", code
            )
            mismatched.append(code)
    return mismatched
