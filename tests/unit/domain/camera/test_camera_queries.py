import attrs
import pytest
from decimal import Decimal

from src.data.camera.constants import DRANGE_MODE_TO_PTP, FILM_SIMULATION_TO_PTP, PTP_TO_FILM_SIMULATION
from src.domain.camera.queries import recipe_to_ptp_values
from src.domain.images.dataclasses import FujifilmRecipeData


def _make_recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        name="Test Recipe",
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


class TestFilmSimulationPTPMapping:
    """Verify all film simulation PTP values match the filmkit reference."""

    EXPECTED_VALUES = {
        "Provia": 1,
        "Velvia": 2,
        "Astia": 3,
        "Pro Neg. Hi": 4,
        "Pro Neg. Std": 5,
        "Monochrome STD": 6,
        "Monochrome Yellow": 7,
        "Monochrome Red": 8,
        "Monochrome Green": 9,
        "Sepia": 10,
        "Classic Chrome": 11,
        "Acros STD": 12,
        "Acros Yellow": 13,
        "Acros Red": 14,
        "Acros Green": 15,
        "Eterna": 16,
        "Classic Negative": 17,
        "Eterna Bleach Bypass": 18,
        "Nostalgic Negative": 19,
        "Reala Ace": 20,
    }

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_film_simulation_to_ptp(self, name, expected_ptp):
        assert FILM_SIMULATION_TO_PTP[name] == expected_ptp

    @pytest.mark.parametrize(
        "expected_ptp, name",
        [(v, k) for k, v in EXPECTED_VALUES.items()],
        ids=EXPECTED_VALUES.keys(),
    )
    def test_ptp_to_film_simulation(self, expected_ptp, name):
        assert PTP_TO_FILM_SIMULATION[expected_ptp] == name

    def test_no_gap_at_value_19(self):
        """Nostalgic Negative occupies value 19, between Eterna BB (18) and Reala Ace (20)."""
        assert FILM_SIMULATION_TO_PTP["Nostalgic Negative"] == 19

    def test_nostalgic_negative_round_trips_through_recipe(self):
        recipe = _make_recipe(film_simulation="Nostalgic Negative")
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.FilmSimulation == 19


class TestMonochromaticColorPTPMapping:
    """
    Verify MonochromaticColorWarmCool (0xD193) and MonochromaticColorMagentaGreen (0xD194)
    are encoded as value × 10 (int16), and are None for non-monochromatic film sims.

    Confirmed 2026-03-26 X-S10:
      -18 → 65356 (0xFF4C = -180 as int16)
        0 → 0
      +18 → 180
    """

    _MONO_SIM = "Acros STD"
    _NON_MONO_SIM = "Provia"

    @pytest.mark.parametrize("domain,expected_ptp", [
        ("-18", -180),
        ("-9",  -90),
        ("0",     0),
        ("+9",   90),
        ("+18",  180),
    ])
    def test_mono_warm_cool_encoding(self, domain, expected_ptp):
        recipe = _make_recipe(
            film_simulation=self._MONO_SIM,
            color=None,
            monochromatic_color_warm_cool=domain,
            monochromatic_color_magenta_green="0",
        )
        assert recipe_to_ptp_values(recipe).MonochromaticColorWarmCool == expected_ptp

    @pytest.mark.parametrize("domain,expected_ptp", [
        ("-18", -180),
        ("-9",  -90),
        ("0",     0),
        ("+9",   90),
        ("+18",  180),
    ])
    def test_mono_magenta_green_encoding(self, domain, expected_ptp):
        recipe = _make_recipe(
            film_simulation=self._MONO_SIM,
            color=None,
            monochromatic_color_warm_cool="0",
            monochromatic_color_magenta_green=domain,
        )
        assert recipe_to_ptp_values(recipe).MonochromaticColorMagentaGreen == expected_ptp

    @pytest.mark.parametrize("value", [None, ""])
    def test_mono_fields_none_for_non_mono_sim(self, value):
        recipe = _make_recipe(
            film_simulation=self._NON_MONO_SIM,
            monochromatic_color_warm_cool=value,
            monochromatic_color_magenta_green=value,
        )
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.MonochromaticColorWarmCool is None
        assert ptp.MonochromaticColorMagentaGreen is None


