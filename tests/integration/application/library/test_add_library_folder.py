import pytest

from src.application.usecases.library.add_library_folder import (
    FolderAlreadyInLibrary,
    FolderNotFound,
    add_library_folder,
)
from src.application.usecases.library._dataclasses import LibraryFolderData
from src.data import models


@pytest.mark.django_db
class TestAddLibraryFolder:
    def test_returns_library_folder_data(self, tmp_path):
        result = add_library_folder(path=str(tmp_path))
        assert isinstance(result, LibraryFolderData)
        assert result.path == str(tmp_path)
        assert result.folder_id is not None
        assert result.last_processed_at is None
        assert result.last_checked_at is None

    def test_persists_folder_to_db(self, tmp_path):
        result = add_library_folder(path=str(tmp_path))
        assert models.LibraryFolder.objects.filter(pk=result.folder_id).exists()

    def test_raises_folder_not_found_for_missing_path(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FolderNotFound) as exc_info:
            add_library_folder(path=missing)
        assert exc_info.value.path == missing

    def test_raises_folder_already_in_library_for_duplicate(self, tmp_path):
        add_library_folder(path=str(tmp_path))
        with pytest.raises(FolderAlreadyInLibrary) as exc_info:
            add_library_folder(path=str(tmp_path))
        assert exc_info.value.path == str(tmp_path)
