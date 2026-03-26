from unittest.mock import patch

import pytest

from src.application.usecases.camera.push_recipe import push_recipe_to_camera
from src.data.camera import constants
from src.domain.camera import events
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from src.domain.images.dataclasses import FujifilmRecipeData
from tests.fakes import FakePTPDevice


def _make_recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        name="Test Recipe",
        film_simulation="Provia",
        dynamic_range="DR100",
        d_range_priority="Off",
        grain_roughness="Off",
        grain_size="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        highlight="0",
        shadow="0",
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        monochromatic_color_warm_cool="N/A",
        monochromatic_color_magenta_green="N/A",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


def _push(device=None, recipe=None, slot_index=1):
    """Convenience wrapper that patches time.sleep and supplies defaults."""
    with patch("src.application.usecases.camera.push_recipe.time.sleep"):
        return push_recipe_to_camera(
            device or FakePTPDevice(),
            recipe or _make_recipe(),
            slot_index=slot_index,
        )


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------


class TestPushRecipeVerification:
    def test_verification_passes_when_readback_matches(self):
        assert _push() == []

    def test_verification_detects_mismatched_readback(self):
        device = FakePTPDevice(int_read_overrides={0xD192: 99})
        failed = _push(device=device, recipe=_make_recipe(film_simulation="Provia"))
        assert 0xD192 in failed

    def test_slot_name_rejection_reported_in_failed_codes(self):
        # The camera rejects the slot-name write — it should appear in the
        # returned failed codes, just like any other property.
        device = FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005},
        )
        failed = _push(device=device)
        assert constants.PROP_SLOT_NAME in failed

    def test_slot_name_mismatch_reported_in_failed_codes(self, caplog):
        # The write reports success but the camera stores a different value.
        # Verification reads it back and reports the code as failed.
        device = FakePTPDevice(
            str_read_overrides={constants.PROP_SLOT_NAME: "Wrong Name"},
        )
        failed = _push(device=device)
        assert constants.PROP_SLOT_NAME in failed
        assert any("Verification failed" in rec.message for rec in caplog.records)

    def test_verification_handles_read_error_gracefully(self):
        # All int reads raise — simulates the camera going away during the
        # verification phase.  String reads (slot name) still succeed so the
        # test reaches verification without aborting early.
        device = FakePTPDevice(
            default_int_get_error=CameraConnectionError("USB read failed"),
        )
        failed = _push(device=device)
        assert len(failed) > 0


# ---------------------------------------------------------------------------
# Write event tests
# ---------------------------------------------------------------------------


class TestWriteSuccessEvents:
    def test_succeeded_event_published_for_each_written_property(self, captured_logs):
        _push()

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0
        for evt in succeeded:
            assert "0x" in evt["params"]["description"]


class TestWriteFailedCameraRejection:
    def test_failed_event_published_once_on_camera_rejection(self, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(set_rejection_codes={film_sim_code: 0x2005})
        failed = _push(device=device)

        assert film_sim_code in failed

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["params"]["description"]
        ]
        assert len(failed_events) == 1
        assert "camera rejected write" in failed_events[0]["params"]["description"]

    def test_other_properties_still_written_after_camera_rejection(self, captured_logs):
        # Camera rejection is not a transport failure — writing continues.
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(set_rejection_codes={film_sim_code: 0x2005})
        failed = _push(device=device)

        assert film_sim_code in failed
        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0

    def test_slot_name_rejection_does_not_abort_recipe_write(self, captured_logs):
        # A rejected slot-name write is not a transport failure; recipe
        # properties should still be written.
        device = FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )
        _push(device=device)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0


class TestWriteFailedTransportError:
    def test_raises_camera_connection_error_on_transport_failure(self):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

    def test_write_sequence_aborted_after_transport_failure(self, captured_logs):
        # Transport failure aborts — later properties are never attempted.
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

        succeeded_int_props = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
            and f"0x{film_sim_code:04X}" not in e["params"]["description"]
            and f"0x{constants.PROP_SLOT_NAME:04X}" not in e["params"]["description"]
        ]
        assert succeeded_int_props == []

    def test_slot_name_transport_failure_aborts_entire_write(self):
        device = FakePTPDevice(
            set_errors={constants.PROP_SLOT_NAME: CameraConnectionError("cable pulled")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

    def test_failed_event_published_per_retry_attempt_on_transport_error(self, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["params"]["description"]
        ]
        assert len(failed_events) == 3

    def test_failed_event_description_contains_attempt_number(self, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["params"]["description"]
        ]
        descriptions = [e["params"]["description"] for e in failed_events]
        assert any("attempt 1/" in d for d in descriptions)
        assert any("attempt 2/" in d for d in descriptions)
        assert any("attempt 3/" in d for d in descriptions)

    def test_succeeded_event_not_published_when_all_retries_fail(self, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push(device=device)

        succeeded_for_film_sim = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
            and f"0x{film_sim_code:04X}" in e["params"]["description"]
        ]
        assert succeeded_for_film_sim == []
