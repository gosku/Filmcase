import pytest
from django.core.management import call_command

from src.data import models
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestFixEmptyGrainRecipesCommand:
    def test_updates_unique_buggy_row_in_place(self):
        """A buggy row with no matching correct row is updated in place."""
        buggy = FujifilmRecipeFactory(grain_roughness="Off", grain_size="")

        call_command("fix_empty_grain_recipes")

        buggy.refresh_from_db()
        assert buggy.grain_size == "Off"
        assert models.FujifilmRecipe.objects.count() == 1

    def test_reassigns_images_and_deletes_buggy_row_when_correct_row_exists(self):
        """When a correct 'Off' row already exists, images are reassigned and the buggy row deleted."""
        correct = FujifilmRecipeFactory(grain_roughness="Off", grain_size="Off", white_balance_red=1)
        buggy = FujifilmRecipeFactory(
            grain_roughness="Off",
            grain_size="",
            white_balance_red=correct.white_balance_red,
            white_balance_blue=correct.white_balance_blue,
            film_simulation=correct.film_simulation,
            dynamic_range=correct.dynamic_range,
            d_range_priority=correct.d_range_priority,
            color_chrome_effect=correct.color_chrome_effect,
            color_chrome_fx_blue=correct.color_chrome_fx_blue,
            white_balance=correct.white_balance,
        )
        image = ImageFactory(fujifilm_recipe=buggy)
        buggy_id = buggy.id

        call_command("fix_empty_grain_recipes")

        image.refresh_from_db()
        assert image.fujifilm_recipe_id == correct.id
        assert not models.FujifilmRecipe.objects.filter(pk=buggy_id).exists()
        assert models.FujifilmRecipe.objects.count() == 1

    def test_does_not_touch_rows_with_correct_grain_size(self):
        """Rows already storing 'Off' are left untouched."""
        recipe = FujifilmRecipeFactory(grain_roughness="Off", grain_size="Off")

        call_command("fix_empty_grain_recipes")

        recipe.refresh_from_db()
        assert recipe.grain_size == "Off"

    def test_does_not_touch_non_off_roughness_rows(self):
        """Rows with non-Off roughness are not affected even if grain_size is empty."""
        recipe = FujifilmRecipeFactory(grain_roughness="Weak", grain_size="")

        call_command("fix_empty_grain_recipes")

        recipe.refresh_from_db()
        assert recipe.grain_size == ""

    def test_transfers_name_from_buggy_row_to_correct_row_on_merge(self):
        """A name on the buggy row is transferred to the unnamed correct row during a merge."""
        correct = FujifilmRecipeFactory(grain_roughness="Off", grain_size="Off", white_balance_red=2, name="")
        buggy = FujifilmRecipeFactory(
            grain_roughness="Off",
            grain_size="",
            name="My Recipe",
            white_balance_red=correct.white_balance_red,
            white_balance_blue=correct.white_balance_blue,
            film_simulation=correct.film_simulation,
            dynamic_range=correct.dynamic_range,
            d_range_priority=correct.d_range_priority,
            color_chrome_effect=correct.color_chrome_effect,
            color_chrome_fx_blue=correct.color_chrome_fx_blue,
            white_balance=correct.white_balance,
        )

        call_command("fix_empty_grain_recipes")

        correct.refresh_from_db()
        assert correct.name == "My Recipe"
        assert not models.FujifilmRecipe.objects.filter(pk=buggy.pk).exists()

    def test_outputs_summary(self, capsys):
        """The command prints a summary of what was fixed."""
        FujifilmRecipeFactory(grain_roughness="Off", grain_size="")

        call_command("fix_empty_grain_recipes")

        captured = capsys.readouterr()
        assert "1 updated in place" in captured.out
        assert "0 merged" in captured.out

    def test_outputs_nothing_to_do_when_no_buggy_rows(self, capsys):
        """The command reports nothing to do when no buggy rows exist."""
        call_command("fix_empty_grain_recipes")

        captured = capsys.readouterr()
        assert "Nothing to do" in captured.out
