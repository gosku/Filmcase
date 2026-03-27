"""
Unit tests for PTPUSBDevice retry logic and post-read delay.

These tests patch the low-level _send / _recv_data / _recv_response helpers
so no real USB hardware is required.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, call, patch

import pytest

from src.domain.camera import events as camera_events
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.ptp_usb_device import (
    PTPUSBDevice,
    _PROP_MAX_RETRIES,
    _PROP_READ_DELAY,
    _RETRY_BACKOFF,
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
            patch("src.domain.camera.ptp_usb_device.time.sleep"),
        ):
            result = device._get_prop_with_retry(0xD192)

        assert result == good_data
        assert send_mock.call_count == 2

    def test_raises_after_exhausting_all_retries(self):
        device = _make_device()

        with (
            patch.object(device, "_send", side_effect=CameraConnectionError("USB dead")),
            patch("src.domain.camera.ptp_usb_device.time.sleep"),
        ):
            with pytest.raises(CameraConnectionError, match="USB dead"):
                device._get_prop_with_retry(0xD192)

    def test_retry_count_equals_prop_max_retries(self):
        device = _make_device()
        send_mock = MagicMock(side_effect=CameraConnectionError("fail"))

        with (
            patch.object(device, "_send", send_mock),
            patch("src.domain.camera.ptp_usb_device.time.sleep"),
        ):
            with pytest.raises(CameraConnectionError):
                device._get_prop_with_retry(0xD192)

        assert send_mock.call_count == _PROP_MAX_RETRIES

    def test_no_sleep_before_first_attempt(self):
        device = _make_device()

        sleep_mock = MagicMock()
        with (
            patch.object(device, "_send"),
            patch.object(device, "_recv_data", return_value=_data_for_uint16(0)),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(device, "_check_rc"),
            patch("src.domain.camera.ptp_usb_device.time.sleep", sleep_mock),
        ):
            device._get_prop_with_retry(0xD192)

        sleep_mock.assert_not_called()

    def test_backoff_sleep_on_retry(self):
        device = _make_device()
        good_data = _data_for_uint16(0)

        send_mock = MagicMock(side_effect=[CameraConnectionError("timeout"), None])
        sleep_mock = MagicMock()

        with (
            patch.object(device, "_send", send_mock),
            patch.object(device, "_recv_data", return_value=good_data),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(device, "_check_rc"),
            patch("src.domain.camera.ptp_usb_device.time.sleep", sleep_mock),
        ):
            device._get_prop_with_retry(0xD192)

        # First retry (attempt=1): sleep(_RETRY_BACKOFF * 2**0 = _RETRY_BACKOFF)
        sleep_mock.assert_called_once_with(_RETRY_BACKOFF)


# ---------------------------------------------------------------------------
# get_property_int / get_property_string — post-read delay
# ---------------------------------------------------------------------------

class TestPostReadDelay:

    def test_get_property_int_sleeps_after_read(self):
        device = _make_device()
        sleep_mock = MagicMock()

        with (
            patch.object(device, "_get_prop_with_retry", return_value=_data_for_uint16(5)),
            patch("src.domain.camera.ptp_usb_device.time.sleep", sleep_mock),
            patch.object(camera_events, "publish_event"),
        ):
            device.get_property_int(0xD192)

        sleep_mock.assert_called_once_with(_PROP_READ_DELAY)

    def test_get_property_string_sleeps_after_read(self):
        device = _make_device()
        sleep_mock = MagicMock()

        # Minimal PTP string: length byte = 0 (empty string), no chars, no null
        empty_ptp_string = struct.pack("<IHHI", 13, 0x0002, 0x1015, 1) + b"\x00"

        with (
            patch.object(device, "_get_prop_with_retry", return_value=empty_ptp_string),
            patch("src.domain.camera.ptp_usb_device.time.sleep", sleep_mock),
            patch.object(camera_events, "publish_event"),
        ):
            device.get_property_string(0xD18D)

        sleep_mock.assert_called_once_with(_PROP_READ_DELAY)


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------

class TestEventPublishing:

    def test_get_property_int_publishes_read_succeeded(self):
        device = _make_device()

        with (
            patch.object(device, "_get_prop_with_retry", return_value=_data_for_uint16(42)),
            patch("src.domain.camera.ptp_usb_device.time.sleep"),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device.get_property_int(0xD192)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            params={"prop": "0xD192", "value": 42},
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
            params={"prop": "0xD192", "error": "USB dead"},
        )

    def test_get_property_string_publishes_read_succeeded(self):
        device = _make_device()
        # PTP string encoding of "A": numChars=2, [0x41, 0x00] (char + NUL)
        ptp_str = struct.pack("<B2H", 2, 0x41, 0x00)
        data = struct.pack("<IHHI", 12 + len(ptp_str), 0x0002, 0x1015, 1) + ptp_str

        with (
            patch.object(device, "_get_prop_with_retry", return_value=data),
            patch("src.domain.camera.ptp_usb_device.time.sleep"),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device.get_property_string(0xD18D)

        mock_publish.assert_called_once_with(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            params={"prop": "0xD18D", "value": "A"},
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
            params={"prop": "0xD18D", "error": "timeout"},
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
            params={"prop": "0xD192"},
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
            params={"prop": "0xD192", "rc": "0x2005"},
        )
