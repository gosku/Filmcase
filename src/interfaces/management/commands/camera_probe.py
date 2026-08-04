"""
Diagnostic command: report every signal that distinguishes USB connection modes.

Built to test whether a reduced PTP property set is a property of the camera
model or of the USB mode it is in.  Run it once per mode on the same body and
diff the output.

Nothing here aborts on a failed property read; every probe reports its own
result so a degraded session still produces a full report.

Usage:
    python manage.py camera_probe
    python manage.py camera_probe --no-cursor-test   # skip the slot cursor probe

Camera setup:
    MENU -> CONNECTION SETTING -> USB SETTING, then re-run for each mode
    (USB CARD READER, USB TETHER SHOOTING, USB RAW CONV./BACKUP RESTORE).
"""

from typing import Any

import usb.core
import usb.util
from django.core.management.base import BaseCommand, CommandParser

from src.data.camera import constants
from src.domain.camera import ptp_device
from src.domain.camera import ptp_usb_device

# Fujifilm USB modes, from libfuji lib/fujiptp.h enum FujiUSBModes.
PROP_USB_MODE = 0xD16E
PROP_FIRMWARE_VERSION = 0xD153
PROP_BATTERY_INFO_1 = 0xD36A  # libfuji reads battery percent from this one
USB_MODE_NAMES = {
    5: "USB TETHER SHOOTING",
    6: "USB RAW CONV./BACKUP RESTORE",
    8: "USB WEBCAM",
}

# USB interface classes (usb.org base class codes).
INTERFACE_CLASS_NAMES = {
    0x06: "Still Image / PTP",
    0x08: "Mass Storage",
}

FUJIFILM_VENDOR_ID = 0x04CB
VENDOR_PROPERTY_FLOOR = 0xD000  # codes at or above this are vendor-specific

_STATUS_PROPERTIES = (
    (PROP_USB_MODE, "USBMode"),
    (constants.PROP_BATTERY, "BatteryInfo2"),
    (PROP_BATTERY_INFO_1, "BatteryInfo1"),
    (PROP_FIRMWARE_VERSION, "FirmwareVersion"),
    (constants.PROP_PING, "Ping/GrainEffect"),
)

_SLOT_PROPERTIES = (
    (constants.PROP_SLOT_CURSOR, "PROP_SLOT_CURSOR"),
    (constants.PROP_SLOT_NAME, "PROP_SLOT_NAME"),
)


