import attrs
import pytest
from decimal import Decimal

from src.data.camera.constants import DRANGE_MODE_TO_PTP, FILM_SIMULATION_TO_PTP, PTP_TO_FILM_SIMULATION
from src.domain.camera.queries import RecipePTPValues, recipe_to_ptp_values
from src.domain.images.dataclasses import FujifilmRecipeData
from src.domain.images.queries import recipe_from_db
from tests.factories import FujifilmRecipeFactory


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
# Factory-pipeline tests: FujifilmRecipeFactory.build() → recipe_from_db()
#                         → recipe_to_ptp_values()
# ---------------------------------------------------------------------------

def _build_ptp(**overrides) -> RecipePTPValues:
    """
    Build a FujifilmRecipe in-memory via the factory (no DB), convert it to the
    domain dataclass via recipe_from_db(), then encode it as PTP values.

    Mandatory Decimal fields (sharpness, high_iso_nr, clarity) default to 0 so
    callers only need to supply the fields under test.
    """
    defaults = dict(
        name="Test Recipe",
        sharpness=Decimal("0"),
        high_iso_nr=Decimal("0"),
        clarity=Decimal("0"),
    )
    defaults.update(overrides)
    db_recipe = FujifilmRecipeFactory.build(**defaults)
    domain = recipe_from_db(recipe=db_recipe)
    return recipe_to_ptp_values(domain)


