from pathlib import Path

import pytest

from src.application.usecases.recipes import preview_recipe_card as uc
from src.data import models
from src.domain.recipes.cards import templates as card_templates
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestPreviewRecipeCard:
    def test_returns_path_to_generated_file(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()

        result = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )

        assert isinstance(result, Path)
        assert result.exists()

    def test_raises_if_recipe_does_not_exist(self) -> None:
        with pytest.raises(models.FujifilmRecipe.DoesNotExist):
            uc.preview_recipe_card(
                recipe_id=999999,
                image_id=None,
                template=card_templates.LONG_LABEL,
            )

    def test_raises_if_image_does_not_exist(self) -> None:
        recipe = FujifilmRecipeFactory()

        with pytest.raises(models.Image.DoesNotExist):
            uc.preview_recipe_card(
                recipe_id=recipe.pk,
                image_id=999999,
                template=card_templates.LONG_LABEL,
            )

    def test_output_path_is_deterministic(self) -> None:
        recipe = FujifilmRecipeFactory()

        path1 = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )
        path2 = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )

        assert path1 == path2

    def test_different_templates_produce_different_paths(self) -> None:
        recipe = FujifilmRecipeFactory()

        path_long = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )
        path_short = uc.preview_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.SHORT_LABEL,
        )

        assert path_long != path_short
