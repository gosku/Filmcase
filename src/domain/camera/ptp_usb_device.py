"""
PTPDevice implementation using PyUSB — pure Python, no C compilation.

Sends raw PTP/USB packets over USB bulk transfers directly to the camera.

Requirements:
    pip install pyusb

    Linux: sudo apt install libusb-1.0-0
           (plus a udev rule — see docs/camera_usb_access.md)
    macOS: brew install libusb

Camera setup:
    Set the camera to USB RAW CONV / BACKUP RESTORE mode, or any mode where
    it presents as a PTP device rather than mass storage.  On most Fujifilm
    bodies: MENU → CONNECTION SETTING → USB SETTING → USB RAW CONV./BACKUP RESTORE.

References:
    - PTP spec: PIMA 15740:2000, section 5
    - Fujifilm PTP constants: danielc/libfuji/lib/fujiptp.h
"""

from __future__ import annotations

import struct
import time
from typing import TYPE_CHECKING

import usb.core
import usb.util

from src.domain.camera import events as camera_events
from django.conf import settings as _settings

from src.domain.camera import ptp_device

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Fujifilm USB identity
# ---------------------------------------------------------------------------

_FUJIFILM_VENDOR_ID = 0x04CB   # all Fujifilm cameras share this vendor ID

# ---------------------------------------------------------------------------
# PTP/USB packet types (PIMA 15740:2000 §5.3.1)
# ---------------------------------------------------------------------------

_PTP_COMMAND  = 0x0001
_PTP_DATA     = 0x0002
_PTP_RESPONSE = 0x0003

# ---------------------------------------------------------------------------
# PTP operation codes
# ---------------------------------------------------------------------------

_OC_GET_DEVICE_INFO       = 0x1001
_OC_OPEN_SESSION          = 0x1002
_OC_CLOSE_SESSION         = 0x1003
_OC_GET_DEVICE_PROP_VALUE = 0x1015
_OC_SET_DEVICE_PROP_VALUE = 0x1016

# ---------------------------------------------------------------------------
# PTP response codes
# ---------------------------------------------------------------------------

_RC_OK                  = 0x2001
_RC_SESSION_ALREADY     = 0x201E  # treat as OK

# ---------------------------------------------------------------------------
# Timeout / buffer constants
# ---------------------------------------------------------------------------

_USB_TIMEOUT_MS  = 5_000     # 5 s — camera can be slow to respond
_READ_BUFFER     = 65_536    # max data to read in one call
_SESSION_ID      = 1
# Re-exported under legacy names so existing test imports keep working.
_PROP_READ_DELAY  = _settings.CAMERA_POST_READ_DELAY_S
_PROP_MAX_RETRIES = _settings.CAMERA_MAX_RETRIES
_RETRY_BACKOFF    = _settings.CAMERA_RETRY_BACKOFF_S


# ---------------------------------------------------------------------------
# Packet construction / parsing helpers
# ---------------------------------------------------------------------------

def _command_packet(code: int, tx_id: int, *params: int) -> bytes:
    """Build a PTP command container packet (no data payload)."""
    param_bytes = struct.pack(f"<{len(params)}I", *params)
    length = 12 + len(param_bytes)
    return struct.pack("<IHHI", length, _PTP_COMMAND, code, tx_id) + param_bytes


def _data_packet(code: int, tx_id: int, payload: bytes) -> bytes:
    """Build a PTP data container packet."""
    length = 12 + len(payload)
    return struct.pack("<IHHI", length, _PTP_DATA, code, tx_id) + payload


def _parse_response(raw: bytes) -> tuple[int, list[int]]:
    """Parse a PTP response container. Returns (response_code, [params])."""
    if len(raw) < 12:
        raise ptp_device.CameraConnectionError(
            f"PTP response too short ({len(raw)} bytes); camera may have disconnected."
        )
    length, ptype, code, _ = struct.unpack_from("<IHHI", raw, 0)
    n_params = (min(length, len(raw)) - 12) // 4
    params = list(struct.unpack_from(f"<{n_params}I", raw, 12))
    return code, params


# ---------------------------------------------------------------------------
# PTP string encoding / decoding
# (PTP strings: uint8 numChars + numChars × uint16 UCS-2 LE, NUL included)
# ---------------------------------------------------------------------------

def _decode_ptp_string(data: bytes, offset: int) -> tuple[str, int]:
    """Decode a PTP string starting at *offset*. Returns (string, new_offset)."""
    if offset >= len(data):
        return "", offset
    num_chars = data[offset]
    offset += 1
    if num_chars == 0:
        return "", offset
    chars = struct.unpack_from(f"<{num_chars}H", data, offset)
    offset += num_chars * 2
    # chars[-1] is the NUL terminator
    return "".join(chr(c) for c in chars[:-1] if c != 0), offset


