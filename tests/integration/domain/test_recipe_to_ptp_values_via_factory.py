"""End-to-end integration tests for the pipeline
FujifilmRecipeFactory() → recipe_from_db() → recipe_to_ptp_values().

Lives under tests/integration/ because recipe_from_db() reads the
``sensors`` M2M relation, which Django refuses to evaluate on unsaved
instances. The tests exercise the composition of DB-to-domain conversion
and domain-to-PTP encoding across a variety of field combinations.
"""

from decimal import Decimal

import pytest

from src.domain.camera.queries import RecipePTPValues, recipe_to_ptp_values
from src.domain.recipes.queries import recipe_from_db
from tests.factories import FujifilmRecipeFactory


def _build_ptp(**overrides) -> RecipePTPValues:
    """
    Create a FujifilmRecipe via the factory (DB-backed), convert it to the
    domain dataclass via recipe_from_db(), then encode it as PTP values.

    Mandatory Decimal fields default to 0 so callers only need to supply the
    fields under test.
    """
    defaults = dict(
        name="Test Recipe",
        sharpness=Decimal("0"),
        high_iso_nr=Decimal("0"),
        clarity=Decimal("0"),
    )
    defaults.update(overrides)
    db_recipe = FujifilmRecipeFactory(**defaults)
    domain = recipe_from_db(recipe=db_recipe)
    return recipe_to_ptp_values(domain)


@pytest.mark.django_db
class TestRecipeToPTPValuesViaFactory:
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
