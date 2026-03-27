"""
Integration tests for the get_camera_slots use case.

Uses FakePTPDevice via settings.PTP_DEVICE (see conftest autouse fixture).
"""
from unittest.mock import patch

import pytest

from src.application.usecases.camera.get_camera_slots import get_camera_slots
from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from src.domain.camera.queries import SlotState
from tests.fakes import FakePTPDevice


def _run():
    """Run the use case with time.sleep patched out."""
    with patch("src.application.usecases.camera.get_camera_slots.time.sleep"):
        return get_camera_slots()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestGetCameraSlotsSuccess:
    def test_returns_one_state_per_slot(self):
        # autouse fixture → FakePTPDevice(camera_name="X-S10") → 4 slots
        states = _run()
        assert len(states) == 4

    def test_slot_indices_are_one_based(self):
        states = _run()
        assert [s.index for s in states] == [1, 2, 3, 4]

    def test_slot_names_reflect_stored_values(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            string_values={constants.PROP_SLOT_NAME: "My Slot"}
        )
        states = _run()
        assert all(s.name == "My Slot" for s in states)

    def test_film_sim_ptp_reflects_stored_value(self, settings):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(int_values={film_sim_code: 11})
        states = _run()
        assert all(s.film_sim_ptp == 11 for s in states)
        assert all(s.film_sim_name == "Classic Chrome" for s in states)

    def test_returns_empty_list_for_unknown_camera(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="UNKNOWN_CAM")
        states = _run()
        assert states == []

    def test_connect_and_disconnect_are_called(self, settings):
        class _TrackingDevice(FakePTPDevice):
            def __init__(self):
                super().__init__()
                self.connected = False
                self.disconnected = False

            def connect(self):
                self.connected = True

            def disconnect(self):
                self.disconnected = True

        device = _TrackingDevice()
        settings.PTP_DEVICE = lambda: device
        _run()
        assert device.connected
        assert device.disconnected


# ---------------------------------------------------------------------------
# Disconnect always called
# ---------------------------------------------------------------------------


class TestGetCameraSlotsAlwaysDisconnects:
    def test_disconnect_called_on_camera_connection_error(self, settings):
        class _TrackingDevice(FakePTPDevice):
            def __init__(self):
                super().__init__(
                    set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
                )
                self.disconnected = False

            def disconnect(self):
                self.disconnected = True

        device = _TrackingDevice()
        settings.PTP_DEVICE = lambda: device
        with pytest.raises(CameraConnectionError):
            _run()
        assert device.disconnected

    def test_disconnect_called_on_camera_write_error(self, settings):
        class _TrackingDevice(FakePTPDevice):
            def __init__(self):
                super().__init__(
                    set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
                )
                self.disconnected = False

            def disconnect(self):
                self.disconnected = True

        device = _TrackingDevice()
        settings.PTP_DEVICE = lambda: device
        with pytest.raises(CameraWriteError):
            _run()
        assert device.disconnected


# ---------------------------------------------------------------------------
# Slot cursor write errors
# ---------------------------------------------------------------------------


class TestSetCursorErrors:
    def test_camera_connection_error_raised_after_retries(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _run()

    def test_camera_write_error_raised_immediately_on_rejection(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )
        with pytest.raises(CameraWriteError) as exc_info:
            _run()
        assert exc_info.value.code == constants.PROP_SLOT_CURSOR

    def test_cursor_retried_before_raising(self, settings):
        call_count = 0

        class _CountingDevice(FakePTPDevice):
            def set_property_uint16(self, code, value):
                nonlocal call_count
                if code == constants.PROP_SLOT_CURSOR:
                    call_count += 1
                    raise CameraConnectionError("USB timeout")
                return super().set_property_uint16(code, value)

        settings.PTP_DEVICE = _CountingDevice
        with pytest.raises(CameraConnectionError):
            _run()
        assert call_count == 3  # _MAX_RETRIES


# ---------------------------------------------------------------------------
# Slot name read errors
# ---------------------------------------------------------------------------


class TestReadNameErrors:
    def test_camera_connection_error_raised_after_retries(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            get_errors={constants.PROP_SLOT_NAME: CameraConnectionError("read timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _run()

    def test_name_read_retried_before_raising(self, settings):
        call_count = 0

        class _CountingDevice(FakePTPDevice):
            def get_property_string(self, code):
                nonlocal call_count
                if code == constants.PROP_SLOT_NAME:
                    call_count += 1
                    raise CameraConnectionError("read timeout")
                return super().get_property_string(code)

        settings.PTP_DEVICE = _CountingDevice
        with pytest.raises(CameraConnectionError):
            _run()
        assert call_count == 3  # _MAX_RETRIES


# ---------------------------------------------------------------------------
# Film sim read errors
# ---------------------------------------------------------------------------


class TestReadFilmSimErrors:
    def test_camera_connection_error_raised_after_retries(self, settings):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            get_errors={film_sim_code: CameraConnectionError("read timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _run()

    def test_film_sim_read_retried_before_raising(self, settings):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        call_count = 0

        class _CountingDevice(FakePTPDevice):
            def get_property_int(self, code):
                nonlocal call_count
                if code == film_sim_code:
                    call_count += 1
                    raise CameraConnectionError("read timeout")
                return super().get_property_int(code)

        settings.PTP_DEVICE = _CountingDevice
        with pytest.raises(CameraConnectionError):
            _run()
        assert call_count == 3  # _MAX_RETRIES