def _encode_ptp_string(s: str) -> bytes:
    """Encode a Python string as a PTP string (includes NUL terminator char)."""
    if not s:
        return b"\x00"  # numChars = 0
    chars = [ord(c) for c in s] + [0]  # NUL terminated
    num_chars = len(chars)
    return struct.pack(f"<B{num_chars}H", num_chars, *chars)


def _skip_ptp_string(data: bytes, offset: int) -> int:
    """Skip a PTP string and return the new offset."""
    _, offset = _decode_ptp_string(data, offset)
    return offset


def _skip_ptp_uint16_array(data: bytes, offset: int) -> int:
    """Skip a PTP uint16 array (uint32 count + count × uint16)."""
    if offset + 4 > len(data):
        return offset
    count = struct.unpack_from("<I", data, offset)[0]
    return offset + 4 + count * 2


# ---------------------------------------------------------------------------
# DeviceInfo parser — only extracts the camera model name
# ---------------------------------------------------------------------------

def _device_info_offsets(data: bytes) -> tuple[int, int]:
    """
    Walk a GetDeviceInfo payload and return the byte offsets of:
        (DevicePropertiesSupported array, Manufacturer string)

    DeviceInfo layout (PIMA 15740:2000 §5.5.1):
        uint16  StandardVersion
        uint32  VendorExtensionID
        uint16  VendorExtensionVersion
        string  VendorExtensionDesc
        uint16  FunctionalMode
        array16 OperationsSupported    (uint32 count + count×uint16)
        array16 EventsSupported
        array16 DevicePropertiesSupported  ← first return value
        array16 CaptureFormats
        array16 ImageFormats
        string  Manufacturer               ← second return value
        string  Model
        ...
    """
    off = 12  # skip data-container header
    off += 2 + 4 + 2                         # StandardVersion, VendorExtensionID, VendorExtensionVersion
    off = _skip_ptp_string(data, off)        # VendorExtensionDesc
    off += 2                                  # FunctionalMode
    off = _skip_ptp_uint16_array(data, off)  # OperationsSupported
    off = _skip_ptp_uint16_array(data, off)  # EventsSupported
    props_off = off
    off = _skip_ptp_uint16_array(data, off)  # DevicePropertiesSupported
    off = _skip_ptp_uint16_array(data, off)  # CaptureFormats
    off = _skip_ptp_uint16_array(data, off)  # ImageFormats
    return props_off, off                    # off now points at Manufacturer


def _parse_device_info_model(data: bytes) -> str:
    """Extract the Model string from a PTP GetDeviceInfo response payload."""
    _, mfr_off = _device_info_offsets(data)
    off = _skip_ptp_string(data, mfr_off)   # Manufacturer
    model, _ = _decode_ptp_string(data, off)
    return model


def _parse_device_info_supported_props(data: bytes) -> list[int]:
    """Extract DevicePropertiesSupported codes from a PTP GetDeviceInfo response payload."""
    props_off, _ = _device_info_offsets(data)
    if props_off + 4 > len(data):
        return []
    count = struct.unpack_from("<I", data, props_off)[0]
    off = props_off + 4
    if count == 0 or off + count * 2 > len(data):
        return []
    return list(struct.unpack_from(f"<{count}H", data, off))


# ---------------------------------------------------------------------------
# PTPUSBDevice
# ---------------------------------------------------------------------------