class TestDRangeModePTPMapping:
    """Verify all D-Range mode PTP values, especially the corrected DR-Auto."""

    EXPECTED_VALUES = {
        "DR-Auto": 65535,  # 0xFFFF — was incorrectly 0 before fix
        "DR100":   100,
        "DR200":   200,
        "DR400":   400,
    }

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_drange_mode_to_ptp(self, name, expected_ptp):
        assert DRANGE_MODE_TO_PTP[name] == expected_ptp

    def test_dr_auto_is_not_zero(self):
        """DR-Auto must be 0xFFFF, not 0. 0 was the pre-fix incorrect value."""
        assert DRANGE_MODE_TO_PTP["DR-Auto"] != 0
        assert DRANGE_MODE_TO_PTP["DR-Auto"] == 0xFFFF

    @pytest.mark.parametrize(
        "name, expected_ptp",
        EXPECTED_VALUES.items(),
        ids=EXPECTED_VALUES.keys(),
    )
    def test_dr_auto_round_trips_through_recipe(self, name, expected_ptp):
        recipe = _make_recipe(dynamic_range=name)
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.DRangeMode == expected_ptp


# ---------------------------------------------------------------------------
# Read event tests
# ---------------------------------------------------------------------------

from src.data.camera import constants as cam_constants
from src.domain.camera import events
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.queries import camera_info, slot_recipe, slot_states
from tests.fakes import FakePTPDevice


class TestReadSucceededEvents:
    def test_slot_recipe_publishes_succeeded_event_per_property(self, captured_logs):
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]: 1},
            string_values={cam_constants.PROP_SLOT_NAME: "Test"},
        )
        slot_recipe(device, slot_index=1)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # slot_recipe reads ~19 properties (1 string + 18 int/int16)
        assert len(succeeded) >= 19
        for evt in succeeded:
            assert "0x" in evt["description"]

    def test_camera_info_publishes_succeeded_events(self, captured_logs):
        device = FakePTPDevice()
        camera_info(device)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # battery, usb_mode, firmware_version (3 reads minimum)
        assert len(succeeded) >= 2  # firmware may be silently skipped on some models

    def test_slot_states_publishes_succeeded_events(self, captured_logs):
        device = FakePTPDevice()
        slot_states(device, slot_count=2)

        succeeded = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_SUCCEEDED
        ]
        # 2 slots × 2 reads each (name + film sim)
        assert len(succeeded) >= 4


class TestReadFailedEvents:
    def test_slot_recipe_publishes_failed_event_and_propagates(self, captured_logs):
        film_sim_code = cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            get_errors={film_sim_code: CameraConnectionError("USB timeout")}
        )
        with pytest.raises(CameraConnectionError):
            slot_recipe(device, slot_index=1)

        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert f"0x{film_sim_code:04X}" in failed[0]["description"]

    def test_camera_info_publishes_failed_event_for_firmware_and_continues(self, captured_logs):
        # firmware_version read is allowed to fail (older cameras); camera_info
        # catches the exception and sets firmware_version=0.
        device = FakePTPDevice(
            get_errors={0xD153: CameraConnectionError("not supported")}
        )
        info = camera_info(device)

        assert info.firmware_version == 0
        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert "0xD153" in failed[0]["description"]

    def test_slot_states_publishes_failed_event_for_slot_name_and_continues(self, captured_logs):
        # Slot name read fails (older models); slot_states catches it and uses "".
        device = FakePTPDevice(
            get_errors={cam_constants.PROP_SLOT_NAME: CameraConnectionError("not supported")}
        )
        states = slot_states(device, slot_count=1)

        assert states[0].name == ""
        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert len(failed) == 1
        assert f"0x{cam_constants.PROP_SLOT_NAME:04X}" in failed[0]["description"]

    def test_failed_event_description_contains_exception_message(self, captured_logs):
        film_sim_code = cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]
        device = FakePTPDevice(
            get_errors={film_sim_code: CameraConnectionError("USB timeout reason")}
        )
        with pytest.raises(CameraConnectionError):
            slot_recipe(device, slot_index=1)

        failed = [
            e for e in captured_logs
            if e.get("event_type") == events.PTP_READ_FAILED
        ]
        assert "USB timeout reason" in failed[0]["description"]


