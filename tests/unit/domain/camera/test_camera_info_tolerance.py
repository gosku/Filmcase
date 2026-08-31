"""
Not every body serves every status property. Reading identity must survive a
camera that declines one of them rather than failing the whole call.
"""

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.queries import camera_info
from tests.fakes import FakePTPDevice

PROP_USB_MODE = 0xD16E
PROP_FIRMWARE_VERSION = 0xD153


class TestCameraInfoWithMissingProperties:
    def test_reads_all_properties_when_the_camera_serves_them(self):
        device = FakePTPDevice(
            camera_name="X-T5",
            int_values={
                constants.PROP_BATTERY: 3,
                PROP_USB_MODE: 1,
                PROP_FIRMWARE_VERSION: 42,
            },
        )

        info = camera_info(device)

        assert info.camera_name == "X-T5"
        assert info.battery_raw == 3
        assert info.usb_mode == 1
        assert info.firmware_version == 42

    def test_battery_falls_back_to_zero_when_not_served(self):
        # The X-E5 does not answer PROP_BATTERY.
        device = FakePTPDevice(
            camera_name="X-E5",
            int_values={PROP_USB_MODE: 1, PROP_FIRMWARE_VERSION: 42},
            get_errors={constants.PROP_BATTERY: CameraConnectionError("unsupported")},
        )

        info = camera_info(device)

        assert info.battery_raw == 0
        assert info.usb_mode == 1
        assert info.firmware_version == 42

    def test_usb_mode_falls_back_to_zero_when_not_served(self):
        # The X-E5 does not answer USBMode either.
        device = FakePTPDevice(
            camera_name="X-E5",
            int_values={constants.PROP_BATTERY: 3, PROP_FIRMWARE_VERSION: 42},
            get_errors={PROP_USB_MODE: CameraConnectionError("unsupported")},
        )

        info = camera_info(device)

        assert info.usb_mode == 0
        assert info.battery_raw == 3

    def test_identity_still_reads_when_no_status_property_is_served(self):
        device = FakePTPDevice(
            camera_name="X-E5",
            get_errors={
                constants.PROP_BATTERY: CameraConnectionError("unsupported"),
                PROP_USB_MODE: CameraConnectionError("unsupported"),
                PROP_FIRMWARE_VERSION: CameraConnectionError("unsupported"),
            },
        )

        info = camera_info(device)

        assert info.camera_name == "X-E5"
        assert (info.battery_raw, info.usb_mode, info.firmware_version) == (0, 0, 0)
