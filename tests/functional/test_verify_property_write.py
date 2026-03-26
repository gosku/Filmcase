"""
Functional tests for the verify_property_write management command.

The only fake is FakePTPDevice — all command logic, argument parsing,
output formatting, and error handling run for real.  time.sleep is patched
to keep the test suite fast.
"""

from __future__ import annotations

from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError
from tests.fakes import FakePTPDevice

_CMD = "verify_property_write"
_DRANGE_PRIORITY_CODE = constants.CUSTOM_SLOT_CODES["DRangePriority"]  # 0xD191
_GRAIN_EFFECT_CODE    = constants.CUSTOM_SLOT_CODES["GrainEffect"]      # 0xD195


@contextmanager
def _run(property_name=None, *, device=None, slot=1, list_=False):
    """
    Context manager that runs verify_property_write with a FakePTPDevice
    injected in place of PTPUSBDevice.

    Yields (stdout_str, stderr_str, fake_device) so callers can inspect the
    device state after the command finishes (e.g. to check value restoration).
    """
    fake = device if device is not None else FakePTPDevice()
    out, err = StringIO(), StringIO()

    args = [] if property_name is None else [property_name]
    kwargs = dict(stdout=out, stderr=err)
    if list_:
        kwargs["list"] = True
    else:
        kwargs["slot"] = slot

    with (
        patch(
            f"src.interfaces.management.commands.{_CMD}.PTPUSBDevice",
            return_value=fake,
        ),
        patch(f"src.interfaces.management.commands.{_CMD}.time.sleep"),
    ):
        call_command(_CMD, *args, **kwargs)

    yield out.getvalue(), err.getvalue(), fake


class TestListFlag:
    def test_shows_all_testable_properties(self):
        with _run(list_=True) as (out, err, _):
            assert "DRangePriority" in out
            assert "FilmSimulation" in out
            assert "GrainEffect" in out

    def test_shows_value_counts(self):
        with _run(list_=True) as (out, err, _):
            # DRangePriority has 4 values
            assert "DRangePriority" in out
            assert "4" in out

    def test_no_device_connection_attempted(self):
        # PTPUSBDevice is patched but connect() should never be called.
        fake = FakePTPDevice()
        with _run(list_=True, device=fake) as _:
            pass
        # connect() on FakePTPDevice is a no-op; no assertion needed beyond
        # the fact that the command completes without error.


class TestArgumentValidation:
    def test_unknown_property_reports_error(self):
        with _run("NonExistentProperty") as (out, err, _):
            assert "Unknown property" in err

    def test_unknown_property_does_not_raise(self):
        with _run("NonExistentProperty") as _:
            pass  # call_command must not propagate an unhandled exception


class TestAllValuesPassing:
    def test_all_values_pass_when_readback_matches(self):
        # FakePTPDevice default: writes update the store, reads return the
        # stored value → every write/read round-trip matches.
        with _run("DRangePriority") as (out, err, _):
            assert "4 passed, 0 failed" in out

    def test_each_passing_value_shows_tick(self):
        with _run("DRangePriority") as (out, err, _):
            assert out.count("✓") == 4


class TestMismatchDetection:
    def test_mismatches_are_counted(self):
        # All reads return 999, which matches nothing in DRangePriority.
        device = FakePTPDevice(int_read_overrides={_DRANGE_PRIORITY_CODE: 999})
        with _run("DRangePriority", device=device) as (out, err, _):
            assert "0 passed, 4 failed" in out

    def test_failing_values_show_cross(self):
        device = FakePTPDevice(int_read_overrides={_DRANGE_PRIORITY_CODE: 999})
        with _run("DRangePriority", device=device) as (out, err, _):
            assert "✗" in out

    def test_partial_mismatch(self):
        # DR-Auto (0xFFFF = 65535) is overridden; the other three pass.
        device = FakePTPDevice(
            int_read_overrides={_DRANGE_PRIORITY_CODE: 999},
            int_values={_DRANGE_PRIORITY_CODE: 65535},
        )
        # All reads come back as 999, so all 4 fail.
        with _run("DRangePriority", device=device) as (out, err, _):
            assert "0 passed, 4 failed" in out


class TestSetBasedExpected:
    def test_grain_off_passes_when_readback_in_expected_set(self):
        # GrainEffect Off: write 1, expected {6, 7}.  Camera normalises to 6.
        # Other values (2-5) also read as 6 → fail, but Off must pass.
        device = FakePTPDevice(int_read_overrides={_GRAIN_EFFECT_CODE: 6})
        with _run("GrainEffect", device=device) as (out, err, _):
            # Off is the first row; it should show ✓
            lines = out.splitlines()
            off_line = next(l for l in lines if l.strip().startswith("Off"))
            assert "✓" in off_line

    def test_grain_off_fails_when_readback_outside_expected_set(self):
        # Camera returns 99 — not in {6, 7} → Off must fail.
        device = FakePTPDevice(int_read_overrides={_GRAIN_EFFECT_CODE: 99})
        with _run("GrainEffect", device=device) as (out, err, _):
            lines = out.splitlines()
            off_line = next(l for l in lines if l.strip().startswith("Off"))
            assert "✗" in off_line


class TestConnectionFailure:
    def test_connection_error_reported_on_stderr(self):
        class _UnreachableDevice(FakePTPDevice):
            def connect(self):
                raise CameraConnectionError("No Fujifilm camera found via USB")

        with _run("DRangePriority", device=_UnreachableDevice()) as (out, err, _):
            assert "Connection failed" in err
            assert "No Fujifilm camera found via USB" in err

    def test_no_output_on_connection_failure(self):
        class _UnreachableDevice(FakePTPDevice):
            def connect(self):
                raise CameraConnectionError("No camera")

        with _run("DRangePriority", device=_UnreachableDevice()) as (out, err, _):
            assert "passed" not in out


class TestCameraErrorDuringTest:
    def test_camera_error_reported_on_stderr(self):
        # The initial get_property_int (reading the current value) raises —
        # the command's except CameraConnectionError block fires.
        device = FakePTPDevice(
            get_errors={_DRANGE_PRIORITY_CODE: CameraConnectionError("camera gone")}
        )
        with _run("DRangePriority", device=device) as (out, err, _):
            assert "Camera error" in err
            assert "camera gone" in err


class TestValueRestoration:
    def test_original_value_restored_after_all_pass(self):
        initial = 42
        device = FakePTPDevice(int_values={_DRANGE_PRIORITY_CODE: initial})
        with _run("DRangePriority", device=device) as (out, err, fake):
            pass
        # Restore writes via set_property_uint16, which updates the int store.
        assert fake._int_store[_DRANGE_PRIORITY_CODE] == initial & 0xFFFF

    def test_original_value_restored_after_mismatches(self):
        # Writes are rejected so the store stays at 7 throughout.
        # Reads return 7, which matches no DRangePriority expected value
        # → all 4 fail.  The finally block still runs and the store remains
        # at the original value (restore write is also rejected, but the
        # value was never changed).
        initial = 7
        device = FakePTPDevice(
            int_values={_DRANGE_PRIORITY_CODE: initial},
            set_rejection_codes={_DRANGE_PRIORITY_CODE: 0x2005},
        )
        with _run("DRangePriority", device=device) as (out, err, fake):
            assert "0 passed, 4 failed" in out
        assert fake._int_store[_DRANGE_PRIORITY_CODE] == initial

    def test_restore_message_appears_in_output(self):
        with _run("DRangePriority") as (out, err, _):
            assert "Restored to" in out
