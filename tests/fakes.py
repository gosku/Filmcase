"""
Fake PTP device for unit tests.

FakePTPDevice implements the PTPDevice protocol without any USB hardware.
Initialise it with the property values you want reads to return, then
optionally configure write and read failures to test error-handling paths.

Two distinct failure modes mirror the real PTPUSBDevice behaviour:

- Transport failure (CameraConnectionError):
  The camera is unreachable — USB timeout, cable pulled, etc.  Raised by
  the real device from _send / _recv_response.  Simulate via
  ``get_errors`` or ``set_errors``.

- Camera rejection (non-zero return code):
  The camera received the command but declined to apply it — e.g. the
  property is read-only for the active mode.  The real _set_prop() returns
  the PTP response code (non-zero) without raising.  Simulate via
  ``set_rejection_codes``.

There is no "invalid value" validation in the camera: it accepts any uint16
and either stores it or rejects it via the response code.  The fake models
the same contract.

Usage::

    device = FakePTPDevice(
        int_values={0xD192: 1, 0xD190: 65535},
        string_values={0xD18D: "My Slot"},
    )

    # Simulate a USB timeout when reading FilmSimulation:
    device = FakePTPDevice(
        get_errors={0xD192: CameraConnectionError("USB timeout")},
    )

    # Simulate camera rejecting a write (returns non-zero rc, no exception):
    device = FakePTPDevice(
        set_rejection_codes={0xD191: 0x2005},
    )

    # Simulate USB disconnect during a write:
    device = FakePTPDevice(
        set_errors={0xD191: CameraConnectionError("cable pulled")},
    )
"""

from __future__ import annotations

from src.domain.camera.ptp_device import CameraConnectionError


class FakePTPDevice:
    """
    In-memory PTPDevice for unit tests.

    All three set_property_* variants write to a single shared store keyed
    by property code; the three get_property_* variants read from it.  This
    means a write-then-read round-trip works out of the box without any extra
    configuration.

    Args:
        int_values:
            Initial property store for integer-valued properties.
            Keyed by PTP property code.  Reads from missing codes return 0.
        string_values:
            Initial property store for string-valued properties.
            Keyed by PTP property code.  Reads from missing codes return "".
        camera_name:
            Value returned by the ``camera_name`` property.
        ping_fails:
            If True, ``ping()`` returns -1 (camera unreachable) instead of 0.
        get_errors:
            Mapping of property code → exception instance.  When a get is
            attempted for that code the exception is raised, simulating a USB
            transport failure on a specific property.
        default_get_error:
            Exception raised for *any* get call whose code is not in
            ``get_errors``.  Affects both int and string reads.
        default_int_get_error:
            Exception raised for any *integer* get call (get_property_int /
            get_property_int16) whose code is not in ``get_errors``.  String
            reads are unaffected.  Use this to simulate the verification phase
            failing while the initial slot-name read still succeeds.
        int_read_overrides:
            Mapping of property code → int value returned on every read of
            that code, regardless of what was written to the store.  Use this
            to simulate the camera normalising a write to a different value
            (e.g. GrainEffect Off write → camera stores 6 or 7).
        str_read_overrides:
            Mapping of property code → str value returned on every read of
            that code, regardless of what was written to the store.  Use this
            to simulate the camera storing a different string than what was
            written (e.g. truncating a slot name).
        set_errors:
            Mapping of property code → exception instance.  When a set is
            attempted for that code the exception is raised, simulating a USB
            transport failure mid-write.
        set_rejection_codes:
            Mapping of property code → non-zero PTP response code.  When a
            set is attempted for that code the rejection code is returned and
            the internal store is NOT updated, simulating the camera declining
            the write without a transport error.
    """

    def __init__(
        self,
        *,
        int_values: dict[int, int] | None = None,
        string_values: dict[int, str] | None = None,
        camera_name: str = "X-S10",
        ping_fails: bool = False,
        get_errors: dict[int, Exception] | None = None,
        default_get_error: Exception | None = None,
        default_int_get_error: Exception | None = None,
        int_read_overrides: dict[int, int] | None = None,
        set_errors: dict[int, Exception] | None = None,
        set_rejection_codes: dict[int, int] | None = None,
        str_read_overrides: dict[int, str] | None = None,
    ) -> None:
        self._int_store: dict[int, int] = dict(int_values or {})
        self._str_store: dict[int, str] = dict(string_values or {})
        self._camera_name = camera_name
        self._ping_fails = ping_fails
        self._get_errors: dict[int, Exception] = dict(get_errors or {})
        self._default_get_error = default_get_error
        self._default_int_get_error = default_int_get_error
        self._int_read_overrides: dict[int, int] = dict(int_read_overrides or {})
        self._str_read_overrides: dict[int, str] = dict(str_read_overrides or {})
        self._set_errors: dict[int, Exception] = dict(set_errors or {})
        self._set_rejection_codes: dict[int, int] = dict(set_rejection_codes or {})

    # ------------------------------------------------------------------
    # Connection lifecycle — no-ops in the fake
    # ------------------------------------------------------------------

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Liveness
    # ------------------------------------------------------------------

    def ping(self) -> int:
        return -1 if self._ping_fails else 0

    # ------------------------------------------------------------------
    # Property reads
    # ------------------------------------------------------------------

    def get_property_int(self, code: int) -> int:
        if code in self._get_errors:
            raise self._get_errors[code]
        if self._default_int_get_error is not None:
            raise self._default_int_get_error
        if self._default_get_error is not None:
            raise self._default_get_error
        if code in self._int_read_overrides:
            return self._int_read_overrides[code]
        return self._int_store.get(code, 0)

    def get_property_int16(self, code: int) -> int:
        raw = self.get_property_int(code)
        v = raw & 0xFFFF
        return v - 65536 if v >= 32768 else v

    def get_property_string(self, code: int) -> str:
        if code in self._get_errors:
            raise self._get_errors[code]
        if self._default_get_error is not None:
            raise self._default_get_error
        if code in self._str_read_overrides:
            return self._str_read_overrides[code]
        return self._str_store.get(code, "")

    # ------------------------------------------------------------------
    # Property writes
    # ------------------------------------------------------------------

    def set_property_int(self, code: int, value: int) -> int:
        return self._set(code, int_value=value)

    def set_property_uint16(self, code: int, value: int) -> int:
        return self._set(code, int_value=value & 0xFFFF)

    def set_property_string(self, code: int, value: str) -> int:
        return self._set(code, str_value=value)

    # ------------------------------------------------------------------
    # Camera identity
    # ------------------------------------------------------------------

    @property
    def camera_name(self) -> str:
        return self._camera_name

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set(
        self,
        code: int,
        *,
        int_value: int | None = None,
        str_value: str | None = None,
    ) -> int:
        if code in self._set_errors:
            raise self._set_errors[code]
        if code in self._set_rejection_codes:
            return self._set_rejection_codes[code]
        if int_value is not None:
            self._int_store[code] = int_value
        if str_value is not None:
            self._str_store[code] = str_value
        return 0
