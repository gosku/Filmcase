from decimal import Decimal

import pytest
from django.core.management import call_command

from src.data import models
from tests.factories import FujifilmRecipeFactory, ImageFactory

# Shared overrides that make a factory recipe pass validate_recipe_data()
# for a colour sim with DRP off and grain off.
_VALID_COLOR_DEFAULTS: dict[str, object] = dict(
    film_simulation="Provia",
    d_range_priority="Off",
    dynamic_range="DR100",
    grain_roughness="Off",
    grain_size="Off",
    highlight=Decimal("0"),
    shadow=Decimal("0"),
    color=Decimal("0"),
    monochromatic_color_warm_cool=None,
    monochromatic_color_magenta_green=None,
)


@pytest.mark.django_db
class TestNormalizeRecipeRowsCommand:
    def test_no_op_when_all_rows_clean(self, capsys) -> None:
        """Rows already in a normalized shape produce no changes."""
        FujifilmRecipeFactory(**_VALID_COLOR_DEFAULTS)

        call_command("normalize_recipe_rows")

        captured = capsys.readouterr()
        assert "Nothing to do" in captured.out

    def test_nulls_mono_fields_for_colour_sim(self) -> None:
        """A colour sim recipe with monochromatic fields set has them nulled."""
        recipe = FujifilmRecipeFactory(
            **{**_VALID_COLOR_DEFAULTS,
               "monochromatic_color_warm_cool": Decimal("1"),
               "monochromatic_color_magenta_green": Decimal("-1")},
        )

        call_command("normalize_recipe_rows")

        recipe.refresh_from_db()
        assert recipe.monochromatic_color_warm_cool is None
        assert recipe.monochromatic_color_magenta_green is None
        assert recipe.color == Decimal("0")

    def test_nulls_color_for_mono_sim(self) -> None:
        """A mono sim recipe with color set has it nulled."""
        recipe = FujifilmRecipeFactory(
            film_simulation="Acros STD",
            d_range_priority="Off",
            dynamic_range="DR100",
            grain_roughness="Off",
            grain_size="Off",
            highlight=Decimal("0"),
            shadow=Decimal("0"),
            color=Decimal("0"),
            monochromatic_color_warm_cool=Decimal("0"),
            monochromatic_color_magenta_green=Decimal("0"),
        )

        call_command("normalize_recipe_rows")

        recipe.refresh_from_db()
        assert recipe.color is None
        assert recipe.monochromatic_color_warm_cool == Decimal("0")
        assert recipe.monochromatic_color_magenta_green == Decimal("0")

    def test_nulls_hl_sh_and_empties_dr_when_drp_active(self) -> None:
        """A DRP-active recipe with highlight/shadow/dynamic_range set has them cleared."""
        recipe = FujifilmRecipeFactory(
            film_simulation="Provia",
            d_range_priority="Auto",
            dynamic_range="DR100",
            grain_roughness="Off",
            grain_size="Off",
            highlight=Decimal("1"),
            shadow=Decimal("-1"),
            color=Decimal("0"),
            monochromatic_color_warm_cool=None,
            monochromatic_color_magenta_green=None,
        )

        call_command("normalize_recipe_rows")

        recipe.refresh_from_db()
        assert recipe.highlight is None
        assert recipe.shadow is None
        assert recipe.dynamic_range == ""

    def test_merges_when_normalized_row_already_exists(self) -> None:
        """A dirty row whose normalized shape already exists is merged into the clean row."""
        clean = FujifilmRecipeFactory(
            **{**_VALID_COLOR_DEFAULTS, "white_balance_red": 77},
        )
        dirty = FujifilmRecipeFactory(
            film_simulation=clean.film_simulation,
            dynamic_range=clean.dynamic_range,
            d_range_priority=clean.d_range_priority,
            grain_roughness=clean.grain_roughness,
            grain_size=clean.grain_size,
            color_chrome_effect=clean.color_chrome_effect,
            color_chrome_fx_blue=clean.color_chrome_fx_blue,
            white_balance=clean.white_balance,
            white_balance_red=clean.white_balance_red,
            white_balance_blue=clean.white_balance_blue,
            color=clean.color,
            sharpness=clean.sharpness,
            high_iso_nr=clean.high_iso_nr,
            clarity=clean.clarity,
            highlight=clean.highlight,
            shadow=clean.shadow,
            monochromatic_color_warm_cool=Decimal("1"),  # inapplicable — will be nulled
            monochromatic_color_magenta_green=None,
        )
        image = ImageFactory(fujifilm_recipe=dirty)
        dirty_id = dirty.pk

        call_command("normalize_recipe_rows")

        image.refresh_from_db()
        assert image.fujifilm_recipe_id == clean.pk
        assert not models.FujifilmRecipe.objects.filter(pk=dirty_id).exists()
        assert models.FujifilmRecipe.objects.count() == 1

    def test_skips_unfixable_row(self) -> None:
        """A row where normalization cannot produce a valid shape is left unchanged."""
        recipe = FujifilmRecipeFactory(
            **{**_VALID_COLOR_DEFAULTS,
               "color": None,                             # required field missing — unfixable
               "monochromatic_color_warm_cool": Decimal("1")},  # inapplicable — triggers normalize
        )
        original_mono_wc = recipe.monochromatic_color_warm_cool

        call_command("normalize_recipe_rows")

        recipe.refresh_from_db()
        assert recipe.monochromatic_color_warm_cool == original_mono_wc

    def test_output_summary_with_updated_and_skipped(self, capsys) -> None:
        """The command prints a summary line with correct counts."""
        FujifilmRecipeFactory(
            **{**_VALID_COLOR_DEFAULTS,
               "monochromatic_color_warm_cool": Decimal("1")},  # fixable
        )
        FujifilmRecipeFactory(
            **{**_VALID_COLOR_DEFAULTS,
               "color": None,                              # unfixable
               "monochromatic_color_warm_cool": Decimal("1")},
        )

        call_command("normalize_recipe_rows")

        captured = capsys.readouterr()
        assert "1 updated" in captured.out
        assert "1 skipped" in captured.out
