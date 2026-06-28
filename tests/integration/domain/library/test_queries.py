import pytest

from src.domain.library.queries import (
    FolderNotFound,
    LibraryFolderNotFound,
    get_all_library_folders,
    get_library_folder,
    list_subdirectories,
)
from tests.factories import LibraryFolderFactory


@pytest.mark.django_db
class TestGetAllLibraryFolders:
    def test_returns_empty_list_when_no_folders_registered(self):
        assert get_all_library_folders() == []

    def test_returns_all_folders_ordered_by_path(self):
        b = LibraryFolderFactory(path="/photos/beta")
        a = LibraryFolderFactory(path="/photos/alpha")
        c = LibraryFolderFactory(path="/photos/gamma")

        result = get_all_library_folders()

        assert [f.pk for f in result] == [a.pk, b.pk, c.pk]

    def test_returns_list_not_queryset(self):
        LibraryFolderFactory()
        assert isinstance(get_all_library_folders(), list)


@pytest.mark.django_db
class TestGetLibraryFolder:
    def test_returns_folder_by_id(self):
        folder = LibraryFolderFactory()
        result = get_library_folder(folder_id=folder.pk)
        assert result.pk == folder.pk

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            get_library_folder(folder_id=99999)
        assert exc_info.value.folder_id == 99999


class TestListSubdirectories:
    def test_returns_immediate_subdirectories_sorted(self, tmp_path):
        (tmp_path / "beta").mkdir()
        (tmp_path / "alpha").mkdir()
        (tmp_path / "gamma").mkdir()

        result = list_subdirectories(path=str(tmp_path))

        assert result == (
            str(tmp_path / "alpha"),
            str(tmp_path / "beta"),
            str(tmp_path / "gamma"),
        )

    def test_excludes_hidden_directories(self, tmp_path):
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()

        result = list_subdirectories(path=str(tmp_path))

        assert result == (str(tmp_path / "visible"),)

    def test_excludes_files(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("x")

        result = list_subdirectories(path=str(tmp_path))

        assert result == (str(tmp_path / "subdir"),)

    def test_returns_empty_tuple_for_empty_directory(self, tmp_path):
        assert list_subdirectories(path=str(tmp_path)) == ()

    def test_returns_only_one_level_deep(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "nested").mkdir()

        result = list_subdirectories(path=str(tmp_path))

        assert result == (str(tmp_path / "a"),)

    def test_raises_folder_not_found_for_missing_path(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FolderNotFound) as exc_info:
            list_subdirectories(path=missing)
        assert exc_info.value.path == missing

    def test_raises_folder_not_found_for_file_path(self, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        with pytest.raises(FolderNotFound) as exc_info:
            list_subdirectories(path=str(file_path))
        assert exc_info.value.path == str(file_path)
