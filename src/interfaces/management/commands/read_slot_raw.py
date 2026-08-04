"""
Temporary diagnostic command: read C1 and print all raw PTP values.

Prints the known properties plus a raw scan of the surrounding PTP code
range (0xD190–0xD1AF) so unknown properties can be spotted.

Usage:
    python manage.py read_slot_raw
    python manage.py read_slot_raw --slot 2
    python manage.py read_slot_raw --scan-supported
        Fetches the camera's DevicePropertiesSupported list, reads every
        vendor-specific code (≥ 0xD000) at C1 and C2, and flags which values
        differ between slots — useful for discovering slot property codes on
        cameras that don't support the known 0xD190–0xD1AF range.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.ptp_usb_device import PTPUSBDevice

_KNOWN_CODES = {v: k for k, v in constants.CUSTOM_SLOT_CODES.items()}
_KNOWN_CODES[constants.PROP_SLOT_CURSOR] = "PROP_SLOT_CURSOR"
_KNOWN_CODES[constants.PROP_SLOT_NAME]   = "PROP_SLOT_NAME"
_KNOWN_CODES[constants.PROP_BATTERY]     = "PROP_BATTERY"
_KNOWN_CODES[constants.PROP_PING]        = "PROP_PING"

# Range to scan for unknown properties (inclusive)
_SCAN_START = 0xD190
_SCAN_END   = 0xD1AF


class Command(BaseCommand):
    help = "Read a single custom slot and dump all raw PTP values."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slot",
            type=int,
            default=1,
            metavar="N",
            help="Slot index to read (default: 1 = C1).",
        )
        parser.add_argument(
            "--scan-supported",
            action="store_true",
            default=False,
            help=(
                "Read all vendor properties from GetDeviceInfo at C1 and C2, "
                "flagging codes whose value differs between slots."
            ),
        )

    def handle(self, *args, **options):
        device = PTPUSBDevice()
        try:
            device.connect()
        except CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Connection failed: {e}"))
            return

        try:
            if options["scan_supported"]:
                self._run_scan_supported(device)
            else:
                self._run(device, options["slot"])
        except CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Camera error: {e}"))
        finally:
            device.disconnect()

    def _run(self, device: PTPUSBDevice, slot: int) -> None:
        device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
        time.sleep(0.05)

        try:
            name = device.get_property_string(constants.PROP_SLOT_NAME)
        except CameraConnectionError:
            name = "<unsupported>"
        self.stdout.write(f"\nC{slot}: {name!r}\n")
        self.stdout.write(f"{'Code':<10} {'Name':<35} {'int16':>8}  {'uint16/int':>12}  hex")
        self.stdout.write("─" * 75)

        for code in range(_SCAN_START, _SCAN_END + 1):
            label = _KNOWN_CODES.get(code, "")
            try:
                raw_int16  = device.get_property_int16(code)
                raw_uint   = device.get_property_int(code)
                self.stdout.write(
                    f"0x{code:04X}    {label:<35} {raw_int16:>8}  {raw_uint:>12}  0x{raw_uint & 0xFFFF:04X}"
                )
            except Exception as e:
                self.stdout.write(f"0x{code:04X}    {label:<35} {'ERROR':>8}  {str(e)}")

    def _run_scan_supported(self, device: PTPUSBDevice) -> None:
        all_props = device.supported_properties()
        vendor_props = sorted(p for p in all_props if p >= 0xD000)

        self.stdout.write(
            f"\nGetDeviceInfo: {len(all_props)} total properties, "
            f"{len(vendor_props)} vendor-specific (≥ 0xD000)\n"
        )

        if not vendor_props:
            self.stdout.write("No vendor properties found — cannot scan.")
            return

        def read_all(slot: int) -> dict[int, int | Exception]:
            device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
            time.sleep(0.05)
            out: dict[int, int | Exception] = {}
            for code in vendor_props:
                try:
                    out[code] = device.get_property_int(code)
                except Exception as e:
                    out[code] = e
            return out

        self.stdout.write("Reading C1…")
        v1_map = read_all(1)
        self.stdout.write("Reading C2…\n")
        v2_map = read_all(2)

        self.stdout.write(f"{'Code':<10} {'Name':<35} {'C1':>12}  {'C2':>12}  note")
        self.stdout.write("─" * 85)

        for code in vendor_props:
            label = _KNOWN_CODES.get(code, "")
            v1, v2 = v1_map[code], v2_map[code]
            if isinstance(v1, Exception) or isinstance(v2, Exception):
                err = v1 if isinstance(v1, Exception) else v2
                self.stdout.write(
                    f"0x{code:04X}    {label:<35} {'ERROR':>12}  {str(err)[:30]}"
                )
            else:
                note = "  ← slot-specific?" if v1 != v2 else ""
                self.stdout.write(
                    f"0x{code:04X}    {label:<35} {v1:>12}  {v2:>12}{note}"
                )
