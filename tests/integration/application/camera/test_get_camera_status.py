"""
Integration tests for the get_camera_status use case.

A body that does not advertise the slot cursor still answers every
per-property read with a fallback ("" for names, 0 for film simulations), so
scanning it produces a full set of plausible-looking empty slots. Those must
not be reported as the camera's contents.

Uses FakePTPDevice via settings.PTP_DEVICE (see conftest autouse fixture).
"""

from src.application.usecases.camera.get_camera_info import get_camera_status
from src.data.camera import constants
from tests.fakes import FakePTPDevice


class TestSlotsSupportedReporting:
    def test_true_when_the_cursor_is_advertised(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            int_values={constants.PROP_SLOT_CURSOR: 1}
        )
        assert get_camera_status(read_slots=False).slots_supported is True

    def test_false_when_the_cursor_is_absent_from_a_populated_list(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(int_values={0xD041: 0, 0xD303: 0})
        assert get_camera_status(read_slots=False).slots_supported is False

    def test_none_when_the_camera_reports_no_property_list(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice()
        assert get_camera_status(read_slots=False).slots_supported is None


class TestSlotScanIsSkippedWhenUnsupported:
    def test_no_slots_returned_when_the_cursor_is_absent(self, settings):
        # X-S10 → 4 slots by model table, but the body cannot reach them.
        settings.PTP_DEVICE = lambda: FakePTPDevice(int_values={0xD041: 0, 0xD303: 0})

        result = get_camera_status(read_slots=True)

        assert result.custom_slot_count == 4
        assert result.slots is None

    def test_slots_are_read_when_the_cursor_is_advertised(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            int_values={constants.PROP_SLOT_CURSOR: 1},
            string_values={constants.PROP_SLOT_NAME: "My Slot"},
        )

        result = get_camera_status(read_slots=True)

        assert result.slots is not None
        assert len(result.slots) == 4

    def test_slots_are_read_when_support_is_unknown(self, settings):
        # Older bodies answer GetDeviceInfo with nothing. Unknown must not
        # regress into skipping the scan the previous behaviour performed.
        settings.PTP_DEVICE = lambda: FakePTPDevice()

        result = get_camera_status(read_slots=True)

        assert result.slots is not None
        assert len(result.slots) == 4
