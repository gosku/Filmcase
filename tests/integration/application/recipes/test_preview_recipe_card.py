from pathlib import Path

import pytest

from src.application.usecases.recipes import preview_recipe_card as uc
from src.data import models
from src.domain.recipes.cards.designs import classic as classic_design
from tests.factories import FujifilmRecipeFactory

_CLASSIC = classic_design.ClassicDesign()
_CLASSIC_SHORT = classic_design.ClassicDesign(label_style="short")


@pytest.mark.django_db
class TestPreviewRecipeCard:
    def test_returns_path_to_generated_file(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()

        result = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=_CLASSIC,
        )

        assert isinstance(result, Path)
        assert result.exists()

    def test_raises_if_recipe_does_not_exist(self) -> None:
        with pytest.raises(models.FujifilmRecipe.DoesNotExist):
            uc.preview_recipe_card(
                recipe_id=999999,
                image_id=None,
                design=_CLASSIC,
            )

    def test_raises_if_image_does_not_exist(self) -> None:
        recipe = FujifilmRecipeFactory()

        with pytest.raises(models.Image.DoesNotExist):
            uc.preview_recipe_card(
                recipe_id=recipe.pk,
                image_id=999999,
                design=_CLASSIC,
            )

    def test_output_path_is_deterministic(self) -> None:
        recipe = FujifilmRecipeFactory()

        path1 = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=_CLASSIC,
        )
        path2 = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=_CLASSIC,
        )

        assert path1 == path2

    def test_info_side_reuses_the_same_deterministic_path(self) -> None:
        # info_side is a ClassicDesign option but is not part of the persisted
        # template name, so both sides share one preview file. The file is
        # regenerated on every request, so this overwrite is intentional and
        # keeps previews from accumulating.
        recipe = FujifilmRecipeFactory()

        path_left = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=classic_design.ClassicDesign(info_side="left"),
        )
        path_right = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=classic_design.ClassicDesign(info_side="right"),
        )

        assert path_left == path_right
        assert path_left.exists()

    def test_different_templates_produce_different_paths(self) -> None:
        recipe = FujifilmRecipeFactory()

        path_long = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=_CLASSIC,
        )
        path_short = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            design=_CLASSIC_SHORT,
        )

        assert path_long != path_short
