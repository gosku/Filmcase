"""
Read-only queries against a Fujifilm PTP/USB camera.

All functions accept a PTPDevice instance and return pure Python values —
no database access, no side effects.

The recipe_to_ptp_values() function converts an FujifilmRecipeData domain
object into a RecipePTPValues consumed by operations.push_recipe().
"""

from __future__ import annotations

import time

import attrs

from src.data.camera import constants
from src.domain.camera import events
from src.domain.camera.ptp_device import CameraConnectionError, PTPDevice
from src.domain.camera.validation import validate_recipe_for_camera
from src.domain.images.dataclasses import FujifilmRecipeData

# ---------------------------------------------------------------------------
# Lookup tables for read (PTP int → domain value)
# ---------------------------------------------------------------------------

_PTP_TO_WB = {v: k for k, v in constants.WHITE_BALANCE_TO_PTP.items()}
_PTP_TO_DR = {v: k for k, v in constants.DRANGE_MODE_TO_PTP.items()}

# ---------------------------------------------------------------------------
# Lookup tables for write (domain value → PTP int)
# ---------------------------------------------------------------------------

_GRAIN_TO_PTP: dict[tuple[str, str], int] = {
    v: k for k, v in constants.CUSTOM_SLOT_GRAIN_PTP.items()
}
_CCE_TO_PTP: dict[str, int] = {v: k for k, v in constants.CUSTOM_SLOT_CCE_PTP.items()}
_CFX_TO_PTP: dict[str, int] = {v: k for k, v in constants.CUSTOM_SLOT_CFX_PTP.items()}
_NR_TO_PTP: dict[int, int] = {v: k for k, v in constants.CUSTOM_SLOT_NR_DECODE.items()}
_DR_PRIORITY_TO_PTP: dict[str, int] = {v: k for k, v in constants.CUSTOM_SLOT_DR_PRIORITY_DECODE.items()}


# ---------------------------------------------------------------------------
# Event-publishing property-read helpers
# ---------------------------------------------------------------------------


def _get_int(device: PTPDevice, code: int) -> int:
    """Read a 32-bit int property, publishing a read event on success or failure."""
    try:
        value = device.get_property_int(code)
        events.publish_event(
            event_type=events.PTP_READ_SUCCEEDED,
            params={"description": f"0x{code:04X} = {value}"},
        )
        return value
    except CameraConnectionError as exc:
        events.publish_event(
            event_type=events.PTP_READ_FAILED,
            params={"description": f"0x{code:04X}: {exc}"},
        )
        raise


def _get_int16(device: PTPDevice, code: int) -> int:
    """Read an int16 property, publishing a read event on success or failure."""
    try:
        value = device.get_property_int16(code)
        events.publish_event(
            event_type=events.PTP_READ_SUCCEEDED,
            params={"description": f"0x{code:04X} = {value}"},
        )
        return value
    except CameraConnectionError as exc:
        events.publish_event(
            event_type=events.PTP_READ_FAILED,
            params={"description": f"0x{code:04X}: {exc}"},
        )
        raise


def _get_str(device: PTPDevice, code: int) -> str:
    """Read a string property, publishing a read event on success or failure."""
    try:
        value = device.get_property_string(code)
        events.publish_event(
            event_type=events.PTP_READ_SUCCEEDED,
            params={"description": f"0x{code:04X} = {value!r}"},
        )
        return value
    except CameraConnectionError as exc:
        events.publish_event(
            event_type=events.PTP_READ_FAILED,
            params={"description": f"0x{code:04X}: {exc}"},
        )
        raise


def _signed(v: int | float) -> str:
    """Format a signed number as a recipe string (e.g. 2 → '+2', -1.5 → '-1.5').

    Integer values are formatted without a decimal point; half-steps are preserved.
    """
    if v == int(v):
        v = int(v)
    return f"+{v}" if v > 0 else str(v)


# ---------------------------------------------------------------------------
# Read-only camera queries
# ---------------------------------------------------------------------------

@attrs.frozen
class CameraInfo:
    """Snapshot of camera identity and status, collected without modifying state."""
    camera_name: str
    battery_raw: int       # raw PTP value from PROP_BATTERY
    usb_mode: int          # raw PTP value from 0xD16E (USBMode)
    firmware_version: int  # raw PTP value from 0xD153 (FirmwareVersion)


