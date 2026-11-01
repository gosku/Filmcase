"""
Verify a backup restore read back faithfully.

A faithful restore leaves the header and all seven slot records byte-identical
to the pushed blob. Differences are expected only in the live/global region and
the drift bytes, and in the per-slot write counter the camera manages itself, so
those are excluded.
"""
from __future__ import annotations

import attrs

from src.data.camera import constants_xt2 as xt2

# Bytes below this offset are the fixed header and must match (0xA8 is where the
# live/global region begins; the drift bytes live there and are not checked).
_HEADER_END: int = 0xA8
_SLOTS_END: int = xt2.SLOT0_OFFSET + xt2.SLOT_SIZE * xt2.SLOT_COUNT


@attrs.frozen
class RoundTripResult:
    """Whether a read-back matches the pushed blob in the header and slot regions."""

    ok: bool
    mismatches: tuple[int, ...]   # fidelity-region offsets that differ


def _is_fidelity_offset(offset: int) -> bool:
    if offset < _HEADER_END:
        return True
    if xt2.SLOT0_OFFSET <= offset < _SLOTS_END:
        within = (offset - xt2.SLOT0_OFFSET) % xt2.SLOT_SIZE
        return within != xt2.SLOT_WRITE_COUNTER_OFFSET
    return False


def verify_round_trip(read_back: bytes, pushed: bytes) -> RoundTripResult:
    """
    Compare a read-back blob to the pushed blob over the header and slot regions.

    Returns ``ok`` True when no fidelity-region byte differs; a size mismatch is
    itself a failure.
    """
    if len(read_back) != len(pushed):
        return RoundTripResult(ok=False, mismatches=())
    mismatches = tuple(
        offset
        for offset in range(len(pushed))
        if read_back[offset] != pushed[offset] and _is_fidelity_offset(offset)
    )
    return RoundTripResult(ok=not mismatches, mismatches=mismatches)
