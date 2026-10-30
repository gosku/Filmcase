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
from src.domain.camera import ptp_device
from src.domain.settings import queries as settings_queries

if TYPE_CHECKING:
    pass

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
# These four are standard PTP object-transfer opcodes, used here to read and
# restore the settings backup blob (object handle 0). That backup read/restore
# path is only proven on the X-T2; whether other Fujifilm bodies expose their
# settings backup the same way is unverified, so do not assume it generalises.
_OC_GET_OBJECT_INFO       = 0x1008
_OC_GET_OBJECT            = 0x1009
_OC_SEND_OBJECT_INFO      = 0x100C
_OC_SEND_OBJECT           = 0x100D
_OC_GET_DEVICE_PROP_VALUE = 0x1015
_OC_SET_DEVICE_PROP_VALUE = 0x1016

# The settings backup is addressed as object handle 0 (matches libfuji and the
# proven read/restore). SendObjectInfo describes it with a 1088-byte ObjectInfo
# whose only meaningful fields are the first 12 bytes; the rest is zero.
_BACKUP_HANDLE       = 0x00000000
_OBJ_FORMAT_BACKUP   = 0x5000
_OBJECT_INFO_LEN     = 1088

# ---------------------------------------------------------------------------
# PTP response codes
# ---------------------------------------------------------------------------

_RC_OK                  = 0x2001
_RC_SESSION_ALREADY     = 0x201E  # treat as OK

# ---------------------------------------------------------------------------
# Buffer constants
# ---------------------------------------------------------------------------

_READ_BUFFER     = 65_536    # max data to read in one call
_SESSION_ID      = 1
# The USB timeout, property-read delay, retry count and back-off are dynamic
# settings read into instance attributes in PTPUSBDevice.__init__.


# ---------------------------------------------------------------------------
# Packet construction / parsing helpers
# ---------------------------------------------------------------------------

def _command_packet(code: int, tx_id: int, *params: int) -> bytes:
    """
    Build a PTP command container packet (no data payload).
    """
    param_bytes = struct.pack(f"<{len(params)}I", *params)
    length = 12 + len(param_bytes)
    return struct.pack("<IHHI", length, _PTP_COMMAND, code, tx_id) + param_bytes


def _data_packet(code: int, tx_id: int, payload: bytes) -> bytes:
    """
    Build a PTP data container packet.
    """
    length = 12 + len(payload)
    return struct.pack("<IHHI", length, _PTP_DATA, code, tx_id) + payload


def _parse_response(raw: bytes) -> tuple[int, list[int]]:
    """
    Parse a PTP response container. Returns (response_code, [params]).
    """
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
    """
    Decode a PTP string starting at *offset*. Returns (string, new_offset).
    """
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
    """
    Encode a Python string as a PTP string (includes NUL terminator char).
    """
    if not s:
        return b"\x00"  # numChars = 0
    chars = [ord(c) for c in s] + [0]  # NUL terminated
    num_chars = len(chars)
    return struct.pack(f"<B{num_chars}H", num_chars, *chars)


def _skip_ptp_string(data: bytes, offset: int) -> int:
    """
    Skip a PTP string and return the new offset.
    """
    _, offset = _decode_ptp_string(data, offset)
    return offset


def _skip_ptp_uint16_array(data: bytes, offset: int) -> int:
    """
    Skip a PTP uint16 array (uint32 count + count × uint16).
    """
    if offset + 4 > len(data):
        return offset
    count: int = struct.unpack_from("<I", data, offset)[0]
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
    """
    Extract the Model string from a PTP GetDeviceInfo response payload.
    """
    _, mfr_off = _device_info_offsets(data)
    off = _skip_ptp_string(data, mfr_off)   # Manufacturer
    model, _ = _decode_ptp_string(data, off)
    return model


