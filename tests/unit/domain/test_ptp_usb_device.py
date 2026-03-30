"""
Unit tests for PTPUSBDevice retry logic.

These tests patch the low-level _send / _recv_data / _recv_response helpers
so no real USB hardware is required.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

from src.domain.camera import events as camera_events
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.ptp_usb_device import (
    PTPUSBDevice,
    _PROP_MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RC_OK = 0x2001


def _ok_response() -> tuple[int, list]:
    return (_RC_OK, [])


def _data_for_uint16(value: int) -> bytes:
    """Build a minimal 14-byte PTP data container wrapping a uint16 payload."""
    payload = struct.pack("<H", value & 0xFFFF)
    header = struct.pack("<IHHI", 12 + len(payload), 0x0002, 0x1015, 1)
    return header + payload


def _make_device() -> PTPUSBDevice:
    """Return an uninitialised PTPUSBDevice (no USB connection attempted)."""
    return PTPUSBDevice()


# ---------------------------------------------------------------------------
# _get_prop_with_retry
# ---------------------------------------------------------------------------

class TestGetPropWithRetry:

    def test_succeeds_on_first_attempt(self):
        device = _make_device()
        expected = _data_for_uint16(42)

        with (
            patch.object(device, "_send"),
            patch.object(device, "_recv_data", return_value=expected),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(device, "_check_rc"),
        ):
            result = device._get_prop_with_retry(0xD192)

        assert result == expected

    def test_retries_after_transient_error_then_succeeds(self):
        device = _make_device()
        good_data = _data_for_uint16(7)

        send_mock = MagicMock(side_effect=[CameraConnectionError("timeout"), None])

        with (
            patch.object(device, "_send", send_mock),
            patch.object(device, "_recv_data", return_value=good_data),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(device, "_check_rc"),
        ):
            result = device._get_prop_with_retry(0xD192)

        assert result == good_data
        assert send_mock.call_count == 2

    def test_raises_after_exhausting_all_retries(self):
        device = _make_device()

        with patch.object(device, "_send", side_effect=CameraConnectionError("USB dead")):
            with pytest.raises(CameraConnectionError, match="USB dead"):
                device._get_prop_with_retry(0xD192)

    def test_retry_count_equals_prop_max_retries(self):
        device = _make_device()
        send_mock = MagicMock(side_effect=CameraConnectionError("fail"))

        with patch.object(device, "_send", send_mock):
            with pytest.raises(CameraConnectionError):
                device._get_prop_with_retry(0xD192)

        assert send_mock.call_count == _PROP_MAX_RETRIES


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------

class TestEventPublishing:

    def test_get_property_int_publishes_read_succeeded(self):
        device = _make_device()

        with (
            patch.object(device, "_get_prop_with_retry", return_value=_data_for_uint16(42)),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device.get_property_int(0xD192)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            prop="0xD192",
            value=42,
        )

    def test_get_property_int_publishes_read_failed_and_reraises(self):
        device = _make_device()
        err = CameraConnectionError("USB dead")

        with (
            patch.object(device, "_get_prop_with_retry", side_effect=err),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            with pytest.raises(CameraConnectionError, match="USB dead"):
                device.get_property_int(0xD192)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_FAILED,
            prop="0xD192",
            error="USB dead",
        )

    def test_get_property_string_publishes_read_succeeded(self):
        device = _make_device()
        # PTP string encoding of "A": numChars=2, [0x41, 0x00] (char + NUL)
        ptp_str = struct.pack("<B2H", 2, 0x41, 0x00)
        data = struct.pack("<IHHI", 12 + len(ptp_str), 0x0002, 0x1015, 1) + ptp_str

        with (
            patch.object(device, "_get_prop_with_retry", return_value=data),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device.get_property_string(0xD18D)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            prop="0xD18D",
            value="A",
        )

    def test_get_property_string_publishes_read_failed_and_reraises(self):
        device = _make_device()
        err = CameraConnectionError("timeout")

        with (
            patch.object(device, "_get_prop_with_retry", side_effect=err),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            with pytest.raises(CameraConnectionError, match="timeout"):
                device.get_property_string(0xD18D)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_FAILED,
            prop="0xD18D",
            error="timeout",
        )

    def test_set_property_int_publishes_write_succeeded(self):
        device = _make_device()

        with (
            patch.object(device, "_send"),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device.set_property_int(0xD192, 5)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_WRITE_SUCCEEDED,
            prop="0xD192",
        )

    def test_set_property_int_publishes_write_failed(self):
        device = _make_device()
        bad_rc = 0x2005

        with (
            patch.object(device, "_send"),
            patch.object(device, "_recv_response", return_value=(bad_rc, [])),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            rc = device.set_property_int(0xD192, 5)

        assert rc == bad_rc
        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_WRITE_FAILED,
            prop="0xD192",
            rc="0x2005",
        )
