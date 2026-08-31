"""
Bodies that do not expose the slot cursor must be reported as unsupported
rather than scanned — a scan returns the per-property fallbacks ("", 0) for
every slot, which is indistinguishable from a camera with seven empty slots.
"""

from src.data.camera import constants
from src.domain.camera.queries import supports_custom_slots
from tests.fakes import FakePTPDevice


class TestSupportsCustomSlots:
    def test_true_when_slot_cursor_is_advertised(self):
        device = FakePTPDevice(int_values={constants.PROP_SLOT_CURSOR: 1})
        assert supports_custom_slots(device) is True

    def test_false_when_slot_cursor_is_absent(self):
        # An X-E5 advertises a handful of vendor properties, none of them the cursor.
        device = FakePTPDevice(int_values={0xD041: 0, 0xD303: 0, 0xD406: 0, 0xD407: 0})
        assert supports_custom_slots(device) is False

    def test_none_when_camera_reports_no_property_list(self):
        # Older bodies answer GetDeviceInfo with nothing; that is "unknown",
        # not "unsupported", so the existing tolerant read path still runs.
        device = FakePTPDevice()
        assert supports_custom_slots(device) is None
