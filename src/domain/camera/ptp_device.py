"""
Protocol and exceptions for PTP/USB camera device communication.

The PTPDevice protocol defines the interface that any concrete implementation
must satisfy.  Currently the only implementation is LibFujiDevice (ctypes
wrapper around the compiled fuji_bridge shared library).  A mock implementation
can be provided for tests without a physical camera.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class CameraConnectionError(Exception):
    """Raised when the camera is not reachable or the connection fails."""


class CameraBusyError(Exception):
    """Raised when the camera returns a 'busy' status (-5 in libujxp terms)."""


class CameraWriteError(Exception):
    """Raised when the camera actively rejects a property write (non-zero rc)."""

    def __init__(self, code: int, value: str | int, rc: int) -> None:
        self.code = code
        self.value = value
        self.rc = rc
        super().__init__(
            f"Camera rejected write of PTP property 0x{code:04X} = {value!r} (rc={rc:#x})"
        )


@runtime_checkable
class PTPDevice(Protocol):
    """
    Structural protocol for a Fujifilm PTP/USB device.

    All integers returned by get_property_int / ping are raw PTP values
    (0 = success / property value as signed int).

    Callers are responsible for timing between operations — the camera
    requires 50 ms before each write and 200 ms after.
    """

    def connect(self) -> None:
        """
        Open a USB connection to the first available Fujifilm camera.

        Raises:
            CameraConnectionError: If no camera is found or the session
                                   cannot be opened.
        """
        ...

    def disconnect(self) -> None:
        """Close the PTP session and release USB resources."""
        ...

    def ping(self) -> int:
        """
        Read property 0xD023 (GrainEffect / ping register).

        Returns:
            0 on success, non-zero on failure.

        Raises:
            CameraConnectionError: If the ping transport fails entirely.
        """
        ...

    def get_property_int(self, code: int) -> int:
        """
        Read a device property as a 32-bit signed integer.

        Args:
            code: PTP device property code.

        Returns:
            The property value as a signed int.

        Raises:
            CameraConnectionError: On transport failure.
        """
        ...

    def get_property_int16(self, code: int) -> int:
        """
        Read a device property and reinterpret the lower 16 bits as a signed
        int16 (-32768..32767).

        The Fujifilm camera sends many recipe properties (WB fine-tune,
        highlight/shadow tone, colour, sharpness, clarity, …) as a uint16
        zero-extended to a 4-byte PTP payload.  get_property_int() returns
        these as a large positive int32 (e.g. 65526 for sharpness -1×10).
        This method reinterprets them correctly as signed int16 (-10 → -1×10).

        Use get_property_int() for properties that are genuinely 32-bit (film
        simulation, DR mode, WB mode code, colour temperature, NR, …).

        Args:
            code: PTP device property code.

        Returns:
            The property value as a signed int16.

        Raises:
            CameraConnectionError: On transport failure.
        """
        ...

    def get_property_string(self, code: int) -> str:
        """
        Read a device property as a PTP string.

        Args:
            code: PTP device property code.

        Returns:
            The property value as a Python str.

        Raises:
            CameraConnectionError: On transport failure.
        """
        ...

    def set_property_int(self, code: int, value: int) -> int:
        """
        Write a device property as a 32-bit signed integer.

        Args:
            code:  PTP device property code.
            value: Integer value to write.

        Returns:
            0 on success, non-zero on failure.
        """
        ...

    def set_property_uint16(self, code: int, value: int) -> int:
        """
        Write a device property as an unsigned 16-bit integer.

        Used exclusively for the slot cursor (PROP_SLOT_CURSOR = 0xD18C).

        Args:
            code:  PTP device property code.
            value: Value to write (0–65535).

        Returns:
            0 on success, non-zero on failure.
        """
        ...

    def set_property_string(self, code: int, value: str) -> int:
        """
        Write a device property as a PTP string.

        Used to rename a custom slot (PROP_SLOT_NAME = 0xD18D).

        Args:
            code:  PTP device property code.
            value: String to write.

        Returns:
            0 on success, non-zero on failure.
        """
        ...

    @property
    def camera_name(self) -> str:
        """
        Camera model string reported during the PTP session handshake.

        Available after a successful connect().
        """
        ...
