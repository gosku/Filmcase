"""
Python half of the shared PTP wire-format golden vectors.

The JavaScript transport asserts against the same file. Between them these
tests say: both implementations put identical bytes on the wire.

A failure means the framing changed. Framing is the one thing a camera will not
forgive, so regenerate the fixture only once you are sure the new bytes are the
ones you meant to send.
"""

from __future__ import annotations

import json
import pathlib
import struct

import pytest

from src.domain.camera import ptp_usb_device as ptp

VECTORS_PATH = pathlib.Path(__file__).parents[3] / "fixtures" / "camera" / "ptp_vectors.json"

_FIXTURE = json.loads(VECTORS_PATH.read_text())


def _ids(records: list[dict]) -> list[str]:
    return [record["name"] for record in records]


class TestCommandPacketVectors:
    @pytest.mark.parametrize(
        "vector", _FIXTURE["command_packets"], ids=_ids(_FIXTURE["command_packets"])
    )
    def test_matches_the_frozen_bytes(self, vector) -> None:
        packet = ptp._command_packet(vector["code"], vector["tx_id"], *vector["params"])

        assert packet.hex() == vector["hex"]


class TestDataPacketVectors:
    @pytest.mark.parametrize(
        "vector", _FIXTURE["data_packets"], ids=_ids(_FIXTURE["data_packets"])
    )
    def test_matches_the_frozen_bytes(self, vector) -> None:
        payload = bytes.fromhex(vector["payload_hex"])

        packet = ptp._data_packet(vector["code"], vector["tx_id"], payload)

        assert packet.hex() == vector["hex"]


class TestPtpStringVectors:
    @pytest.mark.parametrize(
        "vector", _FIXTURE["ptp_strings"], ids=_ids(_FIXTURE["ptp_strings"])
    )
    def test_encodes_to_the_frozen_bytes(self, vector) -> None:
        assert ptp._encode_ptp_string(vector["value"]).hex() == vector["hex"]

    @pytest.mark.parametrize(
        "vector", _FIXTURE["ptp_strings"], ids=_ids(_FIXTURE["ptp_strings"])
    )
    def test_round_trips_back_to_the_original(self, vector) -> None:
        encoded = bytes.fromhex(vector["hex"])

        decoded, offset = ptp._decode_ptp_string(encoded, 0)

        assert decoded == vector["value"]
        assert offset == len(encoded)


class TestResponseVectors:
    @pytest.mark.parametrize(
        "vector", _FIXTURE["responses"], ids=_ids(_FIXTURE["responses"])
    )
    def test_parses_to_the_frozen_code_and_params(self, vector) -> None:
        code, params = ptp._parse_response(bytes.fromhex(vector["hex"]))

        assert code == vector["expected_code"]
        assert params == vector["expected_params"]


class TestDeviceInfoVectors:
    @pytest.mark.parametrize(
        "vector", _FIXTURE["device_info"], ids=_ids(_FIXTURE["device_info"])
    )
    def test_finds_the_model_name(self, vector) -> None:
        data = bytes.fromhex(vector["hex"])

        assert ptp._parse_device_info_model(data) == vector["expected_model"]

    @pytest.mark.parametrize(
        "vector", _FIXTURE["device_info"], ids=_ids(_FIXTURE["device_info"])
    )
    def test_finds_the_supported_properties(self, vector) -> None:
        data = bytes.fromhex(vector["hex"])

        assert ptp._parse_device_info_supported_props(data) == vector["expected_supported_props"]


class TestVectorsFixtureShape:
    def test_covers_every_section(self) -> None:
        # A truncated fixture would turn the parametrized tests above into zero
        # tests without failing anything.
        for section in ("command_packets", "data_packets", "ptp_strings", "responses", "device_info"):
            assert _FIXTURE[section], section

    def test_a_command_vector_carries_no_parameters(self) -> None:
        # The parameter-free path builds a bare 12-byte header, and an
        # off-by-one there is invisible until a camera rejects it.
        assert any(not v["params"] for v in _FIXTURE["command_packets"])

    def test_a_data_vector_carries_a_negative_int32(self) -> None:
        # Two's complement on the wire is the easiest thing for a port to get
        # wrong, so the vectors have to exercise it.
        negative = struct.pack("<i", -40).hex()
        assert any(v["payload_hex"] == negative for v in _FIXTURE["data_packets"])

    def test_a_string_vector_is_empty(self) -> None:
        # The empty string is a single zero byte, not a count of one plus a NUL.
        assert any(v["value"] == "" for v in _FIXTURE["ptp_strings"])