# ---------------------------------------------------------------------------
# Direct unit tests for recipe_to_ptp_values()
# ---------------------------------------------------------------------------


class TestRecipeToPTPValuesDirect:
    """
    Exhaustive unit tests for recipe_to_ptp_values(), driving FujifilmRecipeData
    directly — no factory, no DB layer.

    Tests verify two things for every field:
      1. The expected PTP integer is produced for each domain value.
      2. Optional RecipePTPValues attrs are None (i.e. not written to camera)
         when the corresponding recipe field is absent/inapplicable.
    """

    # ------------------------------------------------------------------
    # Minimal recipe shapes — all absent optional attrs must be None
    # ------------------------------------------------------------------

    def test_minimal_colour_recipe_all_optional_attrs_none(self):
        """
        A colour recipe supplying only required fields yields a RecipePTPValues
        where every optional attribute is None.
        """
        recipe = _make_recipe(
            white_balance="Auto",                    # not Kelvin → no WB temperature
            d_range_priority="Off",
            dynamic_range=None,                      # no DR mode
            grain_roughness="Off",
            grain_size=None,
            sharpness="0",
            high_iso_nr="0",
            clarity="0",
            highlight=None,
            shadow=None,
            color=None,
            monochromatic_color_warm_cool=None,
            monochromatic_color_magenta_green=None,
        )
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.WhiteBalanceColorTemperature is None
        assert ptp.DRangeMode is None
        assert ptp.ColorMode is None
        assert ptp.HighLightTone is None
        assert ptp.ShadowTone is None
        assert ptp.MonochromaticColorWarmCool is None
        assert ptp.MonochromaticColorMagentaGreen is None

    def test_minimal_mono_recipe_colour_mode_absent_mono_fields_present(self):
        """
        A monochromatic recipe without a color value has ColorMode=None,
        while MonochromaticColor fields are encoded when set.
        """
        recipe = _make_recipe(
            film_simulation="Acros STD",
            color=None,
            monochromatic_color_warm_cool="+9",
            monochromatic_color_magenta_green="-9",
        )
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.ColorMode is None
        assert ptp.MonochromaticColorWarmCool == 90
        assert ptp.MonochromaticColorMagentaGreen == -90

    # ------------------------------------------------------------------
    # FilmSimulation — all 20 values
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("film_sim, expected_ptp", [
        ("Provia",              1),
        ("Velvia",              2),
        ("Astia",               3),
        ("Pro Neg. Hi",         4),
        ("Pro Neg. Std",        5),
        ("Monochrome STD",      6),
        ("Monochrome Yellow",   7),
        ("Monochrome Red",      8),
        ("Monochrome Green",    9),
        ("Sepia",              10),
        ("Classic Chrome",     11),
        ("Acros STD",          12),
        ("Acros Yellow",       13),
        ("Acros Red",          14),
        ("Acros Green",        15),
        ("Eterna",             16),
        ("Classic Negative",   17),
        ("Eterna Bleach Bypass", 18),
        ("Nostalgic Negative", 19),
        ("Reala Ace",          20),
    ])
    def test_film_simulation_all_values(self, film_sim, expected_ptp):
        recipe = _make_recipe(film_simulation=film_sim)
        assert recipe_to_ptp_values(recipe).FilmSimulation == expected_ptp

    # ------------------------------------------------------------------
    # WhiteBalance — named modes and Kelvin strings
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("wb_label, expected_ptp", [
        ("Auto",                     0x0002),
        ("Auto (white priority)",    0x8020),
        ("Auto (ambience priority)", 0x8021),
        ("Daylight",                 0x0004),
        ("Incandescent",             0x0006),
        ("Fluorescent 1",            0x8001),
        ("Fluorescent 2",            0x8002),
        ("Fluorescent 3",            0x8003),
        ("Shade",                    0x8006),
        ("Underwater",               0x0008),
        ("Custom 1",                 0x8008),
        ("Custom 2",                 0x8009),
        ("Custom 3",                 0x800A),
    ])
    def test_white_balance_named_modes(self, wb_label, expected_ptp):
        recipe = _make_recipe(white_balance=wb_label)
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.WhiteBalance == expected_ptp
        assert ptp.WhiteBalanceColorTemperature is None

    @pytest.mark.parametrize("kelvin_str, expected_temp", [
        ("2500K",  2500),
        ("4000K",  4000),
        ("5500K",  5500),
        ("6500K",  6500),
        ("10000K", 10000),
    ])
    def test_kelvin_white_balance_sets_mode_and_temperature(self, kelvin_str, expected_temp):
        recipe = _make_recipe(white_balance=kelvin_str)
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.WhiteBalance == 0x8007          # Kelvin PTP code
        assert ptp.WhiteBalanceColorTemperature == expected_temp

    # ------------------------------------------------------------------
    # WhiteBalanceRed / WhiteBalanceBlue — direct pass-through
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("red, blue", [
        (0,   0),
        (3,  -5),
        (-9,  9),
        (18, -18),
    ])
    def test_white_balance_red_blue_pass_through(self, red, blue):
        recipe = _make_recipe(white_balance_red=red, white_balance_blue=blue)
        ptp = recipe_to_ptp_values(recipe)
        assert ptp.WhiteBalanceRed == red
        assert ptp.WhiteBalanceBlue == blue

    # ------------------------------------------------------------------
    # DRangePriority — all four domain values
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("drp, expected_ptp", [
        ("Off",    0),
        ("Weak",   1),
        ("Strong", 2),
        ("Auto",   32768),
    ])
    def test_d_range_priority_all_values(self, drp, expected_ptp):
        recipe = _make_recipe(d_range_priority=drp)
        assert recipe_to_ptp_values(recipe).DRangePriority == expected_ptp

    # ------------------------------------------------------------------
    # DRangeMode — conditional on DRangePriority being Off
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("dr_mode, expected_ptp", [
        ("DR100",   100),
        ("DR200",   200),
        ("DR400",   400),
        ("DR-Auto", 65535),
    ])
    def test_dr_mode_all_values_when_priority_off(self, dr_mode, expected_ptp):
        recipe = _make_recipe(d_range_priority="Off", dynamic_range=dr_mode)
        assert recipe_to_ptp_values(recipe).DRangeMode == expected_ptp

    @pytest.mark.parametrize("drp", ["Weak", "Strong", "Auto"])
    def test_dr_mode_none_when_priority_active(self, drp):
        recipe = _make_recipe(d_range_priority=drp, dynamic_range="DR400")
        assert recipe_to_ptp_values(recipe).DRangeMode is None

    def test_dr_mode_none_when_dynamic_range_absent(self):
        recipe = _make_recipe(d_range_priority="Off", dynamic_range=None)
        assert recipe_to_ptp_values(recipe).DRangeMode is None

    # ------------------------------------------------------------------
    # GrainEffect — Off always writes 1; Weak/Strong × Small/Large each distinct
    # ------------------------------------------------------------------

    def test_grain_off_encodes_as_1(self):
        recipe = _make_recipe(grain_roughness="Off", grain_size=None)
        assert recipe_to_ptp_values(recipe).GrainEffect == 1

    @pytest.mark.parametrize("roughness, size, expected_ptp", [
        ("Weak",   "Small", 2),
        ("Strong", "Small", 3),
        ("Weak",   "Large", 4),
        ("Strong", "Large", 5),
    ])
    def test_grain_roughness_size_all_combinations(self, roughness, size, expected_ptp):
        recipe = _make_recipe(grain_roughness=roughness, grain_size=size)
        assert recipe_to_ptp_values(recipe).GrainEffect == expected_ptp

    # ------------------------------------------------------------------
    # ColorEffect (CCE) and ColorFx (CFX) — Off/Weak/Strong
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("cce, expected_ptp", [
        ("Off",    1),
        ("Weak",   2),
        ("Strong", 3),
    ])
    def test_color_chrome_effect_all_values(self, cce, expected_ptp):
        recipe = _make_recipe(color_chrome_effect=cce)
        assert recipe_to_ptp_values(recipe).ColorEffect == expected_ptp

    @pytest.mark.parametrize("cfx, expected_ptp", [
        ("Off",    1),
        ("Weak",   2),
        ("Strong", 3),
    ])
    def test_color_chrome_fx_blue_all_values(self, cfx, expected_ptp):
        recipe = _make_recipe(color_chrome_fx_blue=cfx)
        assert recipe_to_ptp_values(recipe).ColorFx == expected_ptp

    # ------------------------------------------------------------------
    # Sharpness (always written; absent/N/A → 0)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("sharpness_str, expected_ptp", [
        ("-4", -40),
        ("-2", -20),
        ("0",    0),
        ("+2",  20),
        ("+4",  40),
    ])
    def test_sharpness_encoding(self, sharpness_str, expected_ptp):
        recipe = _make_recipe(sharpness=sharpness_str)
        assert recipe_to_ptp_values(recipe).Sharpness == expected_ptp

    @pytest.mark.parametrize("absent", ["", "N/A"])
    def test_sharpness_absent_defaults_to_zero(self, absent):
        recipe = _make_recipe(sharpness=absent)
        assert recipe_to_ptp_values(recipe).Sharpness == 0

    # ------------------------------------------------------------------
    # Definition / Clarity (always written; absent/N/A → 0)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("clarity_str, expected_ptp", [
        ("-5", -50),
        ("-2", -20),
        ("0",    0),
        ("+2",  20),
        ("+5",  50),
    ])
    def test_clarity_encoding(self, clarity_str, expected_ptp):
        recipe = _make_recipe(clarity=clarity_str)
        assert recipe_to_ptp_values(recipe).Definition == expected_ptp

    @pytest.mark.parametrize("absent", ["", "N/A"])
    def test_clarity_absent_defaults_to_zero(self, absent):
        recipe = _make_recipe(clarity=absent)
        assert recipe_to_ptp_values(recipe).Definition == 0

    # ------------------------------------------------------------------
    # HighLightTone (optional; None when absent)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("highlight_str, expected_ptp", [
        ("-2",   -20),
        ("-1.5", -15),
        ("0",      0),
        ("+1.5",  15),
        ("+2",    20),
    ])
    def test_highlight_encoding(self, highlight_str, expected_ptp):
        recipe = _make_recipe(highlight=highlight_str)
        assert recipe_to_ptp_values(recipe).HighLightTone == expected_ptp

    def test_highlight_none_is_absent(self):
        recipe = _make_recipe(highlight=None)
        assert recipe_to_ptp_values(recipe).HighLightTone is None

    # ------------------------------------------------------------------
    # ShadowTone (optional; None when absent)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("shadow_str, expected_ptp", [
        ("-2",  -20),
        ("-1",  -10),
        ("0",     0),
        ("+1",   10),
        ("+2",   20),
    ])
    def test_shadow_encoding(self, shadow_str, expected_ptp):
        recipe = _make_recipe(shadow=shadow_str)
        assert recipe_to_ptp_values(recipe).ShadowTone == expected_ptp

    def test_shadow_none_is_absent(self):
        recipe = _make_recipe(shadow=None)
        assert recipe_to_ptp_values(recipe).ShadowTone is None

    # ------------------------------------------------------------------
    # ColorMode (optional; None when absent)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("color_str, expected_ptp", [
        ("-4", -40),
        ("-2", -20),
        ("0",    0),
        ("+2",  20),
        ("+4",  40),
    ])
    def test_color_encoding(self, color_str, expected_ptp):
        recipe = _make_recipe(color=color_str)
        assert recipe_to_ptp_values(recipe).ColorMode == expected_ptp

    def test_color_none_is_absent(self):
        recipe = _make_recipe(color=None)
        assert recipe_to_ptp_values(recipe).ColorMode is None

    # ------------------------------------------------------------------
    # HighIsoNoiseReduction — non-linear lookup, all 9 domain values
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("nr_str, expected_ptp", [
        ("+4",  20480),   # 0x5000
        ("+3",  24576),   # 0x6000
        ("+2",      0),   # 0x0000
        ("+1",   4096),   # 0x1000
        ("0",    8192),   # 0x2000 — normal
        ("-1",  12288),   # 0x3000
        ("-2",  16384),   # 0x4000
        ("-3",  28672),   # 0x7000
        ("-4",  32768),   # 0x8000
    ])
    def test_high_iso_nr_all_values(self, nr_str, expected_ptp):
        recipe = _make_recipe(high_iso_nr=nr_str)
        assert recipe_to_ptp_values(recipe).HighIsoNoiseReduction == expected_ptp

    @pytest.mark.parametrize("absent", ["", "N/A"])
    def test_high_iso_nr_absent_defaults_to_normal(self, absent):
        """Absent NR maps to domain 0 → PTP 8192 (0x2000, normal)."""
        recipe = _make_recipe(high_iso_nr=absent)
        assert recipe_to_ptp_values(recipe).HighIsoNoiseReduction == 8192

    # ------------------------------------------------------------------
    # MonochromaticColorWarmCool / MagentaGreen (optional; None when absent)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("wc_str, expected_ptp", [
        ("-18", -180),
        ("-9",   -90),
        ("0",      0),
        ("+9",    90),
        ("+18",  180),
    ])
    def test_mono_warm_cool_encoding(self, wc_str, expected_ptp):
        recipe = _make_recipe(
            film_simulation="Acros STD",
            color=None,
            monochromatic_color_warm_cool=wc_str,
            monochromatic_color_magenta_green="0",
        )
        assert recipe_to_ptp_values(recipe).MonochromaticColorWarmCool == expected_ptp

    def test_mono_warm_cool_none_when_absent(self):
        recipe = _make_recipe(monochromatic_color_warm_cool=None)
        assert recipe_to_ptp_values(recipe).MonochromaticColorWarmCool is None

    @pytest.mark.parametrize("mg_str, expected_ptp", [
        ("-18", -180),
        ("-9",   -90),
        ("0",      0),
        ("+9",    90),
        ("+18",  180),
    ])
    def test_mono_magenta_green_encoding(self, mg_str, expected_ptp):
        recipe = _make_recipe(
            film_simulation="Acros STD",
            color=None,
            monochromatic_color_warm_cool="0",
            monochromatic_color_magenta_green=mg_str,
        )
        assert recipe_to_ptp_values(recipe).MonochromaticColorMagentaGreen == expected_ptp

    def test_mono_magenta_green_none_when_absent(self):
        recipe = _make_recipe(monochromatic_color_magenta_green=None)
        assert recipe_to_ptp_values(recipe).MonochromaticColorMagentaGreen is None


