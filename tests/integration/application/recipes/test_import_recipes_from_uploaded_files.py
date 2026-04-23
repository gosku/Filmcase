from pathlib import Path

import pytest

from src.application.usecases.recipes.import_recipes_from_uploaded_files import (
    import_recipes_from_uploaded_files,
)
from src.data import models
from src.domain.recipes.dataclasses import ImportRecipesResult, UploadedFile

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"


def uploaded_file_from_fixture(filename: str) -> UploadedFile:
    """Build an UploadedFile from a real fixture image, mimicking what the interface
    layer produces when it calls request.FILES["image"].read()."""
    path = FIXTURES_DIR / filename
    return UploadedFile(name=filename, content=path.read_bytes())


@pytest.mark.django_db
class TestImportRecipesFromUploadedFiles:
    def test_imports_recipe_from_single_file(self):
        files = [uploaded_file_from_fixture("XS107114.JPG")]

        result = import_recipes_from_uploaded_files(files=files)

        assert len(result.imported) == 1
        assert isinstance(result.imported[0], models.FujifilmRecipe)
        assert result.imported[0].film_simulation == "Classic Negative"
        assert result.failed == ()

    def test_imports_recipes_from_multiple_files(self):
        files = [
            uploaded_file_from_fixture("XS107114.JPG"),
            uploaded_file_from_fixture("XS107209.jpg"),
        ]

        result = import_recipes_from_uploaded_files(files=files)

        assert len(result.imported) == 2
        assert result.failed == ()

    def test_deduplicates_identical_recipes(self):
        files = [
            uploaded_file_from_fixture("XS107114.JPG"),
            uploaded_file_from_fixture("XS107114.JPG"),
        ]

        result = import_recipes_from_uploaded_files(files=files)

        assert len(result.imported) == 2
        assert result.imported[0].pk == result.imported[1].pk
        assert models.FujifilmRecipe.objects.count() == 1

    def test_records_failure_for_non_fujifilm_file(self):
        non_fujifilm = UploadedFile(name="canon.jpg", content=b"\xff\xd8\xff\xd9")
        files = [non_fujifilm]

        result = import_recipes_from_uploaded_files(files=files)

        assert result.imported == ()
        assert result.failed == ("canon.jpg",)

    def test_continues_after_failure_and_processes_remaining_files(self):
        non_fujifilm = UploadedFile(name="bad.jpg", content=b"\xff\xd8\xff\xd9")
        files = [
            non_fujifilm,
            uploaded_file_from_fixture("XS107114.JPG"),
        ]

        result = import_recipes_from_uploaded_files(files=files)

        assert len(result.imported) == 1
        assert result.failed == ("bad.jpg",)

    def test_temp_file_is_deleted_after_success(self, tmp_path, monkeypatch):
        created_paths: list[str] = []

        original_unlink = __import__("os").unlink

        def tracking_unlink(path: str) -> None:
            created_paths.append(path)
            original_unlink(path)

        monkeypatch.setattr("src.application.usecases.recipes.import_recipes_from_uploaded_files.os.unlink", tracking_unlink)

        files = [uploaded_file_from_fixture("XS107114.JPG")]
        import_recipes_from_uploaded_files(files=files)

        assert len(created_paths) == 1
        assert not Path(created_paths[0]).exists()

    def test_temp_file_is_deleted_after_failure(self, monkeypatch):
        created_paths: list[str] = []

        original_unlink = __import__("os").unlink

        def tracking_unlink(path: str) -> None:
            created_paths.append(path)
            original_unlink(path)

        monkeypatch.setattr("src.application.usecases.recipes.import_recipes_from_uploaded_files.os.unlink", tracking_unlink)

        files = [UploadedFile(name="bad.jpg", content=b"\xff\xd8\xff\xd9")]
        import_recipes_from_uploaded_files(files=files)

        assert len(created_paths) == 1
        assert not Path(created_paths[0]).exists()

    def test_empty_file_list_returns_empty_result(self):
        result = import_recipes_from_uploaded_files(files=[])

        assert result == ImportRecipesResult(imported=(), failed=())
