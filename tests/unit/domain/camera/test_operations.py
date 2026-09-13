import pytest

from src.data.camera import constants
from src.domain.camera import operations
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError

_CURSOR = constants.PROP_SLOT_CURSOR


class _ScriptedCursorDevice:
    """
    Minimal device whose set_property_uint16 follows a scripted list of outcomes.

    Each outcome is either an int response code to return, or an Exception
    instance to raise. Lets a test drive the retry loop deterministically.
    """

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def set_property_uint16(self, code: int, value: int) -> int:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, int)
        return outcome


class TestSetCursorWithRetry:
    def test_succeeds_on_first_attempt(self, settings) -> None:
        settings.CAMERA_MAX_RETRIES = 3
        device = _ScriptedCursorDevice([0])

        operations.set_cursor_with_retry(device, _CURSOR, 1)

        assert device.calls == 1

    def test_retries_transport_failure_then_succeeds(self, settings) -> None:
        settings.CAMERA_MAX_RETRIES = 3
        device = _ScriptedCursorDevice(
            [CameraConnectionError("timeout"), CameraConnectionError("timeout"), 0]
        )

        operations.set_cursor_with_retry(device, _CURSOR, 1)

        assert device.calls == 3

    def test_raises_connection_error_after_exhausting_attempts(self, settings) -> None:
        settings.CAMERA_MAX_RETRIES = 3
        device = _ScriptedCursorDevice([CameraConnectionError("timeout")] * 3)

        with pytest.raises(CameraConnectionError):
            operations.set_cursor_with_retry(device, _CURSOR, 1)

        assert device.calls == 3

    def test_rejection_raises_write_error_without_retrying(self, settings) -> None:
        settings.CAMERA_MAX_RETRIES = 3
        device = _ScriptedCursorDevice([0x2005])

        with pytest.raises(CameraWriteError) as excinfo:
            operations.set_cursor_with_retry(device, _CURSOR, 1)

        # A rejection is the camera's decision; retrying would not change it.
        assert device.calls == 1
        assert excinfo.value.rc == 0x2005