class TestRecipeToPTPValuesViaFactory:
    """
    End-to-end unit tests for the full pipeline:
    FujifilmRecipeFactory.build() → recipe_from_db() → recipe_to_ptp_values().

    These tests exercise the composition of DB-to-domain conversion and
    domain-to-PTP encoding, using a variety of field combinations.
    """

    # ------------------------------------------------------------------
    # White balance
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("wb_label, expected_ptp", [
        ("Auto",                     0x0002),
        ("Auto (white priority)",    0x8020),
        ("Auto (ambience priority)", 0x8021),
        ("Daylight",                 0x0004),
        ("Incandescent",             0x0006),
        ("Shade",                    0x8006),
        ("Fluorescent 1",            0x8001),
        ("Fluorescent 3",            0x8003),
        ("Underwater",               0x0008),
        ("Custom 1",                 0x8008),
        ("Custom 3",                 0x800A),
    ])
    def test_white_balance_modes(self, wb_label, expected_ptp):
        ptp = _build_ptp(white_balance=wb_label)
        assert ptp.WhiteBalance == expected_ptp
        assert ptp.WhiteBalanceColorTemperature is None

    def test_kelvin_white_balance_sets_wb_code_and_temperature(self):
        ptp = _build_ptp(white_balance="6500K")
        assert ptp.WhiteBalance == 0x8007          # Kelvin PTP code
        assert ptp.WhiteBalanceColorTemperature == 6500

    def test_kelvin_white_balance_temperature_4000(self):
        ptp = _build_ptp(white_balance="4000K")
        assert ptp.WhiteBalance == 0x8007
        assert ptp.WhiteBalanceColorTemperature == 4000

    def test_white_balance_red_blue_pass_through(self):
        ptp = _build_ptp(white_balance_red=3, white_balance_blue=-5)
        assert ptp.WhiteBalanceRed == 3
        assert ptp.WhiteBalanceBlue == -5

    # ------------------------------------------------------------------
    # Grain effect
    # ------------------------------------------------------------------

    def test_grain_off_encodes_as_1(self):
        ptp = _build_ptp(grain_roughness="Off", grain_size="Off")
        assert ptp.GrainEffect == 1

    @pytest.mark.parametrize("roughness, size, expected_ptp", [
        ("Weak",   "Small", 2),
        ("Strong", "Small", 3),
        ("Weak",   "Large", 4),
        ("Strong", "Large", 5),
    ])
    def test_grain_roughness_size_combinations(self, roughness, size, expected_ptp):
        ptp = _build_ptp(grain_roughness=roughness, grain_size=size)
        assert ptp.GrainEffect == expected_ptp

    # ------------------------------------------------------------------
    # Color chrome effect and FX blue
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("cce, expected_ptp", [
        ("Off",    1),
        ("Weak",   2),
        ("Strong", 3),
    ])
    def test_color_chrome_effect(self, cce, expected_ptp):
        ptp = _build_ptp(color_chrome_effect=cce)
        assert ptp.ColorEffect == expected_ptp

    @pytest.mark.parametrize("cfx, expected_ptp", [
        ("Off",    1),
        ("Weak",   2),
        ("Strong", 3),
    ])
    def test_color_chrome_fx_blue(self, cfx, expected_ptp):
        ptp = _build_ptp(color_chrome_fx_blue=cfx)
        assert ptp.ColorFx == expected_ptp

    # ------------------------------------------------------------------
    # D-Range Priority vs D-Range Mode interaction
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("drp, expected_drp_ptp", [
        ("Off",    0),
        ("Weak",   1),
        ("Strong", 2),
        ("Auto",   32768),
    ])
    def test_d_range_priority_encoding(self, drp, expected_drp_ptp):
        ptp = _build_ptp(d_range_priority=drp, dynamic_range="DR100")
        assert ptp.DRangePriority == expected_drp_ptp

    def test_d_range_priority_active_suppresses_dr_mode(self):
        """When DRP is not Off, DRangeMode must be None (not written to camera)."""
        for drp in ("Weak", "Strong", "Auto"):
            ptp = _build_ptp(d_range_priority=drp, dynamic_range="DR400")
            assert ptp.DRangeMode is None, f"DRangeMode should be None when DRP={drp!r}"

    @pytest.mark.parametrize("dr_setting, expected_ptp", [
        ("DR100",   100),
        ("DR200",   200),
        ("DR400",   400),
        ("DR-Auto", 65535),
    ])
    def test_dr_mode_set_when_priority_is_off(self, dr_setting, expected_ptp):
        ptp = _build_ptp(d_range_priority="Off", dynamic_range=dr_setting)
        assert ptp.DRangeMode == expected_ptp
        assert ptp.DRangePriority == 0

    # ------------------------------------------------------------------
    # Scaled int16 fields (value × 10)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("sharpness, expected_ptp", [
        (Decimal("0"),  0),
        (Decimal("2"),  20),
        (Decimal("-2"), -20),
        (Decimal("4"),  40),
    ])
    def test_sharpness_scaling(self, sharpness, expected_ptp):
        ptp = _build_ptp(sharpness=sharpness)
        assert ptp.Sharpness == expected_ptp

    @pytest.mark.parametrize("clarity, expected_ptp", [
        (Decimal("0"),  0),
        (Decimal("5"),  50),
        (Decimal("-5"), -50),
    ])
    def test_clarity_scaling(self, clarity, expected_ptp):
        ptp = _build_ptp(clarity=clarity)
        assert ptp.Definition == expected_ptp

    @pytest.mark.parametrize("highlight, expected_ptp", [
        (Decimal("0"),   0),
        (Decimal("2"),   20),
        (Decimal("-2"),  -20),
        (Decimal("1.5"), 15),   # half-step
    ])
    def test_highlight_scaling(self, highlight, expected_ptp):
        ptp = _build_ptp(highlight=highlight)
        assert ptp.HighLightTone == expected_ptp

    @pytest.mark.parametrize("shadow, expected_ptp", [
        (Decimal("0"),    0),
        (Decimal("-1"),   -10),
        (Decimal("1.5"),  15),  # half-step
    ])
    def test_shadow_scaling(self, shadow, expected_ptp):
        ptp = _build_ptp(shadow=shadow)
        assert ptp.ShadowTone == expected_ptp

    def test_color_scaling(self):
        ptp = _build_ptp(color=Decimal("4"))
        assert ptp.ColorMode == 40

    def test_color_none_is_absent(self):
        ptp = _build_ptp(color=None)
        assert ptp.ColorMode is None

    def test_highlight_none_is_absent(self):
        ptp = _build_ptp(highlight=None)
        assert ptp.HighLightTone is None

    def test_shadow_none_is_absent(self):
        ptp = _build_ptp(shadow=None)
        assert ptp.ShadowTone is None

    # ------------------------------------------------------------------
    # High ISO noise reduction (non-linear lookup)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("nr_value, expected_ptp", [
        (Decimal("4"),  20480),   # 0x5000
        (Decimal("3"),  24576),   # 0x6000
        (Decimal("2"),  0),       # 0x0000
        (Decimal("1"),  4096),    # 0x1000
        (Decimal("0"),  8192),    # 0x2000
        (Decimal("-1"), 12288),   # 0x3000
        (Decimal("-2"), 16384),   # 0x4000
        (Decimal("-3"), 28672),   # 0x7000
        (Decimal("-4"), 32768),   # 0x8000
    ])
    def test_high_iso_nr_non_linear_encoding(self, nr_value, expected_ptp):
        ptp = _build_ptp(high_iso_nr=nr_value)
        assert ptp.HighIsoNoiseReduction == expected_ptp

    # ------------------------------------------------------------------
    # Film simulation (spot-check via factory)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("film_sim, expected_ptp", [
        ("Provia",           1),
        ("Velvia",           2),
        ("Classic Chrome",   11),
        ("Acros STD",        12),
        ("Eterna",           16),
        ("Classic Negative", 17),
        ("Reala Ace",        20),
    ])
    def test_film_simulation_via_factory(self, film_sim, expected_ptp):
        ptp = _build_ptp(film_simulation=film_sim)
        assert ptp.FilmSimulation == expected_ptp

    # ------------------------------------------------------------------
    # Monochromatic colour tuning (mono vs non-mono film sims)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("film_sim", [
        "Monochrome STD", "Monochrome Yellow", "Monochrome Red", "Monochrome Green",
        "Acros STD", "Acros Yellow", "Acros Red", "Acros Green", "Sepia",
    ])
    def test_mono_color_fields_encoded_for_mono_sims(self, film_sim):
        ptp = _build_ptp(
            film_simulation=film_sim,
            color=None,
            monochromatic_color_warm_cool=Decimal("9"),
            monochromatic_color_magenta_green=Decimal("-9"),
        )
        assert ptp.MonochromaticColorWarmCool == 90
        assert ptp.MonochromaticColorMagentaGreen == -90

    @pytest.mark.parametrize("film_sim", [
        "Provia", "Velvia", "Astia", "Classic Chrome",
        "Eterna", "Classic Negative", "Reala Ace",
    ])
    def test_mono_color_fields_none_for_colour_sims(self, film_sim):
        ptp = _build_ptp(
            film_simulation=film_sim,
            monochromatic_color_warm_cool=None,
            monochromatic_color_magenta_green=None,
        )
        assert ptp.MonochromaticColorWarmCool is None
        assert ptp.MonochromaticColorMagentaGreen is None

    # ------------------------------------------------------------------
    # Composite: multiple fields together
    # ------------------------------------------------------------------

    def test_full_colour_recipe(self):
        """A fully-specified colour recipe encodes every PTP field correctly."""
        ptp = _build_ptp(
            film_simulation="Classic Chrome",
            white_balance="Daylight",
            white_balance_red=2,
            white_balance_blue=-3,
            dynamic_range="DR200",
            d_range_priority="Off",
            grain_roughness="Weak",
            grain_size="Large",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Weak",
            sharpness=Decimal("-2"),
            clarity=Decimal("2"),
            high_iso_nr=Decimal("-1"),
            highlight=Decimal("1.5"),
            shadow=Decimal("-1"),
            color=Decimal("2"),
            monochromatic_color_warm_cool=None,
            monochromatic_color_magenta_green=None,
        )
        assert ptp.FilmSimulation == 11            # Classic Chrome
        assert ptp.WhiteBalance == 0x0004          # Daylight
        assert ptp.WhiteBalanceColorTemperature is None
        assert ptp.WhiteBalanceRed == 2
        assert ptp.WhiteBalanceBlue == -3
        assert ptp.DRangeMode == 200
        assert ptp.DRangePriority == 0             # Off
        assert ptp.GrainEffect == 4                # Weak/Large
        assert ptp.ColorEffect == 3                # Strong
        assert ptp.ColorFx == 2                    # Weak
        assert ptp.Sharpness == -20
        assert ptp.Definition == 20
        assert ptp.HighIsoNoiseReduction == 12288  # -1 → 0x3000
        assert ptp.HighLightTone == 15             # +1.5 × 10
        assert ptp.ShadowTone == -10
        assert ptp.ColorMode == 20
        assert ptp.MonochromaticColorWarmCool is None
        assert ptp.MonochromaticColorMagentaGreen is None

    def test_full_mono_recipe_with_kelvin_wb_and_drp(self):
        """A monochromatic recipe with Kelvin WB and active D-Range Priority."""
        ptp = _build_ptp(
            film_simulation="Acros Red",
            white_balance="10000K",
            white_balance_red=0,
            white_balance_blue=0,
            dynamic_range="DR400",
            d_range_priority="Strong",
            grain_roughness="Strong",
            grain_size="Small",
            color_chrome_effect="Off",
            color_chrome_fx_blue="Off",
            sharpness=Decimal("4"),
            clarity=Decimal("-5"),
            high_iso_nr=Decimal("4"),
            highlight=None,
            shadow=None,
            color=None,
            monochromatic_color_warm_cool=Decimal("-18"),
            monochromatic_color_magenta_green=Decimal("0"),
        )
        assert ptp.FilmSimulation == 14             # Acros Red
        assert ptp.WhiteBalance == 0x8007           # Kelvin
        assert ptp.WhiteBalanceColorTemperature == 10000
        assert ptp.DRangePriority == 2              # Strong
        assert ptp.DRangeMode is None               # suppressed by DRP
        assert ptp.GrainEffect == 3                 # Strong/Small
        assert ptp.ColorEffect == 1                 # Off
        assert ptp.ColorFx == 1                     # Off
        assert ptp.Sharpness == 40
        assert ptp.Definition == -50
        assert ptp.HighIsoNoiseReduction == 20480   # 4 → 0x5000
        assert ptp.HighLightTone is None
        assert ptp.ShadowTone is None
        assert ptp.ColorMode is None
        assert ptp.MonochromaticColorWarmCool == -180
        assert ptp.MonochromaticColorMagentaGreen == 0


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
