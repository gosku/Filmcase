import pytest

from src.application.usecases.library.update_library_folder_path import (
    FolderAlreadyInLibrary,
    FolderNotFound,
    LibraryFolderNotFound,
    update_library_folder_path,
)
from src.application.usecases.library._dataclasses import LibraryFolderData
from tests.factories import LibraryFolderFactory


@pytest.mark.django_db
class TestUpdateLibraryFolderPath:
    def test_returns_updated_library_folder_data(self, tmp_path):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()

        folder = LibraryFolderFactory(path=str(old_dir))
        result = update_library_folder_path(folder_id=folder.pk, path=str(new_dir))

        assert isinstance(result, LibraryFolderData)
        assert result.path == str(new_dir)
        assert result.folder_id == folder.pk

    def test_raises_library_folder_not_found_for_unknown_id(self, tmp_path):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            update_library_folder_path(folder_id=99999, path=str(tmp_path))
        assert exc_info.value.folder_id == 99999

    def test_raises_folder_not_found_for_missing_path(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FolderNotFound) as exc_info:
            update_library_folder_path(folder_id=folder.pk, path=missing)
        assert exc_info.value.path == missing

    def test_raises_folder_already_in_library_when_path_taken(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()

        LibraryFolderFactory(path=str(dir_a))
        folder_b = LibraryFolderFactory(path=str(dir_b))

        with pytest.raises(FolderAlreadyInLibrary) as exc_info:
            update_library_folder_path(folder_id=folder_b.pk, path=str(dir_a))
        assert exc_info.value.path == str(dir_a)
