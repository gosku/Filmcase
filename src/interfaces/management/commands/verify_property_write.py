"""
Verify that writing each known value for a custom-slot PTP property reads back
correctly from the camera.

For each test value the command:
  1. Writes the value to the property.
  2. Reads it back.
  3. Checks the read-back matches the expected value.
  4. Reports pass / fail.

After all tests the original value is restored.

Usage:
    python manage.py verify_property_write FilmSimulation
    python manage.py verify_property_write GrainEffect --slot 2
    python manage.py verify_property_write --list
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.ptp_usb_device import PTPUSBDevice

# ---------------------------------------------------------------------------
# Test value table
#
# Each entry: (label, write_value, expected_read_back)
# For most properties expected_read_back == write_value.
# GrainEffect Off is the known exception: write 1, read back 6 or 7.
# ---------------------------------------------------------------------------

def _tone(domain: int) -> int:
    """Convert a domain tone/sharpness integer to its ×10 PTP uint16."""
    raw = abs(domain) * 10
    return raw if domain >= 0 else (65536 - raw)


def _nr(domain: int) -> int:
    """Convert a domain NR integer (+4..−4) to its PTP uint16."""
    return {
        4: 0x5000, 3: 0x6000, 2: 0x0000, 1: 0x1000, 0: 0x2000,
        -1: 0x3000, -2: 0x4000, -3: 0x7000, -4: 0x8000,
    }[domain]


_GRAIN_OFF_EXPECTED = {6, 7}  # camera normalises Off write (1) to 6 or 7

TEST_VALUES: dict[str, list[tuple[str, int, int | set]]] = {
    "FilmSimulation": [
        (name, ptp, ptp)
        for name, ptp in constants.FILM_SIMULATION_TO_PTP.items()
    ],
    "WhiteBalance": [
        (name, ptp, ptp)
        for name, ptp in constants.WHITE_BALANCE_TO_PTP.items()
    ],
    "WhiteBalanceRed": [
        (str(v), v if v >= 0 else 65536 + v, v if v >= 0 else 65536 + v)
        for v in range(-9, 10)
    ],
    "WhiteBalanceBlue": [
        (str(v), v if v >= 0 else 65536 + v, v if v >= 0 else 65536 + v)
        for v in range(-9, 10)
    ],
    "DRangeMode": [
        (name, ptp, ptp)
        for name, ptp in constants.DRANGE_MODE_TO_PTP.items()
    ],
    "DRangePriority": [
        ("Off",    0,      0),
        ("Weak",   1,      1),
        ("Strong", 2,      2),
        ("Auto",   0x8000, 0x8000),
    ],
    "GrainEffect": [
        ("Off",          1, _GRAIN_OFF_EXPECTED),
        ("Weak+Small",   2, 2),
        ("Strong+Small", 3, 3),
        ("Weak+Large",   4, 4),
        ("Strong+Large", 5, 5),
    ],
    "ColorEffect": [
        ("Off",    1, 1),
        ("Weak",   2, 2),
        ("Strong", 3, 3),
    ],
    "ColorFx": [
        ("Off",    1, 1),
        ("Weak",   2, 2),
        ("Strong", 3, 3),
    ],
    "ColorMode": [
        (str(v), _tone(v), _tone(v)) for v in range(-4, 5)
    ],
    "Sharpness": [
        (str(v), _tone(v), _tone(v)) for v in range(-4, 5)
    ],
    "HighLightTone": [
        (str(v), _tone(v), _tone(v)) for v in range(-2, 5)
    ],
    "ShadowTone": [
        (str(v), _tone(v), _tone(v)) for v in range(-2, 5)
    ],
    "HighIsoNoiseReduction": [
        (str(v), _nr(v), _nr(v)) for v in range(4, -5, -1)
    ],
    "Definition": [
        (str(v), _tone(v), _tone(v)) for v in range(-5, 6)
    ],
    "MonochromaticColorWarmCool": [
        (str(v), _tone(v), _tone(v)) for v in range(-18, 19)
    ],
    "MonochromaticColorMagentaGreen": [
        (str(v), _tone(v), _tone(v)) for v in range(-18, 19)
    ],
}


class Command(BaseCommand):
    help = "Write each known value for a custom-slot property and verify the read-back."

    def add_arguments(self, parser):
        parser.add_argument(
            "property",
            nargs="?",
            help="Property name (e.g. FilmSimulation). Omit to use --list.",
        )
        parser.add_argument(
            "--slot",
            type=int,
            default=1,
            metavar="N",
            help="Slot index (default: 1 = C1).",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all testable properties and exit.",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self.stdout.write("Testable properties:")
            for name in TEST_VALUES:
                n = len(TEST_VALUES[name])
                self.stdout.write(f"  {name}  ({n} values)")
            return

        prop_name = options.get("property")
        if not prop_name:
            self.stderr.write(self.style.ERROR("Provide a property name or use --list."))
            return

        if prop_name not in TEST_VALUES:
            self.stderr.write(self.style.ERROR(
                f"Unknown property '{prop_name}'. Use --list to see available properties."
            ))
            return

        if prop_name not in constants.CUSTOM_SLOT_CODES:
            self.stderr.write(self.style.ERROR(
                f"'{prop_name}' has no entry in CUSTOM_SLOT_CODES."
            ))
            return

        prop_code = constants.CUSTOM_SLOT_CODES[prop_name]
        slot = options["slot"]
        test_cases = TEST_VALUES[prop_name]

        device = PTPUSBDevice()
        try:
            device.connect()
        except CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Connection failed: {e}"))
            return

        try:
            device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
            time.sleep(0.3)

            # Read and save initial value for restore
            initial = device.get_property_int(prop_code)
            self.stdout.write(
                f"\nC{slot} — {prop_name} (0x{prop_code:04X})"
                f"  initial={initial} (0x{initial & 0xFFFF:04X})\n"
            )
            self.stdout.write(f"{'Value':<25} {'Write':>8}  {'Read':>8}  Result")
            self.stdout.write("─" * 60)

            passed = 0
            failed = 0

            for label, write_val, expected in test_cases:
                device.set_property_uint16(prop_code, write_val & 0xFFFF)
                time.sleep(1.0)
                device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
                time.sleep(1.0)
                read_back = device.get_property_int(prop_code)

                if isinstance(expected, set):
                    ok = read_back in expected
                    exp_str = "{" + ",".join(str(e) for e in sorted(expected)) + "}"
                else:
                    ok = read_back == expected
                    exp_str = str(expected)

                if ok:
                    result = self.style.SUCCESS("✓")
                    passed += 1
                else:
                    result = self.style.ERROR(f"✗  expected {exp_str}")
                    failed += 1

                self.stdout.write(
                    f"{label:<25} {write_val:>8}  {read_back:>8}  {result}"
                )

            self.stdout.write("─" * 60)
            self.stdout.write(f"{passed} passed, {failed} failed\n")

        except CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Camera error: {e}"))
        finally:
            # Restore original value
            try:
                device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot)
                time.sleep(0.1)
                device.set_property_uint16(prop_code, initial & 0xFFFF)
                self.stdout.write(f"Restored to {initial} (0x{initial & 0xFFFF:04X})")
            except Exception:
                self.stdout.write(self.style.WARNING("Could not restore original value."))
            device.disconnect()
