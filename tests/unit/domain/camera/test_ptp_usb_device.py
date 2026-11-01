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
from src.domain.camera.ptp_usb_device import PTPUSBDevice
from src.domain.settings import queries as settings_queries


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

        assert send_mock.call_count == settings_queries.get_camera_max_retries()

    def test_publishes_read_retry_event_on_transient_failure(self):
        device = _make_device()
        good_data = _data_for_uint16(7)

        with (
            patch.object(
                device,
                "_send",
                MagicMock(side_effect=[CameraConnectionError("timeout"), None]),
            ),
            patch.object(device, "_recv_data", return_value=good_data),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(device, "_check_rc"),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device._get_prop_with_retry(0xD192)

        assert any(
            call.kwargs.get("event_type") == camera_events.PTP_READ_RETRY
            for call in mock_publish.call_args_list
        )


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


# ---------------------------------------------------------------------------
# _open_session (retried, so a transient timeout on the first exchange of a
# push does not abort the whole recipe)
# ---------------------------------------------------------------------------

_RC_SESSION_ALREADY = 0x201E


class TestOpenSessionRetry:

    def test_succeeds_on_first_attempt(self):
        device = _make_device()
        send_mock = MagicMock()

        with (
            patch.object(device, "_send", send_mock),
            patch.object(device, "_recv_response", return_value=_ok_response()),
        ):
            device._open_session()

        assert send_mock.call_count == 1

    def test_retries_transport_failure_then_succeeds(self):
        device = _make_device()
        send_mock = MagicMock(side_effect=[CameraConnectionError("timeout"), None])

        with (
            patch.object(device, "_send", send_mock),
            patch.object(device, "_recv_response", return_value=_ok_response()),
        ):
            device._open_session()

        assert send_mock.call_count == 2

    def test_session_already_open_is_treated_as_success(self):
        device = _make_device()

        with (
            patch.object(device, "_send"),
            patch.object(device, "_recv_response", return_value=(_RC_SESSION_ALREADY, [])),
        ):
            device._open_session()  # must not raise

    def test_bad_response_code_is_not_retried(self):
        device = _make_device()
        send_mock = MagicMock()

        with (
            patch.object(device, "_send", send_mock),
            patch.object(device, "_recv_response", return_value=(0x2019, [])),
        ):
            with pytest.raises(CameraConnectionError, match="OpenSession"):
                device._open_session()

        assert send_mock.call_count == 1

    def test_raises_after_exhausting_all_retries(self):
        device = _make_device()
        send_mock = MagicMock(side_effect=CameraConnectionError("USB dead"))

        with patch.object(device, "_send", send_mock):
            with pytest.raises(CameraConnectionError):
                device._open_session()

        assert send_mock.call_count == settings_queries.get_camera_max_retries()

    def test_publishes_read_retry_event_on_transport_failure(self):
        device = _make_device()

        with (
            patch.object(
                device,
                "_send",
                MagicMock(side_effect=[CameraConnectionError("timeout"), None]),
            ),
            patch.object(device, "_recv_response", return_value=_ok_response()),
            patch.object(camera_events, "publish_event") as mock_publish,
        ):
            device._open_session()

        assert any(
            call.kwargs.get("event_type") == camera_events.PTP_READ_RETRY
            for call in mock_publish.call_args_list
        )


# ---------------------------------------------------------------------------
# Whole-backup transport: get_backup / restore_backup / _object_op
# ---------------------------------------------------------------------------

_OC_GET_OBJECT = 0x1009
_OC_SEND_OBJECT_INFO = 0x100C
_PTP_DATA = 0x0002
_PTP_RESPONSE = 0x0003


def _data_container(code: int, payload: bytes, tx: int = 1) -> bytes:
    return struct.pack("<IHHI", 12 + len(payload), _PTP_DATA, code, tx) + payload


def _response_container(rc: int = _RC_OK, tx: int = 1) -> bytes:
    return struct.pack("<IHHI", 12, _PTP_RESPONSE, rc, tx)


class TestObjectOp:
    def test_strips_header_and_returns_payload_then_reads_response(self):
        device = _make_device()
        blob = b"X-T2-BACKUP-BYTES"
        device._ep_in = MagicMock()
        device._ep_in.read.side_effect = [_data_container(_OC_GET_OBJECT, blob), _response_container()]
        with patch.object(device, "_send"):
            rc, payload = device._object_op(_OC_GET_OBJECT, 0)
        assert rc == _RC_OK
        assert payload == blob

    def test_rejects_a_data_phase_that_spans_reads(self):
        device = _make_device()
        # Declare a longer length than the bytes actually returned.
        truncated = struct.pack("<IHHI", 12 + 9000, _PTP_DATA, _OC_GET_OBJECT, 1) + b"short"
        device._ep_in = MagicMock()
        device._ep_in.read.side_effect = [truncated]
        with patch.object(device, "_send"):
            with pytest.raises(CameraConnectionError):
                device._object_op(_OC_GET_OBJECT, 0)


class TestGetBackup:
    def test_returns_the_blob(self):
        device = _make_device()
        blob = b"BACKUP" * 100
        with patch.object(device, "_object_op", side_effect=[(_RC_OK, b"objinfo"), (_RC_OK, blob)]):
            assert device.get_backup() == blob

    def test_retries_then_succeeds(self):
        device = _make_device()
        blob = b"BACKUP"
        with patch.object(
            device,
            "_object_op",
            side_effect=[CameraConnectionError("timeout"), (_RC_OK, b"objinfo"), (_RC_OK, blob)],
        ):
            assert device.get_backup() == blob

    def test_raises_after_all_retries(self):
        device = _make_device()
        with patch.object(device, "_object_op", side_effect=CameraConnectionError("gone")):
            with pytest.raises(CameraConnectionError):
                device.get_backup()


class TestRestoreBackup:
    def test_success_restores_usb_timeout_afterwards(self):
        from src.domain.camera.ptp_device import CameraWriteError  # noqa: F401 (symmetry)

        device = _make_device()
        before = device._usb_timeout_ms
        with (
            patch.object(device, "_send"),
            patch.object(device, "_read_restore_ack", side_effect=[_RC_OK, _RC_OK]),
        ):
            device.restore_backup(b"\x00" * 5660)
        assert device._usb_timeout_ms == before

    def test_raises_write_error_when_a_step_is_rejected(self):
        from src.domain.camera.ptp_device import CameraWriteError

        device = _make_device()
        with (
            patch.object(device, "_send"),
            patch.object(device, "_read_restore_ack", side_effect=[0x2005]),
        ):
            with pytest.raises(CameraWriteError):
                device.restore_backup(b"\x00" * 5660)

    def test_lost_ack_propagates_as_restore_ack_timeout(self):
        from src.domain.camera.ptp_device import RestoreAckTimeout

        device = _make_device()
        with (
            patch.object(device, "_send"),
            patch.object(device, "_read_restore_ack", side_effect=RestoreAckTimeout("no ack")),
        ):
            with pytest.raises(RestoreAckTimeout):
                device.restore_backup(b"\x00" * 5660)