def camera_info(device: PTPDevice) -> CameraInfo:
    """
    Read camera identity and status properties without modifying any state.

    This is safe to call at any time after connect().
    """
    battery_raw = _get_int(device, constants.PROP_BATTERY)
    usb_mode = _get_int(device, 0xD16E)         # PTP_DPC_FUJI_USBMode
    try:
        firmware_version = _get_int(device, 0xD153)  # PTP_DPC_FUJI_FirmwareVersion
    except CameraConnectionError:
        firmware_version = 0  # not supported on all models (e.g. X-S10)

    return CameraInfo(
        camera_name=device.camera_name,
        battery_raw=battery_raw,
        usb_mode=usb_mode,
        firmware_version=firmware_version,
    )


@attrs.frozen
class SlotState:
    """Current state of one custom C1–Cn slot as read from the camera."""
    index: int       # 1-based slot number
    name: str        # display name stored in the slot
    film_sim_ptp: int  # raw PTP FilmSimulation value (see constants.PTP_TO_FILM_SIMULATION)

    @property
    def film_sim_name(self) -> str:
        return constants.PTP_TO_FILM_SIMULATION.get(self.film_sim_ptp, f"Unknown({self.film_sim_ptp})")


def slot_states(device: PTPDevice, slot_count: int) -> list[SlotState]:
    """
    Read the current content (name + film sim) of each custom slot.

    This is a read-only scan — it positions the slot cursor to each slot
    in turn, then reads back the name and film sim value.  The cursor is
    left pointing at the last slot after the call.

    Args:
        device:     Connected PTP device.
        slot_count: Number of custom slots supported by this camera model.

    Returns:
        List of SlotState, one per slot, in slot order (index 1..slot_count).
    """
    states: list[SlotState] = []
    for idx in range(1, slot_count + 1):
        device.set_property_uint16(constants.PROP_SLOT_CURSOR, idx)
        time.sleep(0.05)  # 50 ms between slots

        try:
            name = _get_str(device, constants.PROP_SLOT_NAME)
        except CameraConnectionError:
            name = ""  # older models (e.g. X-T2) don't serve 0xD18D as a string
        try:
            film_sim_raw = _get_int(device, constants.CUSTOM_SLOT_CODES["FilmSimulation"])
        except CameraConnectionError:
            film_sim_raw = 0  # older models (e.g. X-T2) don't support custom-slot codes
        states.append(SlotState(index=idx, name=name, film_sim_ptp=film_sim_raw))

    return states


def slot_recipe(device: PTPDevice, slot_index: int) -> FujifilmRecipeData:
    """
    Read all recipe parameters stored in a single custom slot.

    Positions the slot cursor to *slot_index*, reads every property that has a
    known PTP code in CUSTOM_SLOT_CODES, and returns a FujifilmRecipeData.
    Fields with no PTP equivalent (grain_size, monochromatic
    tuning) are returned as empty strings.

    Args:
        device:     Connected PTP device.
        slot_index: 1-based slot number (e.g. 1 for C1).

    Returns:
        FujifilmRecipeData populated from the camera's current slot state.
    """
    device.set_property_uint16(constants.PROP_SLOT_CURSOR, slot_index)
    time.sleep(0.05)  # 50 ms settle

    codes = constants.CUSTOM_SLOT_CODES

    name         = _get_str(device, constants.PROP_SLOT_NAME)
    film_sim_raw = _get_int(device, codes["FilmSimulation"])
    wb_raw       = _get_int(device, codes["WhiteBalance"])
    wb_kelvin    = _get_int(device, codes["WhiteBalanceColorTemperature"])
    wb_red       = _get_int16(device, codes["WhiteBalanceRed"])
    wb_blue      = _get_int16(device, codes["WhiteBalanceBlue"])
    dr_raw       = _get_int(device, codes["DRangeMode"])
    grain_raw    = _get_int(device, codes["GrainEffect"])
    cce_raw      = _get_int(device, codes["ColorEffect"])
    cfx_raw      = _get_int(device, codes["ColorFx"])
    color_raw    = _get_int16(device, codes["ColorMode"])
    sharp_raw    = _get_int16(device, codes["Sharpness"])
    hi_raw       = _get_int16(device, codes["HighLightTone"])
    sh_raw       = _get_int16(device, codes["ShadowTone"])
    nr_raw       = _get_int(device, codes["HighIsoNoiseReduction"])
    clarity_raw  = _get_int16(device, codes["Definition"])
    mc_wc_raw    = _get_int16(device, codes["MonochromaticColorWarmCool"])
    mc_mg_raw    = _get_int16(device, codes["MonochromaticColorMagentaGreen"])
    dr_pri_raw   = _get_int(device, codes["DRangePriority"])

    # White balance: if the mode is Kelvin, express as "6500K" etc.
    wb_label = _PTP_TO_WB.get(wb_raw, "")
    wb_str = f"{wb_kelvin}K" if wb_label == "Kelvin" else wb_label

    # NR uses a non-linear lookup; unknown raw values become "".
    nr_domain = constants.CUSTOM_SLOT_NR_DECODE.get(nr_raw)
    nr_str = _signed(nr_domain) if nr_domain is not None else ""

    grain_roughness, grain_size = constants.CUSTOM_SLOT_GRAIN_PTP.get(grain_raw, ("", ""))

    return FujifilmRecipeData(
        name=name,
        film_simulation=constants.PTP_TO_FILM_SIMULATION.get(film_sim_raw, ""),
        white_balance=wb_str,
        white_balance_red=wb_red,
        white_balance_blue=wb_blue,
        dynamic_range=_PTP_TO_DR.get(dr_raw, ""),
        d_range_priority=constants.CUSTOM_SLOT_DR_PRIORITY_DECODE.get(dr_pri_raw, ""),
        grain_roughness=grain_roughness,
        grain_size=grain_size,
        color_chrome_effect=constants.CUSTOM_SLOT_CCE_PTP.get(cce_raw, ""),
        color_chrome_fx_blue=constants.CUSTOM_SLOT_CFX_PTP.get(cfx_raw, ""),
        color=_signed(color_raw / 10),
        sharpness=_signed(sharp_raw / 10),
        highlight=_signed(hi_raw / 10),
        shadow=_signed(sh_raw / 10),
        high_iso_nr=nr_str,
        clarity=_signed(clarity_raw / 10),
        monochromatic_color_warm_cool=_signed(mc_wc_raw / 10),
        monochromatic_color_magenta_green=_signed(mc_mg_raw / 10),
    )


