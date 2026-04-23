from pathlib import Path

import pytest

from src.application.usecases.recipes import create_recipe_card as uc
from src.data import models
from src.domain.recipes.cards import templates as card_templates
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestCreateRecipeCard:
    def test_returns_recipe_card_record(self, tmp_path: Path, settings: object) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)  # type: ignore[attr-defined]
        recipe = FujifilmRecipeFactory()

        card = uc.create_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )

        assert isinstance(card, models.RecipeCard)
        assert card.pk is not None

    def test_raises_if_recipe_does_not_exist(self, tmp_path: Path, settings: object) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)  # type: ignore[attr-defined]

        with pytest.raises(models.FujifilmRecipe.DoesNotExist):
            uc.create_recipe_card(
                recipe_id=999999,
                image_id=None,
                template=card_templates.LONG_LABEL,
            )

    def test_raises_if_image_does_not_exist(self, tmp_path: Path, settings: object) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)  # type: ignore[attr-defined]
        recipe = FujifilmRecipeFactory()

        with pytest.raises(models.Image.DoesNotExist):
            uc.create_recipe_card(
                recipe_id=recipe.pk,
                image_id=999999,
                template=card_templates.LONG_LABEL,
            )

    def test_card_file_is_saved_to_recipe_cards_dir(self, tmp_path: Path, settings: object) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)  # type: ignore[attr-defined]
        recipe = FujifilmRecipeFactory()

        card = uc.create_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )

        assert Path(card.filepath).parent == tmp_path
        assert Path(card.filepath).exists()

    def test_creates_output_dir_if_missing(self, tmp_path: Path, settings: object) -> None:
        output_dir = tmp_path / "nested" / "cards"
        settings.RECIPE_CARDS_DIR = str(output_dir)  # type: ignore[attr-defined]
        recipe = FujifilmRecipeFactory()

        uc.create_recipe_card(
            recipe_id=recipe.pk,
            image_id=None,
            template=card_templates.LONG_LABEL,
        )

        assert output_dir.exists()
