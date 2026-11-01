"""
Decode X-T2 backup-blob slot records into domain objects.

Applies the fixed-offset field map in src.data.camera.constants_xt2 (proven on
hardware). Read-only: pure functions over the blob bytes.
"""
from __future__ import annotations

from src.data.camera import constants
from src.data.camera import constants_xt2 as xt2
from src.domain.camera import queries as camera_queries
from src.domain.images import dataclasses as image_dataclasses


def _signed(value: int) -> str:
    """Format a signed int as a recipe string (2 -> '+2', -1 -> '-1', 0 -> '0')."""
    return f"+{value}" if value > 0 else str(value)


def _slot_base(slot_index: int) -> int:
    return xt2.SLOT0_OFFSET + slot_index * xt2.SLOT_SIZE


def _slot_name(blob: bytes, base: int) -> str:
    window = blob[base + xt2.NAME_OFFSET : base + xt2.NAME_OFFSET + xt2.NAME_FIELD_LEN]
    return window.split(b"\x00", 1)[0].decode("ascii", "replace")


def _wb_shift(blob: bytes, wb_name: str) -> tuple[int, int]:
    """Return the (red, blue) global shift for a WB entry, or (0, 0) if untabled."""
    index = xt2.WB_SHIFT_TABLE_INDEX.get(wb_name)
    if index is None:
        return 0, 0
    base = xt2.WB_SHIFT_TABLE_BASE + index * 2
    return 9 - blob[base], 9 - blob[base + 1]


def decode_slot_states(blob: bytes) -> list[camera_queries.SlotState]:
    """
    Read the name and film simulation of each custom slot from the blob.

    The X-T2 film-sim byte is mapped to its domain name and then to the shared
    per-property PTP value, so the returned SlotState is identical in shape to
    the per-property strategy's and ``film_sim_name`` resolves the same way.
    """
    states: list[camera_queries.SlotState] = []
    for idx in range(xt2.SLOT_COUNT):
        base = _slot_base(idx)
        name = _slot_name(blob, base)
        sim_name = xt2.FILM_SIMULATION_BY_BYTE.get(blob[base + xt2.OFF_FILM_SIMULATION])
        film_sim_ptp = constants.FILM_SIMULATION_TO_PTP.get(sim_name, 0) if sim_name else 0
        states.append(
            camera_queries.SlotState(index=idx + 1, name=name, film_sim_ptp=film_sim_ptp)
        )
    return states


def decode_slot_recipe(blob: bytes, slot_index: int) -> image_dataclasses.FujifilmRecipeData:
    """
    Decode one custom slot (1-based) into a FujifilmRecipeData.

    Fields the X-T2 lacks (D-Range Priority, grain size, Color Chrome Effect,
    Color Chrome FX Blue, Clarity, monochromatic tuning) come back as empty
    strings. Colour is omitted for black-and-white simulations.
    """
    base = _slot_base(slot_index - 1)
    sim_byte = blob[base + xt2.OFF_FILM_SIMULATION]
    sim_name = xt2.FILM_SIMULATION_BY_BYTE.get(sim_byte, "")
    is_bw = sim_byte in xt2.BW_FILM_SIMULATION_BYTES

    wb_name = xt2.WHITE_BALANCE_BY_SELECTOR.get(blob[base + xt2.OFF_WB_SELECTOR], "")
    wb_red, wb_blue = _wb_shift(blob, wb_name)
    if wb_name == "Kelvin":
        kelvin_index = blob[base + xt2.OFF_KELVIN_INDEX]
        kelvin = xt2.KELVIN_STEPS[kelvin_index] if kelvin_index < len(xt2.KELVIN_STEPS) else 0
        white_balance = f"{kelvin}K"
    else:
        white_balance = wb_name

    color_value = xt2.COLOR_VALUE_BY_BYTE.get(blob[base + xt2.OFF_COLOR])
    color = "" if is_bw or color_value is None else _signed(color_value)

    return image_dataclasses.FujifilmRecipeData(
        name=_slot_name(blob, base),
        film_simulation=sim_name,
        white_balance=white_balance,
        white_balance_red=wb_red,
        white_balance_blue=wb_blue,
        dynamic_range=xt2.DYNAMIC_RANGE_BY_BYTE.get(blob[base + xt2.OFF_DYNAMIC_RANGE], ""),
        d_range_priority="",
        grain_roughness=xt2.GRAIN_ROUGHNESS_BY_BYTE.get(blob[base + xt2.OFF_GRAIN], ""),
        grain_size="",
        color_chrome_effect="",
        color_chrome_fx_blue="",
        color=color,
        sharpness=_signed(4 - blob[base + xt2.OFF_SHARPNESS]),
        highlight=_signed(4 - blob[base + xt2.OFF_HIGHLIGHT]),
        shadow=_signed(4 - blob[base + xt2.OFF_SHADOW]),
        high_iso_nr=_signed(blob[base + xt2.OFF_NOISE_REDUCTION] - 4),
        clarity="",
    )