class PTPUSBDevice:
    """
    PTPDevice backed by PyUSB — sends raw PTP/USB packets to the camera.

    Implements the same interface as LibFujiDevice but requires no C
    compilation. Works on Linux and macOS with only libusb (a runtime
    binary) and the pyusb Python package.

    Usage::

        with PTPUSBDevice() as device:
            info = queries.camera_info(device)

    Or manually::

        device = PTPUSBDevice()
        device.connect()
        try:
            operations.push_recipe(device, recipe)
        finally:
            device.disconnect()
    """

    def __init__(self) -> None:
        self._dev: usb.core.Device | None = None
        self._ep_out: usb.core.Endpoint | None = None
        self._ep_in: usb.core.Endpoint | None = None
        self._tx_id: int = 1
        self._camera_name: str = ""

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "PTPUSBDevice":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # PTPDevice protocol
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Find the first Fujifilm USB device, open a PTP session, and read
        the camera model name.

        Raises:
            ptp_device.CameraConnectionError: If no camera is found, USB access is
                                   denied, or the PTP session cannot be opened.
        """
        self._dev = usb.core.find(idVendor=_FUJIFILM_VENDOR_ID)
        if self._dev is None:
            raise ptp_device.CameraConnectionError(
                "No Fujifilm camera found via USB.\n"
                "Make sure the camera is:\n"
                "  • Connected via USB cable and powered on.\n"
                "  • Set to USB RAW CONV. or PC Connection mode\n"
                "    (not USB Mass Storage / card reader).\n"
                "On Linux, you may also need a udev rule — see docs/camera_usb_access.md."
            )

        self._claim_interface()
        self._open_session()
        self._camera_name = self._fetch_camera_name()

    def disconnect(self) -> None:
        if self._dev is None:
            return
        try:
            self._send(_command_packet(_OC_CLOSE_SESSION, self._next_tx()))
            self._recv_response()
        except Exception:
            pass
        try:
            usb.util.dispose_resources(self._dev)
        except Exception:
            pass
        self._dev = None

    def ping(self) -> int:
        """Read 0xD023 (GrainEffect / ping register). Returns 0 if alive."""
        from src.data.camera.constants import PROP_PING
        try:
            self.get_property_int(PROP_PING)
            return 0
        except ptp_device.CameraConnectionError:
            return -1

    def get_property_int(self, code: int) -> int:
        try:
            data = self._get_prop_with_retry(code)
        except ptp_device.CameraConnectionError as e:
            camera_events.publish_event(
                event_type=camera_events.PTP_READ_FAILED,
                params={"prop": f"0x{code:04X}", "error": str(e)},
            )
            raise
        time.sleep(_PROP_READ_DELAY)
        # Property value is in the data payload after the 12-byte container header.
        # Most Fuji recipe properties are uint16; read as uint32 if 4 bytes available.
        payload = data[12:]
        if len(payload) >= 4:
            value = struct.unpack_from("<i", payload, 0)[0]  # signed int32
        elif len(payload) >= 2:
            value = struct.unpack_from("<H", payload, 0)[0]  # uint16
        elif len(payload) >= 1:
            value = payload[0]
        else:
            value = 0
        camera_events.publish_event(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            params={"prop": f"0x{code:04X}", "value": value},
        )
        return value

    def get_property_int16(self, code: int) -> int:
        raw = self.get_property_int(code)
        v = raw & 0xFFFF
        return v - 65536 if v >= 32768 else v

    def get_property_string(self, code: int) -> str:
        try:
            data = self._get_prop_with_retry(code)
        except ptp_device.CameraConnectionError as e:
            camera_events.publish_event(
                event_type=camera_events.PTP_READ_FAILED,
                params={"prop": f"0x{code:04X}", "error": str(e)},
            )
            raise
        time.sleep(_PROP_READ_DELAY)
        value, _ = _decode_ptp_string(data, 12)
        camera_events.publish_event(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            params={"prop": f"0x{code:04X}", "value": value},
        )
        return value

    def set_property_int(self, code: int, value: int) -> int:
        """Write a 32-bit signed integer property."""
        payload = struct.pack("<i", value)
        return self._set_prop(code, payload)

    def set_property_uint16(self, code: int, value: int) -> int:
        """Write a uint16 property."""
        payload = struct.pack("<H", value & 0xFFFF)
        return self._set_prop(code, payload)

    def set_property_string(self, code: int, value: str) -> int:
        """Write a PTP string property (used for slot name, 0xD18D)."""
        payload = _encode_ptp_string(value)
        return self._set_prop(code, payload)

    def supported_properties(self) -> list[int]:
        """
        Return the list of PTP device property codes from GetDeviceInfo.

        Returns an empty list on any error so callers can treat it as optional.
        """
        try:
            tx = self._next_tx()
            self._send(_command_packet(_OC_GET_DEVICE_INFO, tx))
            data = self._recv_data()
            rc, _ = self._recv_response()
            if rc != _RC_OK:
                return []
            return _parse_device_info_supported_props(data)
        except Exception:
            return []

    @property
    def camera_name(self) -> str:
        return self._camera_name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_prop_with_retry(self, code: int) -> bytes:
        """Send GetDevicePropValue and return the raw data, retrying on USB timeout."""
        last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError("No retries attempted")
        for attempt in range(_PROP_MAX_RETRIES):
            if attempt > 0:
                time.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
            try:
                tx = self._next_tx()
                self._send(_command_packet(_OC_GET_DEVICE_PROP_VALUE, tx, code))
                data = self._recv_data()
                rc, _ = self._recv_response()
                self._check_rc(rc, f"GetDevicePropValue(0x{code:04X})")
                return data
            except ptp_device.CameraConnectionError as e:
                last_err = e
        raise last_err

    def _next_tx(self) -> int:
        tx = self._tx_id
        self._tx_id += 1
        return tx

    def _send(self, packet: bytes) -> None:
        assert self._ep_out is not None
        try:
            self._ep_out.write(packet, timeout=_USB_TIMEOUT_MS)
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(f"USB write failed: {e}") from e

    def _recv_data(self) -> bytes:
        """Receive a data container from the camera (may be empty)."""
        assert self._ep_in is not None
        try:
            raw = bytes(self._ep_in.read(_READ_BUFFER, timeout=_USB_TIMEOUT_MS))
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(f"USB read (data) failed: {e}") from e
        # Some cameras skip the data phase for properties with no value.
        if len(raw) >= 12:
            _, ptype, _, _ = struct.unpack_from("<IHHI", raw, 0)
            if ptype == _PTP_RESPONSE:
                # Camera sent response without data phase — parse as response.
                code, _ = _parse_response(raw)
                if code != _RC_OK:
                    raise ptp_device.CameraConnectionError(
                        f"PTP error 0x{code:04X} (no data phase)"
                    )
                return raw  # return as-is; caller's _recv_response will re-read
        return raw

    def _recv_response(self) -> tuple[int, list[int]]:
        assert self._ep_in is not None
        try:
            raw = bytes(self._ep_in.read(64, timeout=_USB_TIMEOUT_MS))
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(f"USB read (response) failed: {e}") from e
        return _parse_response(raw)

    def _check_rc(self, code: int, context: str) -> None:
        if code == _RC_OK:
            return
        if code == -5:
            raise ptp_device.CameraBusyError(f"Camera busy during {context}")
        if code != _RC_OK:
            raise ptp_device.CameraConnectionError(
                f"PTP error 0x{code:04X} during {context}"
            )

    def _set_prop(self, code: int, payload: bytes) -> int:
        tx = self._next_tx()
        self._send(_command_packet(_OC_SET_DEVICE_PROP_VALUE, tx, code))
        self._send(_data_packet(_OC_SET_DEVICE_PROP_VALUE, tx, payload))
        rc, _ = self._recv_response()
        if rc == _RC_OK:
            camera_events.publish_event(
                event_type=camera_events.PTP_WRITE_SUCCEEDED,
                params={"prop": f"0x{code:04X}"},
            )
            return 0
        camera_events.publish_event(
            event_type=camera_events.PTP_WRITE_FAILED,
            params={"prop": f"0x{code:04X}", "rc": f"0x{rc:04X}"},
        )
        return rc  # non-zero = failure; caller decides whether to raise

    def _claim_interface(self) -> None:
        assert self._dev is not None
        # On Linux, the kernel may have the device bound to a driver (e.g. usb-storage).
        # We need to detach it before we can claim the interface for raw PTP.
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            # NotImplementedError on macOS (libusb handles it automatically).
            # USBError if the interface is already detached.
            pass

        try:
            self._dev.set_configuration()
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(
                f"Could not set USB configuration: {e}\n"
                "On Linux, try: sudo chmod a+rw /dev/bus/usb/…  "
                "or add a udev rule — see docs/camera_usb_access.md."
            ) from e

        cfg = self._dev.get_active_configuration()
        intf = cfg[(0, 0)]

        self._ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        self._ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        if not self._ep_out or not self._ep_in:
            raise ptp_device.CameraConnectionError(
                "Could not find PTP bulk USB endpoints on this device. "
                "Is the camera in a PTP-compatible USB mode?"
            )

    def _open_session(self) -> None:
        tx = self._next_tx()
        self._send(_command_packet(_OC_OPEN_SESSION, tx, _SESSION_ID))
        rc, _ = self._recv_response()
        if rc not in (_RC_OK, _RC_SESSION_ALREADY):
            raise ptp_device.CameraConnectionError(
                f"PTP OpenSession failed with code 0x{rc:04X}. "
                "The camera may be in the wrong USB mode."
            )

    def _fetch_camera_name(self) -> str:
        """Read camera model via PTP GetDeviceInfo."""
        try:
            tx = self._next_tx()
            self._send(_command_packet(_OC_GET_DEVICE_INFO, tx))
            data = self._recv_data()
            rc, _ = self._recv_response()
            if rc != _RC_OK:
                return ""
            return _parse_device_info_model(data)
        except Exception:
            return ""
