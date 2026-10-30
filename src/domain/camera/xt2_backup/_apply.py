"""
Edit X-T2 recipe bytes into a backup blob, in place.

Overwrites only the target slot's recipe bytes and the recipe's global WB table
entry; never rebuilds the blob, so fixed-size fields cannot shift anything. Only
call after validate_backup passes and the push is feasible.
"""
from __future__ import annotations

from collections.abc import Sequence

from src.data.camera import constants_xt2 as xt2

from . import _mapping

# Inverse maps (domain value -> stored byte), derived from the canonical decoder maps.
_FILM_SIM_BYTE: dict[str, int] = {name: byte for byte, name in xt2.FILM_SIMULATION_BY_BYTE.items()}
_GRAIN_BYTE: dict[str, int] = {name: byte for byte, name in xt2.GRAIN_ROUGHNESS_BY_BYTE.items()}
_DR_BYTE: dict[str, int] = {name: byte for byte, name in xt2.DYNAMIC_RANGE_BY_BYTE.items()}
_COLOR_BYTE: dict[int, int] = {value: byte for byte, value in xt2.COLOR_VALUE_BY_BYTE.items()}
_WB_SELECTOR_BYTE: dict[str, int] = {
    name: byte for byte, name in xt2.WHITE_BALANCE_BY_SELECTOR.items()
}


def _tone_byte(value: int) -> int:
    return 4 - value          # highlight / shadow / sharpness: byte = 4 - value


def _nr_byte(value: int) -> int:
    return value + 4          # noise reduction: byte = value + 4


def _wb_shift_byte(shift: int) -> int:
    return 9 - shift          # WB R/B shift: byte = 9 - shift


def _write_name(out: bytearray, base: int, name: str) -> None:
    # ASCII, NUL-terminated, within the fixed name window. Only the name chars
    # and one terminator are written, leaving the rest of the window (including
    # the structural bytes past it) untouched, as the camera stores it.
    name_bytes = name.encode("ascii")
    if len(name_bytes) + 1 > xt2.NAME_FIELD_LEN:
        raise ValueError(f"name too long for the {xt2.NAME_FIELD_LEN}-byte field: {name!r}")
    for i, byte in enumerate(name_bytes):
        out[base + xt2.NAME_OFFSET + i] = byte
    out[base + xt2.NAME_OFFSET + len(name_bytes)] = 0


def _apply_one(out: bytearray, slot_index: int, mapping: _mapping.Xt2Mapping) -> None:
    base = xt2.SLOT0_OFFSET + slot_index * xt2.SLOT_SIZE

    out[base + xt2.OFF_FILM_SIMULATION] = _FILM_SIM_BYTE[mapping.film_simulation]
    out[base + xt2.OFF_GRAIN] = _GRAIN_BYTE[mapping.grain_roughness]
    out[base + xt2.OFF_DYNAMIC_RANGE] = _DR_BYTE[mapping.dynamic_range]
    out[base + xt2.OFF_WB_SELECTOR] = _WB_SELECTOR_BYTE[mapping.white_balance]
    out[base + xt2.OFF_HIGHLIGHT] = _tone_byte(mapping.highlight)
    out[base + xt2.OFF_SHADOW] = _tone_byte(mapping.shadow)
    out[base + xt2.OFF_SHARPNESS] = _tone_byte(mapping.sharpness)
    out[base + xt2.OFF_NOISE_REDUCTION] = _nr_byte(mapping.noise_reduction)
    out[base + xt2.OFF_COLOR] = _COLOR_BYTE[mapping.color]

    if mapping.white_balance == "Kelvin" and mapping.kelvin is not None:
        out[base + xt2.OFF_KELVIN_INDEX] = xt2.KELVIN_STEPS.index(mapping.kelvin)

    _write_name(out, base, mapping.name)

    # Global WB shift for this recipe's WB entry (shared across slots).
    index = xt2.WB_SHIFT_TABLE_INDEX[mapping.white_balance]
    shift_base = xt2.WB_SHIFT_TABLE_BASE + index * 2
    out[shift_base] = _wb_shift_byte(mapping.white_balance_red)
    out[shift_base + 1] = _wb_shift_byte(mapping.white_balance_blue)


def apply_recipe(blob: bytes, slot_index: int, mapping: _mapping.Xt2Mapping) -> bytes:
    """
    Return a copy of *blob* with *mapping* written into slot *slot_index* (0-based).
    """
    out = bytearray(blob)
    _apply_one(out, slot_index, mapping)
    return bytes(out)


def apply_recipes(
    blob: bytes, assignments: Sequence[tuple[int, _mapping.Xt2Mapping]]
) -> bytes:
    """
    Return a copy of *blob* with every (slot_index, mapping) assignment applied.

    Used for a collection push: all slots and their global WB entries are edited
    into one blob so the restore happens once. Feasibility must already guarantee
    the assignments do not set conflicting shifts on a shared WB entry.
    """
    out = bytearray(blob)
    for slot_index, mapping in assignments:
        _apply_one(out, slot_index, mapping)
    return bytes(out)
