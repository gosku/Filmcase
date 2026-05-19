import tempfile
import zipfile
from pathlib import Path

import pytest

from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestCreateRecipeCardsZip:
    def _make_card(self, tmp_path: Path) -> object:
        recipe = FujifilmRecipeFactory()
        return card_operations.create_recipe_card(
            recipe=recipe,
            template=card_templates.LONG_LABEL,
            background_image=None,
            output_dir=tmp_path,
        )

    def test_returns_existing_zip_file(self, tmp_path: Path) -> None:
        cards = [self._make_card(tmp_path), self._make_card(tmp_path)]

        zip_path = card_operations.create_recipe_cards_zip(cards=cards)

        assert zip_path.exists()
        assert zipfile.is_zipfile(zip_path)

    def test_zip_contains_one_entry_per_card(self, tmp_path: Path) -> None:
        cards = [self._make_card(tmp_path) for _ in range(3)]

        zip_path = card_operations.create_recipe_cards_zip(cards=cards)

        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
        assert len(names) == 3
        assert {Path(c.filepath).name for c in cards} == set(names)

    def test_zip_persists_in_temp_dir(self, tmp_path: Path) -> None:
        cards = [self._make_card(tmp_path)]

        zip_path = card_operations.create_recipe_cards_zip(cards=cards)

        assert zip_path.parent == Path(tempfile.gettempdir())
        assert zip_path.name.startswith("recipe_cards_")
        assert zip_path.suffix == ".zip"
