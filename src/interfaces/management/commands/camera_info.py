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

from django.core.management.base import BaseCommand

from src.domain.camera import queries
from src.domain.camera import ptp_device
from src.domain.camera import ptp_usb_device


class Command(BaseCommand):
    help = "Read camera identity and status over USB (read-only connectivity test)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slots",
            action="store_true",
            default=False,
            help="Also read the contents of each custom slot (C1–Cn).",
        )

    def handle(self, *args, **options):
        self.stdout.write("Connecting to camera via USB…")

        device = ptp_usb_device.PTPUSBDevice()

        try:
            device.connect()
        except ptp_device.CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Connection failed: {e}"))
            return

        try:
            self._print_camera_info(device, read_slots=options["slots"])
        except ptp_device.CameraConnectionError as e:
            self.stderr.write(self.style.ERROR(f"Error while reading camera: {e}"))
        finally:
            device.disconnect()
            self.stdout.write("Disconnected.")

    def _print_camera_info(self, device: ptp_usb_device.PTPUSBDevice, *, read_slots: bool) -> None:
        info = queries.camera_info(device)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Camera connected"))
        self.stdout.write(f"  Model:            {info.camera_name!r}")
        self.stdout.write(f"  USB mode (raw):   {info.usb_mode}")
        self.stdout.write(f"  Battery (raw):    {info.battery_raw}")
        self.stdout.write(f"  Firmware (raw):   {info.firmware_version}")

        custom_slots = queries.custom_slot_count(info.camera_name)
        self.stdout.write(f"  Custom slots:     {custom_slots}")

        if read_slots:
            if custom_slots == 0:
                self.stdout.write("  (This camera model does not support custom slots.)")
                return

            self.stdout.write("")
            self.stdout.write("Custom slot contents:")
            slot_list = queries.slot_states(device, custom_slots)
            for slot in slot_list:
                self.stdout.write(
                    f"  C{slot.index}: {slot.name!r:20s}  film sim → {slot.film_sim_name}"
                )
