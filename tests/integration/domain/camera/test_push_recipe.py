import pytest
from decimal import Decimal

from src.application.usecases.camera.push_recipe import RecipeWriteError, push_recipe_to_camera
from src.data import models
from src.data.camera import constants
from src.domain.camera import events
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from tests.factories import FujifilmRecipeFactory
from tests.fakes import FakePTPDevice


def _make_recipe(**overrides: object) -> models.FujifilmRecipe:
    """
    Create and save a FujifilmRecipe via the factory.

    push_recipe_to_camera() reads the recipe's sensors M2M (via
    recipe_from_db), which requires a saved instance, so these tests touch
    the DB despite living under tests/unit.
    """
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
        color=Decimal("0"),
        sharpness=Decimal("0"),
        high_iso_nr=Decimal("0"),
        clarity=Decimal("0"),
        highlight=Decimal("0"),
        shadow=Decimal("0"),
    )
    defaults.update(overrides)
    return FujifilmRecipeFactory(**defaults)


def _push(recipe=None, slot_index=1):
    return push_recipe_to_camera(
        recipe or _make_recipe(),
        slot_index=slot_index,
    )


# ---------------------------------------------------------------------------
# Verification tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPushRecipeVerification:
    def test_verification_passes_when_readback_matches(self):
        _push()  # no exception = all properties written and verified

    def test_verification_detects_mismatched_readback(self, settings):
        settings.CAMERA_VERIFY_WRITES = True
        settings.PTP_DEVICE = lambda: FakePTPDevice(int_read_overrides={0xD192: 99})
        with pytest.raises(RecipeWriteError) as exc_info:
            _push(recipe=_make_recipe(film_simulation="Provia"))
        assert "FilmSimulation" in exc_info.value.failed_properties

    def test_slot_name_rejection_reported_in_failed_properties(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005},
        )
        with pytest.raises(RecipeWriteError) as exc_info:
            _push()
        assert "SlotName" in exc_info.value.failed_properties

    def test_slot_name_mismatch_reported_in_failed_properties(self, settings, caplog):
        settings.CAMERA_VERIFY_WRITES = True
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            str_read_overrides={constants.PROP_SLOT_NAME: "Wrong Name"},
        )
        with pytest.raises(RecipeWriteError) as exc_info:
            _push()
        assert "SlotName" in exc_info.value.failed_properties
        assert any("Verification failed" in rec.message for rec in caplog.records)

    def test_verification_handles_read_error_gracefully(self, settings):
        settings.CAMERA_VERIFY_WRITES = True
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            default_int_get_error=CameraConnectionError("USB read failed"),
        )
        with pytest.raises(RecipeWriteError) as exc_info:
            _push()
        assert len(exc_info.value.failed_properties) > 0


# ---------------------------------------------------------------------------
# Write event tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWriteSuccessEvents:
    def test_succeeded_event_published_for_each_written_property(self, captured_logs):
        _push()

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0
        for evt in succeeded:
            assert "0x" in evt["description"]


@pytest.mark.django_db
class TestWriteFailedCameraRejection:
    def test_failed_event_published_once_on_camera_rejection(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(set_rejection_codes={film_sim_code: 0x2005})
        with pytest.raises(RecipeWriteError) as exc_info:
            _push()

        assert "FilmSimulation" in exc_info.value.failed_properties

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["description"]
        ]
        assert len(failed_events) == 1
        assert "camera rejected write" in failed_events[0]["description"]

    def test_other_properties_still_written_after_camera_rejection(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(set_rejection_codes={film_sim_code: 0x2005})
        with pytest.raises(RecipeWriteError) as exc_info:
            _push()

        assert "FilmSimulation" in exc_info.value.failed_properties
        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0

    def test_slot_name_rejection_does_not_abort_recipe_write(self, settings, captured_logs):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )
        with pytest.raises(RecipeWriteError):
            _push()

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
        ]
        assert len(succeeded) > 0


@pytest.mark.django_db
class TestWriteFailedTransportError:
    def test_raises_camera_connection_error_on_transport_failure(self, settings):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

    def test_write_sequence_aborted_after_transport_failure(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

        succeeded_int_props = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
            and f"0x{film_sim_code:04X}" not in e["description"]
            and f"0x{constants.PROP_SLOT_NAME:04X}" not in e["description"]
            # The slot cursor is written first via set_cursor_with_retry and
            # succeeds before the failing property; exclude it too.
            and f"0x{constants.PROP_SLOT_CURSOR:04X}" not in e["description"]
        ]
        assert succeeded_int_props == []

    def test_slot_name_transport_failure_aborts_entire_write(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_NAME: CameraConnectionError("cable pulled")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

    def test_failed_event_published_per_retry_attempt_on_transport_error(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["description"]
        ]
        assert len(failed_events) == 3

    def test_failed_event_description_contains_attempt_number(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

        failed_events = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_FAILED
            and f"0x{film_sim_code:04X}" in e["description"]
        ]
        descriptions = [e["description"] for e in failed_events]
        assert any("attempt 1/" in d for d in descriptions)
        assert any("attempt 2/" in d for d in descriptions)
        assert any("attempt 3/" in d for d in descriptions)

    def test_succeeded_event_not_published_when_all_retries_fail(self, settings, captured_logs):
        film_sim_code = constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            _push()

        succeeded_for_film_sim = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_WRITE_SUCCEEDED
            and f"0x{film_sim_code:04X}" in e["description"]
        ]
        assert succeeded_for_film_sim == []


class _CursorFailsThenSucceeds(FakePTPDevice):
    """FakePTPDevice whose slot-cursor write fails `cursor_fails` times first."""

    def __init__(self, *, cursor_fails: int, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._cursor_fails_left = cursor_fails

    def set_property_uint16(self, code: int, value: int) -> int:
        if code == constants.PROP_SLOT_CURSOR and self._cursor_fails_left > 0:
            self._cursor_fails_left -= 1
            raise CameraConnectionError("transient cursor timeout")
        return super().set_property_uint16(code, value)


@pytest.mark.django_db
class TestSlotCursorRetry:
    def test_transient_cursor_failure_is_retried_and_push_succeeds(self, settings):
        # The slot cursor is written once per push; before it was a single shot,
        # so a lone timeout there aborted the whole recipe. It is now retried.
        settings.CAMERA_MAX_RETRIES = 3
        device = _CursorFailsThenSucceeds(cursor_fails=2)
        settings.PTP_DEVICE = lambda: device

        _push()  # must not raise

    def test_cursor_transport_failure_exhausts_retries_and_aborts(self, settings):
        settings.CAMERA_MAX_RETRIES = 3
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("cursor timeout")}
        )

        with pytest.raises(CameraConnectionError):
            _push()

    def test_cursor_rejection_is_surfaced_as_connection_error(self, settings):
        # A refused cursor write is wrapped as a connection error (nothing has
        # been written yet), mirroring the WebUSB port.
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        with pytest.raises(CameraConnectionError):
            _push()