def custom_slot_count(camera_name: str) -> int:
    """
    Return the number of custom slots for the given camera model.

    Returns 0 for unknown models or cameras that do not support custom slots.
    """
    return constants.CAMERA_CUSTOM_SLOT_COUNTS.get(camera_name, 0)


# ---------------------------------------------------------------------------
# Recipe → PTP value conversion
# ---------------------------------------------------------------------------

@attrs.frozen
class RecipePTPValues:
    """
    PTP integer values to write for each custom-slot property.

    Attribute names mirror the keys of constants.CUSTOM_SLOT_CODES.

    Required fields are always written — they are guaranteed non-None after
    validate_recipe_for_camera().  Optional fields (int | None) are only
    written when not None; None means the property is not applicable for this
    recipe (e.g. DRangeMode when D-Range Priority is active).
    """
    # Always written — correspond to required (non-None) fields in FujifilmRecipeData
    FilmSimulation: int
    WhiteBalance: int
    WhiteBalanceRed: int
    WhiteBalanceBlue: int
    DRangePriority: int
    GrainEffect: int
    ColorEffect: int
    ColorFx: int
    Sharpness: int
    HighIsoNoiseReduction: int
    Definition: int
    # Conditionally written — correspond to str | None fields in FujifilmRecipeData
    WhiteBalanceColorTemperature: int | None = None
    DRangeMode: int | None = None
    ColorMode: int | None = None
    HighLightTone: int | None = None
    ShadowTone: int | None = None
    MonochromaticColorWarmCool: int | None = None
    MonochromaticColorMagentaGreen: int | None = None

    def items(self) -> list[tuple[int, int]]:
        """Return (ptp_code, value) pairs for all properties that are set.

        Write order matters: WhiteBalanceColorTemperature must be written
        before WhiteBalanceRed/WhiteBalanceBlue; otherwise the camera resets
        the shift values to 0 when the colour temperature is applied.
        """
        codes = constants.CUSTOM_SLOT_CODES
        _WRITE_ORDER = [
            "FilmSimulation",
            "WhiteBalance",
            "WhiteBalanceColorTemperature",  # must precede Red/Blue
            "WhiteBalanceRed",
            "WhiteBalanceBlue",
            "DRangePriority",
            "DRangeMode",
            "GrainEffect",
            "ColorEffect",
            "ColorFx",
            "ColorMode",
            "Sharpness",
            "HighLightTone",
            "ShadowTone",
            "HighIsoNoiseReduction",
            "Definition",
            "MonochromaticColorWarmCool",
            "MonochromaticColorMagentaGreen",
        ]
        return [
            (codes[name], getattr(self, name))
            for name in _WRITE_ORDER
            if getattr(self, name) is not None
        ]


