"""
Django management command: camera_info

Connects to a Fujifilm camera over USB, reads its identity and status
properties, and prints a summary — without writing anything to the camera.

This is a read-only connectivity smoke-test for the PyUSB PTP stack.

Usage:
    python manage.py camera_info
    python manage.py camera_info --slots   # also read custom slot contents

Prerequisites:
    pip install pyusb

    Linux:  sudo apt install libusb-1.0-0
            (plus a udev rule so you can access USB without sudo —
             see docs/camera_usb_access.md)
    macOS:  brew install libusb

Camera setup:
    Set the camera to USB RAW CONV. / BACKUP RESTORE mode or similar PTP mode.
    Most Fujifilm bodies: MENU → CONNECTION SETTING → USB SETTING.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from src.application.usecases.camera import get_camera_info as get_camera_info_uc
from src.data.camera import constants
from src.domain.camera import ptp_device


class Command(BaseCommand):
    help = "Read camera identity and status over USB (read-only connectivity test)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--slots",
            action="store_true",
            default=False,
            help="Also read the contents of each custom slot (C1–Cn).",
        )

    def handle(self, *args: object, **options: Any) -> None:
        self.stdout.write("Connecting to camera via USB…")

        try:
            result = get_camera_info_uc.get_camera_status(read_slots=options["slots"])
        except ptp_device.CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Connection failed: {e}"))
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Camera connected"))
        self.stdout.write(f"  Model:            {result.info.camera_name!r}")
        self.stdout.write(f"  USB mode (raw):   {result.info.usb_mode}")
        self.stdout.write(f"  Battery (raw):    {result.info.battery_raw}")
        self.stdout.write(f"  Firmware (raw):   {result.info.firmware_version}")
        self.stdout.write(f"  Custom slots:     {result.custom_slot_count}")
        self.stdout.write("Disconnected.")

        if options["slots"]:
            if result.slots_supported is False:
                self.stderr.write(
                    self.style.ERROR(
                        "This body does not advertise the custom-slot cursor "
                        f"(0x{constants.PROP_SLOT_CURSOR:04X}), so C1–Cn cannot be read "
                        "or written over USB."
                    )
                )
                return
            if result.slots is None:
                self.stdout.write("  (This camera model does not support custom slots.)")
                return
            self.stdout.write("")
            self.stdout.write("Custom slot contents:")
            for slot in result.slots:
                self.stdout.write(
                    f"  C{slot.index}: {slot.name!r:20s}  film sim → {slot.film_sim_name}"
                )
