import zipfile
from pathlib import Path

import pytest

from src.application.usecases.recipes import create_recipe_cards_batch as uc
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestCreateRecipeCardsBatchPersistence:
    def test_creates_a_card_file_for_each_recipe(
        self, tmp_path: Path, settings: object
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()

        result = uc.create_recipe_cards_batch(recipe_ids=[recipe_a.pk, recipe_b.pk])

        assert result.created_count == 2
        assert result.failures == ()

    def test_returns_a_valid_zip_with_one_entry_per_created_card(
        self, tmp_path: Path, settings: object
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipes = [FujifilmRecipeFactory() for _ in range(3)]

        result = uc.create_recipe_cards_batch(recipe_ids=[r.pk for r in recipes])

        assert result.zip_path is not None
        assert result.zip_path.exists()
        assert zipfile.is_zipfile(result.zip_path)
        with zipfile.ZipFile(result.zip_path) as archive:
            assert len(archive.namelist()) == result.created_count == 3


@pytest.mark.django_db
class TestCreateRecipeCardsBatchResult:
    def test_missing_recipe_id_produces_not_found_failure(
        self, tmp_path: Path, settings: object
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()

        result = uc.create_recipe_cards_batch(recipe_ids=[recipe.pk, 999999])

        assert result.created_count == 1
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 999999
        assert result.failures[0].is_not_found

    def test_no_zip_when_every_recipe_fails(
        self, tmp_path: Path, settings: object
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)

        result = uc.create_recipe_cards_batch(recipe_ids=[999998, 999999])

        assert result.created_count == 0
        assert result.zip_path is None
        assert len(result.failures) == 2

    def test_empty_ids_returns_zero_created_and_no_zip(
        self, tmp_path: Path, settings: object
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)

        result = uc.create_recipe_cards_batch(recipe_ids=[])

        assert result.created_count == 0
        assert result.failures == ()
        assert result.zip_path is None
