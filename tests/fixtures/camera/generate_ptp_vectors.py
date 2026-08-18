"""
Regenerate ptp_vectors.json, the golden bytes shared by the Python and
JavaScript PTP transports.

    FILMCASE_ENV_FILE=/dev/null .venv/bin/python tests/fixtures/camera/generate_ptp_vectors.py

These pin the wire format itself: what a command container looks like, how a PTP
string is counted, where the fields of a DeviceInfo payload sit. Both suites
build the same inputs and assert the same hex, which is what proves the two
transports put identical bytes on the wire.

Regenerate deliberately. A diff here means the framing changed, and framing is
the one thing a camera will not forgive.
"""

from __future__ import annotations

import json
import os
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.config.settings")

import django  # noqa: E402

django.setup()

from src.domain.camera import ptp_usb_device as ptp  # noqa: E402

OUT = pathlib.Path(__file__).with_name("ptp_vectors.json")


def _hex(data: bytes) -> str:
    return data.hex()


def _uint16_array(values: list[int]) -> bytes:
    return struct.pack("<I", len(values)) + struct.pack(f"<{len(values)}H", *values)


def _device_info_payload(
    *,
    manufacturer: str,
    model: str,
    supported_props: list[int],
    vendor_desc: str = "fujifilm.co.jp",
) -> bytes:
    """Assemble a DeviceInfo data container the way a camera would."""
    body = b""
    body += struct.pack("<H", 100)                    # StandardVersion
    body += struct.pack("<I", 0x00000006)             # VendorExtensionID
    body += struct.pack("<H", 100)                    # VendorExtensionVersion
    body += ptp._encode_ptp_string(vendor_desc)       # VendorExtensionDesc
    body += struct.pack("<H", 0)                      # FunctionalMode
    body += _uint16_array([0x1001, 0x1002, 0x1003])   # OperationsSupported
    body += _uint16_array([0x4002])                   # EventsSupported
    body += _uint16_array(supported_props)            # DevicePropertiesSupported
    body += _uint16_array([])                         # CaptureFormats
    body += _uint16_array([0x3801])                   # ImageFormats
    body += ptp._encode_ptp_string(manufacturer)
    body += ptp._encode_ptp_string(model)
    body += ptp._encode_ptp_string("1.00")            # DeviceVersion
    body += ptp._encode_ptp_string("ABC123")          # SerialNumber
    return ptp._data_packet(ptp._OC_GET_DEVICE_INFO, 1, body)


COMMAND_PACKETS = [
    ("open_session", ptp._OC_OPEN_SESSION, 1, [ptp._SESSION_ID]),
    ("close_session", ptp._OC_CLOSE_SESSION, 7, []),
    ("get_device_info", ptp._OC_GET_DEVICE_INFO, 1, []),
    ("get_slot_name", ptp._OC_GET_DEVICE_PROP_VALUE, 2, [0xD18D]),
    ("set_film_simulation", ptp._OC_SET_DEVICE_PROP_VALUE, 3, [0xD192]),
    ("large_transaction_id", ptp._OC_GET_DEVICE_PROP_VALUE, 0xFFFF_FFF0, [0xD023]),
]

DATA_PACKETS = [
    ("int32_zero", ptp._OC_SET_DEVICE_PROP_VALUE, 4, struct.pack("<i", 0)),
    ("int32_positive", ptp._OC_SET_DEVICE_PROP_VALUE, 5, struct.pack("<i", 40)),
    ("int32_negative", ptp._OC_SET_DEVICE_PROP_VALUE, 6, struct.pack("<i", -40)),
    ("uint16_slot_cursor", ptp._OC_SET_DEVICE_PROP_VALUE, 8, struct.pack("<H", 4)),
    ("empty_payload", ptp._OC_SET_DEVICE_PROP_VALUE, 9, b""),
]

PTP_STRINGS = [
    ("empty", ""),
    ("single_char", "A"),
    ("recipe_name", "Kodak Portra"),
    ("max_length_ascii", "X" * 25),
    ("with_spaces_and_digits", "Provia 400 v2"),
]

RESPONSES = [
    ("ok_no_params", ptp._RC_OK, 1, []),
    ("session_already_open", ptp._RC_SESSION_ALREADY, 1, []),
    ("operation_not_supported", 0x2005, 2, []),
    ("access_denied", 0x201C, 3, []),
    ("with_params", ptp._RC_OK, 4, [1, 2]),
]

DEVICE_INFOS = [
    ("x_s10", "FUJIFILM", "X-S10", [0xD18C, 0xD18D, 0xD192, 0xD199]),
    ("no_supported_props", "FUJIFILM", "X-T4", []),
    ("empty_model", "FUJIFILM", "", [0xD023]),
]


def build() -> dict[str, object]:
    return {
        "comment": (
            "Golden bytes shared by the Python and JavaScript PTP transports. Both "
            "suites build the same inputs and assert the same hex, so the two cannot "
            "frame packets differently without a test failing. Regenerate with "
            "tests/fixtures/camera/generate_ptp_vectors.py, deliberately: a diff here "
            "means the wire format changed."
        ),
        "command_packets": [
            {"name": name, "code": code, "tx_id": tx, "params": params,
             "hex": _hex(ptp._command_packet(code, tx, *params))}
            for name, code, tx, params in COMMAND_PACKETS
        ],
        "data_packets": [
            {"name": name, "code": code, "tx_id": tx, "payload_hex": _hex(payload),
             "hex": _hex(ptp._data_packet(code, tx, payload))}
            for name, code, tx, payload in DATA_PACKETS
        ],
        "ptp_strings": [
            {"name": name, "value": value, "hex": _hex(ptp._encode_ptp_string(value))}
            for name, value in PTP_STRINGS
        ],
        "responses": [
            {
                "name": name,
                "hex": _hex(
                    struct.pack("<IHHI", 12 + len(params) * 4, ptp._PTP_RESPONSE, rc, tx)
                    + struct.pack(f"<{len(params)}I", *params)
                ),
                "expected_code": rc,
                "expected_params": params,
            }
            for name, rc, tx, params in RESPONSES
        ],
        "device_info": [
            {
                "name": name,
                "hex": _hex(
                    _device_info_payload(
                        manufacturer=manufacturer, model=model, supported_props=props
                    )
                ),
                "expected_model": model,
                "expected_supported_props": props,
            }
            for name, manufacturer, model, props in DEVICE_INFOS
        ],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {OUT}")
