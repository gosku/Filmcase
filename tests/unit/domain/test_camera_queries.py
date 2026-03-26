import attrs
import pytest

from src.data.camera.constants import DRANGE_MODE_TO_PTP, FILM_SIMULATION_TO_PTP, PTP_TO_FILM_SIMULATION
from src.domain.camera.queries import RecipePTPValues, recipe_to_ptp_values
from src.domain.images.dataclasses import FujifilmRecipeData


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


class TestFilmSimulationPTPMapping:
    """Verify all film simulation PTP values match the filmkit reference."""

    EXPECTED_VALUES = {
        "Provia": 1,
        "Velvia": 2,
        "Astia": 3,
        "Pro Neg. Hi": 4,
        "Pro Neg. Std": 5,
        "Monochrome STD": 6,
        "Monochrome Yellow": 7,
        "Monochrome Red": 8,
        "Monochrome Green": 9,
        "Sepia": 10,
        "Classic Chrome": 11,
        "Acros STD": 12,
        "Acros Yellow": 13,
        "Acros Red": 14,
        "Acros Green": 15,
        "Eterna": 16,
        "Classic Negative": 17,
        "Eterna Bleach Bypass": 18,
        "Nostalgic Negative": 19,
        "Reala Ace": 20,
    }

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_film_simulation_to_ptp(self, name, expected_ptp):
        assert FILM_SIMULATION_TO_PTP[name] == expected_ptp

    @pytest.mark.parametrize(
        "expected_ptp, name",
        [(v, k) for k, v in EXPECTED_VALUES.items()],
        ids=EXPECTED_VALUES.keys(),
    )
    def test_ptp_to_film_simulation(self, expected_ptp, name):
        assert PTP_TO_FILM_SIMULATION[expected_ptp] == name

    def test_no_gap_at_value_19(self):
        """Nostalgic Negative occupies value 19, between Eterna BB (18) and Reala Ace (20)."""
        assert FILM_SIMULATION_TO_PTP["Nostalgic Negative"] == 19

    def test_nostalgic_negative_round_trips_through_recipe(self):
        recipe = _make_recipe(film_simulation="Nostalgic Negative")
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.FilmSimulation == 19


class TestDRangeModePTPMapping:
    """Verify all D-Range mode PTP values, especially the corrected DR-Auto."""

    EXPECTED_VALUES = {
        "DR-Auto": 65535,  # 0xFFFF — was incorrectly 0 before fix
        "DR100":   100,
        "DR200":   200,
        "DR400":   400,
    }

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_drange_mode_to_ptp(self, name, expected_ptp):
        assert DRANGE_MODE_TO_PTP[name] == expected_ptp

    def test_dr_auto_is_not_zero(self):
        """DR-Auto must be 0xFFFF, not 0. 0 was the pre-fix incorrect value."""
        assert DRANGE_MODE_TO_PTP["DR-Auto"] != 0
        assert DRANGE_MODE_TO_PTP["DR-Auto"] == 0xFFFF

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_dr_auto_round_trips_through_recipe(self, name, expected_ptp):
        recipe = _make_recipe(dynamic_range=name)
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.DRangeMode == expected_ptp


# ---------------------------------------------------------------------------
# Read event tests
# ---------------------------------------------------------------------------

from src.data.camera import constants as cam_constants
from src.domain.camera import events
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.queries import camera_info, slot_recipe, slot_states
from tests.fakes import FakePTPDevice


class TestReadSucceededEvents:
    def test_slot_recipe_publishes_succeeded_event_per_property(self, captured_logs):
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]: 1},
            string_values={cam_constants.PROP_SLOT_NAME: "Test"},
        )
        slot_recipe(device, slot_index=1)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # slot_recipe reads ~19 properties (1 string + 18 int/int16)
        assert len(succeeded) >= 19
        for evt in succeeded:
            assert "0x" in evt["params"]["description"]

    def test_camera_info_publishes_succeeded_events(self, captured_logs):
        device = FakePTPDevice()
        camera_info(device)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # battery, usb_mode, firmware_version (3 reads minimum)
        assert len(succeeded) >= 2  # firmware may be silently skipped on some models

    def test_slot_states_publishes_succeeded_events(self, captured_logs):
        device = FakePTPDevice()
        slot_states(device, slot_count=2)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # 2 slots × 2 reads each (name + film sim)
        assert len(succeeded) >= 4


class TestReadFailedEvents:
    def test_slot_recipe_publishes_failed_event_and_propagates(self, captured_logs):
        film_sim_code = cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            get_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            slot_recipe(device, slot_index=1)

        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert f"0x{film_sim_code:04X}" in failed[0]["params"]["description"]

    def test_camera_info_publishes_failed_event_for_firmware_and_continues(self, captured_logs):
        # firmware_version read is allowed to fail (older cameras); camera_info
        # catches the exception and sets firmware_version=0.
        device = FakePTPDevice(
            get_errors={0xD153: CameraConnectionError("not supported")}
        )
        info = camera_info(device)

        assert info.firmware_version == 0
        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert "0xD153" in failed[0]["params"]["description"]

    def test_slot_states_publishes_failed_event_for_slot_name_and_continues(self, captured_logs):
        # Slot name read fails (older models); slot_states catches it and uses "".
        device = FakePTPDevice(
            get_errors={cam_constants.PROP_SLOT_NAME: CameraConnectionError("not supported")}
        )
        states = slot_states(device, slot_count=1)

        assert states[0].name == ""
        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert f"0x{cam_constants.PROP_SLOT_NAME:04X}" in failed[0]["params"]["description"]

    def test_failed_event_description_contains_exception_message(self, captured_logs):
        film_sim_code = cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            get_errors={film_sim_code: CameraConnectionError("USB timeout reason")}
        )
        with pytest.raises(CameraConnectionError):
            slot_recipe(device, slot_index=1)

        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert "USB timeout reason" in failed[0]["params"]["description"]