def _parse_device_info_supported_props(data: bytes) -> list[int]:
    """
    Extract DevicePropertiesSupported codes from a PTP GetDeviceInfo response payload.
    """
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
        # Read the dynamic timing/retry settings once, when the device is created.
        # A fresh device is built for each camera operation, so an edit on the
        # settings page takes effect on the next operation without a restart,
        # while a single session keeps consistent timings and avoids a settings
        # lookup on every USB transfer.
        self._usb_timeout_ms = settings_queries.get_camera_usb_timeout_ms()
        self._prop_read_delay_s = settings_queries.get_camera_post_read_delay_s()
        self._prop_max_retries = settings_queries.get_camera_max_retries()
        self._retry_backoff_s = settings_queries.get_camera_retry_backoff_s()

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
        self._dev = usb.core.find(idVendor=ptp_device.FUJIFILM_VENDOR_ID)
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
        """
        Read 0xD023 (GrainEffect / ping register). Returns 0 if alive.
        """
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
                prop=f"0x{code:04X}",
                error=str(e),
            )
            raise
        time.sleep(self._prop_read_delay_s)
        # Property value is in the data payload after the 12-byte container header.
        # Most Fuji recipe properties are uint16; read as uint32 if 4 bytes available.
        payload = data[12:]
        if len(payload) >= 4:
            value: int = struct.unpack_from("<i", payload, 0)[0]  # signed int32
        elif len(payload) >= 2:
            value = struct.unpack_from("<H", payload, 0)[0]  # uint16
        elif len(payload) >= 1:
            value = payload[0]
        else:
            value = 0
        camera_events.publish_event(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            prop=f"0x{code:04X}",
            value=value,
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
                prop=f"0x{code:04X}",
                error=str(e),
            )
            raise
        time.sleep(self._prop_read_delay_s)
        value, _ = _decode_ptp_string(data, 12)
        camera_events.publish_event(
            event_type=camera_events.PTP_READ_SUCCEEDED,
            prop=f"0x{code:04X}",
            value=value,
        )
        return value

    def set_property_int(self, code: int, value: int) -> int:
        """
        Write a 32-bit signed integer property.
        """
        payload = struct.pack("<i", value)
        return self._set_prop(code, payload)

    def set_property_uint16(self, code: int, value: int) -> int:
        """
        Write a uint16 property.
        """
        payload = struct.pack("<H", value & 0xFFFF)
        return self._set_prop(code, payload)

    def set_property_string(self, code: int, value: str) -> int:
        """
        Write a PTP string property (used for slot name, 0xD18D).
        """
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
    # Whole-backup transport (X-T2 and other pre-X-T3 bodies)
    # ------------------------------------------------------------------

    def get_backup(self) -> bytes:
        """
        Read the settings-backup blob via GetObjectInfo(0x1008) + GetObject(0x1009).

        Retries on transport failure like the property reads do.
        """
        last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError(
            "No retries attempted"
        )
        for attempt in range(self._prop_max_retries):
            if attempt > 0:
                time.sleep(self._retry_backoff_s * (2 ** (attempt - 1)))
            try:
                # GetObjectInfo primes the transfer; its payload is not needed here.
                self._object_op(_OC_GET_OBJECT_INFO, _BACKUP_HANDLE)
                rc, blob = self._object_op(_OC_GET_OBJECT, _BACKUP_HANDLE)
                self._check_rc(rc, "GetObject(backup)")
                if not blob:
                    raise ptp_device.CameraConnectionError("GetObject returned no data")
                camera_events.publish_event(
                    event_type=camera_events.PTP_BACKUP_READ_SUCCEEDED,
                    size=len(blob),
                )
                return blob
            except ptp_device.CameraConnectionError as e:
                camera_events.publish_event(
                    event_type=camera_events.PTP_BACKUP_READ_FAILED,
                    attempt=f"{attempt + 1}/{self._prop_max_retries}",
                    error=str(e),
                )
                last_err = e
        raise last_err

    def restore_backup(self, blob: bytes) -> None:
        """
        Restore the blob via SendObjectInfo(0x100C) + SendObject(0x100D), data-out.

        The status read uses CAMERA_RESTORE_TIMEOUT_MS because a settings commit
        takes seconds. The restore is not auto-retried (re-sending a settings
        commit is riskier than confirming by read-back); a lost status ack raises
        RestoreAckTimeout so the caller can decide from a read-back.
        """
        restore_timeout = settings_queries.get_camera_restore_timeout_ms()
        saved_timeout = self._usb_timeout_ms
        self._usb_timeout_ms = restore_timeout
        try:
            # SendObjectInfo: minimal ObjectInfo (storage 0, format 0x5000,
            # protection 0, compressed_size = len), rest zero.
            info = bytearray(_OBJECT_INFO_LEN)
            struct.pack_into("<IHHI", info, 0, 0, _OBJ_FORMAT_BACKUP, 0, len(blob))
            tx = self._next_tx()
            self._send(_command_packet(_OC_SEND_OBJECT_INFO, tx, 0, _BACKUP_HANDLE))
            self._send(_data_packet(_OC_SEND_OBJECT_INFO, tx, bytes(info)))
            rc = self._read_restore_ack("SendObjectInfo")
            if rc != _RC_OK:
                raise ptp_device.CameraWriteError(_OC_SEND_OBJECT_INFO, len(blob), rc)

            # SendObject: the raw blob, verbatim (no transform, no checksum).
            tx = self._next_tx()
            self._send(_command_packet(_OC_SEND_OBJECT, tx))
            self._send(_data_packet(_OC_SEND_OBJECT, tx, blob))
            rc = self._read_restore_ack("SendObject")
            if rc != _RC_OK:
                raise ptp_device.CameraWriteError(_OC_SEND_OBJECT, len(blob), rc)
        except ptp_device.CameraWriteError as e:
            camera_events.publish_event(
                event_type=camera_events.PTP_BACKUP_RESTORE_FAILED,
                rc=f"0x{e.rc:04X}",
            )
            raise
        else:
            camera_events.publish_event(
                event_type=camera_events.PTP_BACKUP_RESTORE_SUCCEEDED,
                size=len(blob),
            )
        finally:
            self._usb_timeout_ms = saved_timeout

    def _object_op(self, code: int, *params: int) -> tuple[int, bytes]:
        """
        Run an operation with a data-in phase (GetObjectInfo / GetObject).

        Returns ``(response_code, payload)`` with the data container header
        stripped. The X-T2 backup is a fixed 5660-byte object that fits in one
        USB read (well under the 64 KiB buffer), so a data phase spanning reads
        is treated as unexpected rather than drained.
        """
        assert self._ep_in is not None
        tx = self._next_tx()
        self._send(_command_packet(code, tx, *params))
        first = self._read_in()
        _, ptype, _, _ = struct.unpack_from("<IHHI", first, 0)
        if ptype != _PTP_DATA:
            # No data phase: the first container is the response itself.
            return _parse_response(first)[0], b""
        length = struct.unpack_from("<I", first, 0)[0]
        if len(first) < length:
            raise ptp_device.CameraConnectionError(
                f"Object data phase spanned multiple USB reads "
                f"({len(first)} of {length} bytes); unexpected for the X-T2 backup."
            )
        payload = first[12:length]
        resp = self._read_in()
        return _parse_response(resp)[0], payload

    def _read_in(self) -> bytes:
        assert self._ep_in is not None
        try:
            return bytes(self._ep_in.read(_READ_BUFFER, timeout=self._usb_timeout_ms))
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(f"USB read failed: {e}") from e

    def _read_restore_ack(self, step: str) -> int:
        """
        Read the status response after a restore step, mapping a timeout to
        RestoreAckTimeout so the caller can confirm by read-back.
        """
        assert self._ep_in is not None
        try:
            raw = bytes(self._ep_in.read(64, timeout=self._usb_timeout_ms))
        except usb.core.USBError as e:
            raise ptp_device.RestoreAckTimeout(
                f"{step} status read timed out: {e}"
            ) from e
        return _parse_response(raw)[0]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_prop_with_retry(self, code: int) -> bytes:
        """
        Send GetDevicePropValue and return the raw data, retrying on USB timeout.
        """
        last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError("No retries attempted")
        for attempt in range(self._prop_max_retries):
            if attempt > 0:
                time.sleep(self._retry_backoff_s * (2 ** (attempt - 1)))
            try:
                tx = self._next_tx()
                self._send(_command_packet(_OC_GET_DEVICE_PROP_VALUE, tx, code))
                data = self._recv_data()
                rc, _ = self._recv_response()
                self._check_rc(rc, f"GetDevicePropValue(0x{code:04X})")
                return data
            except ptp_device.CameraConnectionError as e:
                # Record the read retry so it is observable, mirroring the WebUSB
                # port's camera.ptp_read.retry event. Published on every failed
                # attempt (the last one included), so the count reflects how many
                # reads the camera needed asking twice.
                camera_events.publish_event(
                    event_type=camera_events.PTP_READ_RETRY,
                    prop=f"0x{code:04X}",
                    attempt=f"{attempt + 1}/{self._prop_max_retries}",
                )
                last_err = e
        raise last_err

    def _next_tx(self) -> int:
        tx = self._tx_id
        self._tx_id += 1
        return tx

    def _send(self, packet: bytes) -> None:
        assert self._ep_out is not None
        try:
            self._ep_out.write(packet, timeout=self._usb_timeout_ms)
        except usb.core.USBError as e:
            raise ptp_device.CameraConnectionError(f"USB write failed: {e}") from e

    def _recv_data(self) -> bytes:
        """
        Receive a data container from the camera (may be empty).
        """
        assert self._ep_in is not None
        try:
            raw = bytes(self._ep_in.read(_READ_BUFFER, timeout=self._usb_timeout_ms))
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
            raw = bytes(self._ep_in.read(64, timeout=self._usb_timeout_ms))
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
                prop=f"0x{code:04X}",
            )
            return 0
        camera_events.publish_event(
            event_type=camera_events.PTP_WRITE_FAILED,
            prop=f"0x{code:04X}",
            rc=f"0x{rc:04X}",
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
        # Retry a transport failure here with back-off, mirroring the read and
        # write paths.  OpenSession is the first exchange of every push, and a
        # transient timeout on its response would otherwise abort the whole push
        # before a single property is written.  Re-sending is safe: if the camera
        # opened the session on an earlier attempt it answers SessionAlreadyOpen,
        # which is treated as success.  A non-OK response code is not a transport
        # failure (the camera is in the wrong USB mode) and is not retried.
        last_err: ptp_device.CameraConnectionError = ptp_device.CameraConnectionError(
            "OpenSession not attempted"
        )
        for attempt in range(self._prop_max_retries):
            if attempt > 0:
                time.sleep(self._retry_backoff_s * (2 ** (attempt - 1)))
            try:
                tx = self._next_tx()
                self._send(_command_packet(_OC_OPEN_SESSION, tx, _SESSION_ID))
                rc, _ = self._recv_response()
            except ptp_device.CameraConnectionError as e:
                last_err = e
                camera_events.publish_event(
                    event_type=camera_events.PTP_READ_RETRY,
                    prop="OpenSession",
                    attempt=f"{attempt + 1}/{self._prop_max_retries}",
                )
                continue
            if rc in (_RC_OK, _RC_SESSION_ALREADY):
                return
            raise ptp_device.CameraConnectionError(
                f"PTP OpenSession failed with code 0x{rc:04X}. "
                "The camera may be in the wrong USB mode."
            )
        raise last_err

    def _fetch_camera_name(self) -> str:
        """
        Read camera model via PTP GetDeviceInfo.
        """
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