# ---------------------------------------------------------------------------
# Normalization coverage for slot_recipe()
# ---------------------------------------------------------------------------


class TestSlotRecipeNormalization:
    """slot_recipe() applies normalize_recipe_data() — inapplicable fields are None."""

    def test_nulls_color_for_mono_sim(self) -> None:
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]: 12},  # Acros STD
        )
        result = slot_recipe(device, slot_index=1)
        assert result.color is None

    def test_preserves_mono_fields_for_mono_sim(self) -> None:
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]: 12},  # Acros STD
        )
        result = slot_recipe(device, slot_index=1)
        assert result.monochromatic_color_warm_cool == "0"
        assert result.monochromatic_color_magenta_green == "0"

    def test_nulls_mono_fields_for_colour_sim(self) -> None:
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["FilmSimulation"]: 1},  # Provia
        )
        result = slot_recipe(device, slot_index=1)
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_nulls_drp_fields_when_drp_is_active(self) -> None:
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["DRangePriority"]: 1},  # Weak
        )
        result = slot_recipe(device, slot_index=1)
        assert result.dynamic_range is None
        assert result.highlight is None
        assert result.shadow is None

    def test_nulls_grain_size_when_roughness_is_off(self) -> None:
        # Camera stores 6 or 7 for Off; 1 is write-only.
        device = FakePTPDevice(
            int_values={cam_constants.CUSTOM_SLOT_CODES["GrainEffect"]: 6},
        )
        result = slot_recipe(device, slot_index=1)
        assert result.grain_size is None