def recipe_to_ptp_values(recipe: FujifilmRecipeData) -> RecipePTPValues:
    """
    Convert a FujifilmRecipeData domain object into a RecipePTPValues using
    custom-slot property codes (0xD18C–0xD1A2).

    Properties that cannot be mapped (e.g. unsupported film simulations) are
    left as None and will not be written.
    """
    validate_recipe_for_camera(recipe)

    # --- Film simulation (always set after validation) ---
    film_sim: int = constants.FILM_SIMULATION_TO_PTP[recipe.film_simulation]

    # --- White balance mode (always set after validation) ---
    # recipe.white_balance is either an enum label (e.g. "Auto") or "6500K".
    wb_label = recipe.white_balance
    if wb_label.endswith("K") and wb_label[:-1].isdigit():
        wb: int = constants.WHITE_BALANCE_TO_PTP["Kelvin"]
        wb_kelvin: int | None = int(wb_label[:-1])
    else:
        wb = constants.WHITE_BALANCE_TO_PTP[wb_label]
        wb_kelvin = None

    # --- D-Range Priority (always written; unset → Off) ---
    drp = recipe.d_range_priority
    dr_priority: int = _DR_PRIORITY_TO_PTP.get(drp, _DR_PRIORITY_TO_PTP["Off"])

    # --- D-Range mode ---
    # D-Range Priority takes precedence; skip DRangeMode when active.
    if drp and drp != "Off":
        dr_mode: int | None = None
    else:
        dr_mode = constants.DRANGE_MODE_TO_PTP.get(recipe.dynamic_range) if recipe.dynamic_range not in (None, "") else None

    # --- Grain effect (always written) ---
    # Write 1 for any Off roughness; camera normalises to 6 (Off+Small) or
    # 7 (Off+Large), retaining the last remembered size (X-S10 confirmed 2026-03-26).
    if recipe.grain_roughness == "Off":
        grain: int = 1
    else:
        assert recipe.grain_size is not None  # guaranteed by validate_recipe_for_camera
        grain = _GRAIN_TO_PTP[(recipe.grain_roughness, recipe.grain_size)]

    # --- Color chrome effect / FX blue (always written; unset → Off) ---
    cce: int = _CCE_TO_PTP.get(recipe.color_chrome_effect, _CCE_TO_PTP["Off"])
    cfx: int = _CFX_TO_PTP.get(recipe.color_chrome_fx_blue, _CFX_TO_PTP["Off"])

    # --- Scaled int16 fields (value × 10) ---
    color = int(recipe.color) * 10 if recipe.color not in (None, "") else None
    # Sharpness and clarity always written; unset → 0 (normal)
    sharpness: int = int(recipe.sharpness) * 10 if recipe.sharpness not in (None, "", "N/A") else 0
    # Half-step values possible (e.g. +1.5); round after ×10.
    highlight = round(float(recipe.highlight) * 10) if recipe.highlight not in (None, "") else None
    shadow = round(float(recipe.shadow) * 10) if recipe.shadow not in (None, "") else None
    clarity: int = int(recipe.clarity) * 10 if recipe.clarity not in (None, "", "N/A") else 0

    # --- High ISO noise reduction (non-linear lookup; always written; unset → 0/normal) ---
    nr: int = _NR_TO_PTP[int(recipe.high_iso_nr)] if recipe.high_iso_nr not in (None, "", "N/A") else _NR_TO_PTP[0]

    # --- Monochromatic colour tuning (int16 ÷ 10; confirmed 2026-03-26 X-S10) ---
    # None when film sim is not monochromatic (field not applicable).
    mono_wc = round(float(recipe.monochromatic_color_warm_cool) * 10) if recipe.monochromatic_color_warm_cool not in (None, "") else None
    mono_mg = round(float(recipe.monochromatic_color_magenta_green) * 10) if recipe.monochromatic_color_magenta_green not in (None, "") else None

    return RecipePTPValues(
        FilmSimulation=film_sim,
        WhiteBalance=wb,
        WhiteBalanceColorTemperature=wb_kelvin,
        WhiteBalanceRed=recipe.white_balance_red,
        WhiteBalanceBlue=recipe.white_balance_blue,
        DRangeMode=dr_mode,
        DRangePriority=dr_priority,
        GrainEffect=grain,
        ColorEffect=cce,
        ColorFx=cfx,
        ColorMode=color,
        Sharpness=sharpness,
        HighLightTone=highlight,
        ShadowTone=shadow,
        HighIsoNoiseReduction=nr,
        Definition=clarity,
        MonochromaticColorWarmCool=mono_wc,
        MonochromaticColorMagentaGreen=mono_mg,
    )
