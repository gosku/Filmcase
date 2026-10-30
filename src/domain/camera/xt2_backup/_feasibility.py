"""
Push-feasibility for the X-T2 global white balance.

Each WB entry (Auto, Daylight, ...) has ONE red/blue shift for the whole camera,
shared by every slot that uses it. So a recipe can go into a slot only if setting
its WB entry's shift would not change the white balance of another slot that is
kept and uses the same entry. Custom (measured) WB is not pushable at all.

Handles both the single-slot case and the collection case across several
assignments at once.
"""
from __future__ import annotations

from collections.abc import Sequence

import attrs

from src.data.camera import constants_xt2 as xt2

from . import _mapping

_SELECTOR_BYTE: dict[str, int] = {
    name: byte for byte, name in xt2.WHITE_BALANCE_BY_SELECTOR.items()
}


@attrs.frozen
class Feasibility:
    """Whether a push can go ahead without retuning a kept slot's white balance."""

    ok: bool
    conflicts: tuple[str, ...]
    notes: tuple[str, ...]


def _current_shift(blob: bytes, wb_name: str) -> tuple[int, int]:
    base = xt2.WB_SHIFT_TABLE_BASE + xt2.WB_SHIFT_TABLE_INDEX[wb_name] * 2
    return 9 - blob[base], 9 - blob[base + 1]


def _slots_using(blob: bytes, wb_name: str, *, excluding: set[int]) -> list[int]:
    selector = _SELECTOR_BYTE[wb_name]
    using: list[int] = []
    for other in range(xt2.SLOT_COUNT):
        if other in excluding:
            continue
        base = xt2.SLOT0_OFFSET + other * xt2.SLOT_SIZE
        if blob[base + xt2.OFF_WB_SELECTOR] == selector:
            using.append(other)
    return using


def _dropped_note(dropped: tuple[str, ...]) -> list[str]:
    return [f"Dropped (the X-T2 lacks these): {', '.join(dropped)}"] if dropped else []


def check_feasibility(blob: bytes, slot_index: int, mapping: _mapping.Xt2Mapping) -> Feasibility:
    """
    Decide whether *mapping* can be pushed into slot *slot_index* (0-based).
    """
    notes = _dropped_note(mapping.dropped)

    if mapping.white_balance in xt2.MEASURED_CUSTOM_WB:
        return Feasibility(
            ok=False,
            conflicts=(
                f"White balance '{mapping.white_balance}' is a measured Custom white balance "
                f"stored on the camera; it cannot be sent over USB, so this recipe cannot be pushed.",
            ),
            notes=tuple(notes),
        )

    want = (mapping.white_balance_red, mapping.white_balance_blue)
    current = _current_shift(blob, mapping.white_balance)
    # Feasibility is decided by the OTHER slots on this WB: a push is fine only
    # if it does not retune one that is kept.
    sharers = _slots_using(blob, mapping.white_balance, excluding={slot_index})
    conflicts: list[str] = []
    if want != current and sharers:
        # The detail names every slot on this WB, not the per-target sharers, so
        # it reads the same for each blocked slot and the picker shows it once,
        # behind the (i) on the single conflict note.
        users = _slots_using(blob, mapping.white_balance, excluding=set())
        names = ", ".join(f"C{other + 1}" for other in users)
        wb = mapping.white_balance
        if len(users) == 1:
            conflicts.append(
                f"White balance '{wb}' is already used by {names} with a different R/B shift. "
                f"Pushing this recipe into any other slot would change {names}'s white balance, "
                f"turning it into a different recipe. The only slot it can go in is {names}."
            )
        else:
            conflicts.append(
                f"White balance '{wb}' is used by {names}, each relying on its current R/B shift. "
                f"This recipe needs a different shift, and the camera keeps only one shift per white "
                f"balance, so pushing it would change all of them. Free '{wb}' down to a single slot first."
            )
    return Feasibility(ok=not conflicts, conflicts=tuple(conflicts), notes=tuple(notes))


def check_collection_feasibility(
    blob: bytes, assignments: Sequence[tuple[int, _mapping.Xt2Mapping]]
) -> Feasibility:
    """
    Decide whether every (slot_index, mapping) assignment can be pushed in one blob.

    Two ways a collection can fail: two assignments needing different shifts on
    the same WB entry (one global entry cannot hold both), or an assignment's WB
    entry being retuned while a kept slot (not in the push) still uses it.
    """
    conflicts: list[str] = []
    dropped = tuple(sorted({field for _, mapping in assignments for field in mapping.dropped}))
    notes = _dropped_note(dropped)
    overwritten = {slot_index for slot_index, _ in assignments}

    desired: dict[str, tuple[int, int]] = {}
    for slot_index, mapping in assignments:
        if mapping.white_balance in xt2.MEASURED_CUSTOM_WB:
            conflicts.append(
                f"C{slot_index + 1} '{mapping.name}': white balance "
                f"'{mapping.white_balance}' is a measured Custom WB, not pushable."
            )
            continue
        want = (mapping.white_balance_red, mapping.white_balance_blue)
        if mapping.white_balance in desired and desired[mapping.white_balance] != want:
            conflicts.append(
                f"White balance '{mapping.white_balance}' needs two different shifts in this "
                f"collection; the camera has only one shift for it."
            )
        else:
            desired[mapping.white_balance] = want

    for wb_name, want in desired.items():
        if want == _current_shift(blob, wb_name):
            continue
        kept = _slots_using(blob, wb_name, excluding=overwritten)
        if kept:
            names = ", ".join(f"C{other + 1}" for other in kept)
            conflicts.append(
                f"White balance '{wb_name}' has one global shift; setting it to "
                f"(R{want[0]:+d}, B{want[1]:+d}) would change kept slot(s) {names} that use it."
            )

    return Feasibility(ok=not conflicts, conflicts=tuple(conflicts), notes=tuple(notes))
