"""
Strict validator for X-T2 settings-backup blobs (read-only, no camera).

The push path edits the blob by fixed byte offset, which is only safe if the
blob read back has the layout assumed. This is the pre-write GATE: it strictly
parses the recipe regions (header, 7 slot records, global WB table) and reports
whether the layout is confirmed. A caller MUST refuse to modify/restore a blob
whose validation is not ``ok``.

A shifted or wrong blob would have to land valid enum values at the film-sim,
WB-selector, DR and colour offsets of all seven slots at once, plus clean names
and in-range WB-table bytes; combined with the self-describing header anchors,
a layout shift fails the parse instead of silently corrupting a write.
"""
from __future__ import annotations

import struct
from collections.abc import Set

import attrs

from src.data.camera import constants_xt2 as xt2

_VALID_FILM_SIM: Set[int] = frozenset(xt2.FILM_SIMULATION_BY_BYTE)
_VALID_GRAIN: Set[int] = frozenset(xt2.GRAIN_ROUGHNESS_BY_BYTE)
_VALID_DR: Set[int] = frozenset(xt2.DYNAMIC_RANGE_BY_BYTE)
_VALID_WB_SEL: Set[int] = frozenset(xt2.WHITE_BALANCE_BY_SELECTOR)
_VALID_COLOR: Set[int] = frozenset(xt2.COLOR_VALUE_BY_BYTE)
_WB_SEL_COLOR_TEMP: int = 0x08


@attrs.frozen
class BackupValidationReport:
    """
    Outcome of validating a backup blob.

    ``ok`` is the hard gate: True means the recipe layout is confirmed and
    editing by offset is safe. ``errors`` explain a hard failure (do not write).
    ``warnings`` are soft signals worth noting but not blocking.
    """

    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def _check_header(blob: bytes, errors: list[str]) -> None:
    if len(blob) != xt2.BLOB_SIZE:
        errors.append(f"size {len(blob)} != {xt2.BLOB_SIZE}")
    if not blob.startswith(xt2.MAGIC):
        errors.append(f"magic != {xt2.MAGIC!r} (got {blob[: len(xt2.MAGIC)]!r})")
    for offset, want, label in (
        (xt2.HEADER_SIZE_OFFSET, xt2.HEADER_SIZE_VALUE, "header-size@0x98"),
        (xt2.BODY_SIZE_OFFSET, xt2.BODY_SIZE_VALUE, "body-size@0xA0"),
        (xt2.MARKER_OFFSET, xt2.MARKER_VALUE, "marker@0xAC"),
    ):
        if offset + 4 <= len(blob):
            got = struct.unpack_from("<I", blob, offset)[0]
            if got != want:
                errors.append(f"{label} {got} != {want}")


def _check_name(blob: bytes, base: int, slot: str, errors: list[str]) -> None:
    window = blob[base + xt2.NAME_OFFSET : base + xt2.NAME_OFFSET + xt2.NAME_FIELD_LEN]
    nul = window.find(0)
    if nul == -1:
        errors.append(f"{slot} name: no NUL terminator in the name window")
        return
    for i, char in enumerate(window[:nul]):
        if not (xt2.ASCII_MIN <= char <= xt2.ASCII_MAX):
            errors.append(f"{slot} name: non-printable byte 0x{char:02X} at name+{i}")
            return


def _check_slot(blob: bytes, idx: int, errors: list[str], warnings: list[str]) -> None:
    base = xt2.SLOT0_OFFSET + idx * xt2.SLOT_SIZE
    slot = f"C{idx + 1}"

    def in_range(offset: int, lo: int, hi: int, field: str) -> None:
        value = blob[base + offset]
        if not (lo <= value <= hi):
            errors.append(f"{slot} {field}: byte 0x{value:02X} out of range 0x{lo:02X}..0x{hi:02X}")

    def member(offset: int, valid: Set[int], field: str) -> None:
        value = blob[base + offset]
        if value not in valid:
            errors.append(f"{slot} {field}: byte 0x{value:02X} not a valid value")

    film_sim = blob[base + xt2.OFF_FILM_SIMULATION]
    member(xt2.OFF_FILM_SIMULATION, _VALID_FILM_SIM, "film-sim")
    member(xt2.OFF_GRAIN, _VALID_GRAIN, "grain")
    member(xt2.OFF_DYNAMIC_RANGE, _VALID_DR, "dynamic-range")
    member(xt2.OFF_WB_SELECTOR, _VALID_WB_SEL, "wb-selector")
    # Colour is retained-but-ignored on B&W sims, so only range-check it for colour sims.
    if film_sim not in xt2.BW_FILM_SIMULATION_BYTES:
        member(xt2.OFF_COLOR, _VALID_COLOR, "color")
    in_range(xt2.OFF_HIGHLIGHT, 0, xt2.TONE_BYTE_MAX, "highlight")
    in_range(xt2.OFF_SHADOW, 0, xt2.TONE_BYTE_MAX, "shadow")
    in_range(xt2.OFF_SHARPNESS, 0, xt2.SHARPNESS_BYTE_MAX, "sharpness")
    in_range(xt2.OFF_NOISE_REDUCTION, 0, xt2.NOISE_REDUCTION_BYTE_MAX, "noise-reduction")
    if blob[base + xt2.OFF_WB_SELECTOR] == _WB_SEL_COLOR_TEMP:
        in_range(xt2.OFF_KELVIN_INDEX, 0, len(xt2.KELVIN_STEPS) - 1, "kelvin-index")

    _check_name(blob, base, slot, errors)

    for offset, want in xt2.STRUCTURAL_ANCHORS.items():
        got = blob[base + offset]
        if got != want:
            warnings.append(
                f"{slot} structural anchor +0x{offset:02X}: 0x{got:02X} != expected 0x{want:02X}"
            )


def _check_wb_table(blob: bytes, errors: list[str]) -> None:
    for i in range(xt2.WB_SHIFT_ENTRIES * 2):
        offset = xt2.WB_SHIFT_TABLE_BASE + i
        value = blob[offset]
        if value > xt2.WB_SHIFT_BYTE_MAX:
            errors.append(
                f"WB-shift table @0x{offset:04X}: byte 0x{value:02X} > 0x{xt2.WB_SHIFT_BYTE_MAX:02X}"
            )


def validate_backup(blob: bytes) -> BackupValidationReport:
    """
    Strictly validate a backup blob's recipe regions.

    Callers must treat ``ok is False`` as a hard stop: do not modify or restore
    the blob.
    """
    errors: list[str] = []
    warnings: list[str] = []
    _check_header(blob, errors)
    # Only walk slots/WB table once the blob is at least the expected size, so
    # field reads cannot run past the buffer.
    if len(blob) >= xt2.BLOB_SIZE:
        for idx in range(xt2.SLOT_COUNT):
            _check_slot(blob, idx, errors, warnings)
        _check_wb_table(blob, errors)
    return BackupValidationReport(ok=not errors, errors=tuple(errors), warnings=tuple(warnings))