class Command(BaseCommand):
    help = "Probe the camera's USB mode and PTP property availability."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--no-cursor-test",
            action="store_true",
            default=False,
            help="Skip writing the slot cursor (read-only probe).",
        )

    def handle(self, *args: object, **options: Any) -> None:
        self._report_usb_interface()

        device = ptp_usb_device.PTPUSBDevice()
        try:
            device.connect()
        except ptp_device.CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"\nConnection failed: {e}"))
            return

        try:
            self._section("PTP session")
            self.stdout.write(f"  Model                  : {device.camera_name!r}")

            self._report_status_properties(device)
            advertised = self._report_device_info(device)
            if not options["no_cursor_test"]:
                self._report_cursor_test(device, advertised=advertised)
        finally:
            device.disconnect()
            self.stdout.write("\nDisconnected.")

    # ------------------------------------------------------------------
    # Probes
    # ------------------------------------------------------------------

    def _report_usb_interface(self) -> None:
        """
        Report the USB interface class before any PTP traffic.

        A camera in card reader mode presents Mass Storage (0x08) rather than
        Still Image (0x06).  connect() detaches the kernel driver and claims it
        regardless, so this is the only place the difference is visible.
        """
        self._section("USB device")
        dev = usb.core.find(idVendor=FUJIFILM_VENDOR_ID)
        if dev is None:
            self.stdout.write("  No Fujifilm device found.")
            return

        self.stdout.write(f"  Vendor / Product       : 0x{dev.idVendor:04X} / 0x{dev.idProduct:04X}")
        try:
            driver_active = dev.is_kernel_driver_active(0)
        except (usb.core.USBError, NotImplementedError):
            driver_active = None
        self.stdout.write(f"  Kernel driver attached : {driver_active}")

        try:
            intf = dev.get_active_configuration()[(0, 0)]
        except usb.core.USBError as e:
            self.stdout.write(f"  Interface class        : unavailable ({e})")
            return

        cls = intf.bInterfaceClass
        label = INTERFACE_CLASS_NAMES.get(cls, "unknown")
        self.stdout.write(f"  Interface class        : 0x{cls:02X} ({label})")
        if cls != 0x06:
            self.stdout.write(
                self.style.WARNING(
                    "  ^ not a Still Image interface, so the camera is not in a PTP mode."
                )
            )

    def _report_status_properties(self, device: ptp_usb_device.PTPUSBDevice) -> None:
        """
        Read each status property, reporting failures rather than raising.
        """
        self._section("Status properties")
        for code, name in _STATUS_PROPERTIES:
            try:
                value = device.get_property_int(code)
            except ptp_device.CameraConnectionError as e:
                self.stdout.write(
                    self.style.WARNING(f"  0x{code:04X} {name:<18}: NOT SERVED ({e})")
                )
                continue
            suffix = ""
            if code == PROP_USB_MODE:
                suffix = f"  ({USB_MODE_NAMES.get(value, 'unknown mode')})"
            self.stdout.write(f"  0x{code:04X} {name:<18}: {value}{suffix}")

        self.stdout.write(
            "\n  Note: libfuji treats a USBMode read failure as the signature of\n"
            "  USB CARD READER mode (lib/fuji_usb.c, fujiusb_setup)."
        )

    def _report_device_info(self, device: ptp_usb_device.PTPUSBDevice) -> list[int]:
        """
        Report the advertised property list and whether the slot codes are in it.
        """
        self._section("GetDeviceInfo: DevicePropertiesSupported")
        advertised = device.supported_properties()
        if not advertised:
            self.stdout.write(
                self.style.WARNING("  Empty list. The camera reported no properties at all.")
            )
            return advertised

        vendor = sorted(p for p in advertised if p >= VENDOR_PROPERTY_FLOOR)
        self.stdout.write(f"  Total properties       : {len(advertised)}")
        self.stdout.write(f"  Vendor (>= 0xD000)     : {len(vendor)}")

        for code, name in _SLOT_PROPERTIES:
            present = code in advertised
            status = "ADVERTISED" if present else "ABSENT"
            line = f"  0x{code:04X} {name:<18}: {status}"
            self.stdout.write(line if present else self.style.WARNING(line))

        self.stdout.write("\n  Vendor codes:")
        for start in range(0, len(vendor), 8):
            row = "  ".join(f"0x{c:04X}" for c in vendor[start:start + 8])
            self.stdout.write(f"    {row}")
        return advertised

    def _report_cursor_test(
        self,
        device: ptp_usb_device.PTPUSBDevice,
        *,
        advertised: list[int],
    ) -> None:
        """
        Write the slot cursor and report the response code the camera returns.

        This is the signal slot_states() discards: a rejected write and a failed
        slot read produce identical output once the return code is dropped.
        """
        self._section("Slot cursor write test")
        if constants.PROP_SLOT_CURSOR not in advertised and advertised:
            self.stdout.write(
                "  Cursor is not advertised. Writing it anyway, since PTP devices\n"
                "  can serve properties they do not advertise.\n"
            )

        original = self._try_read_int(device, constants.PROP_SLOT_CURSOR)
        self.stdout.write(f"  Cursor value before    : {original}")

        names: dict[int, str] = {}
        for slot in (1, 2):
            rc = device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
            verdict = "ACCEPTED" if rc == 0 else f"REJECTED (rc=0x{rc:04X})"
            self.stdout.write(f"  set cursor = {slot}         : {verdict}")
            if rc != 0:
                continue
            name = self._try_read_str(device, constants.PROP_SLOT_NAME)
            names[slot] = str(name)
            self.stdout.write(f"    read slot name       : {name!r}")

        if len(names) == 2:
            distinct = names[1] != names[2]
            self.stdout.write(
                f"\n  Cursor selects distinct slots: {'YES' if distinct else 'NO (both identical)'}"
            )
            if not distinct:
                self.stdout.write(
                    "  Identical names mean either both slots are empty or the cursor\n"
                    "  write is being accepted without taking effect."
                )

        if isinstance(original, int):
            device.set_property_uint16(constants.PROP_SLOT_CURSOR, original)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _try_read_int(self, device: ptp_usb_device.PTPUSBDevice, code: int) -> int | str:
        try:
            return device.get_property_int(code)
        except ptp_device.CameraConnectionError as e:
            return f"NOT SERVED ({e})"

    def _try_read_str(self, device: ptp_usb_device.PTPUSBDevice, code: int) -> str:
        try:
            return device.get_property_string(code)
        except ptp_device.CameraConnectionError as e:
            return f"NOT SERVED ({e})"

    def _section(self, title: str) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(title))
        self.stdout.write("-" * len(title))
