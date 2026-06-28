import pytest

from src.data import models
from src.domain.library import events
from src.domain.library.operations import (
    FolderAlreadyInLibrary,
    add_library_folder,
    remove_library_folder,
    update_library_folder_path,
)
from src.domain.library.queries import FolderNotFound, LibraryFolderNotFound
from tests.factories import LibraryFolderFactory


@pytest.mark.django_db
class TestAddLibraryFolder:
    def test_creates_library_folder_row(self, tmp_path):
        result = add_library_folder(path=str(tmp_path))

        assert models.LibraryFolder.objects.filter(pk=result.pk).exists()
        assert result.path == str(tmp_path)

    def test_normalizes_tilde_in_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = add_library_folder(path="~")
        assert result.path == str(tmp_path)

    def test_publishes_folder_added_event(self, tmp_path, captured_logs):
        result = add_library_folder(path=str(tmp_path))

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_ADDED]
        assert len(matching) == 1
        assert matching[0]["folder_id"] == result.pk
        assert matching[0]["path"] == str(tmp_path)

    def test_raises_folder_not_found_for_missing_path(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FolderNotFound) as exc_info:
            add_library_folder(path=missing)
        assert exc_info.value.path == missing

    def test_raises_folder_not_found_for_file_path(self, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        with pytest.raises(FolderNotFound):
            add_library_folder(path=str(file_path))

    def test_raises_folder_already_in_library_for_duplicate_path(self, tmp_path):
        add_library_folder(path=str(tmp_path))
        with pytest.raises(FolderAlreadyInLibrary) as exc_info:
            add_library_folder(path=str(tmp_path))
        assert exc_info.value.path == str(tmp_path)


@pytest.mark.django_db
class TestRemoveLibraryFolder:
    def test_deletes_library_folder_row(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        remove_library_folder(folder_id=folder.pk)
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_publishes_folder_removed_event(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        remove_library_folder(folder_id=folder.pk)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_REMOVED]
        assert len(matching) == 1
        assert matching[0]["folder_id"] == folder.pk
        assert matching[0]["path"] == str(tmp_path)

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            remove_library_folder(folder_id=99999)
        assert exc_info.value.folder_id == 99999


@pytest.mark.django_db
class TestUpdateLibraryFolderPath:
    def test_updates_path_on_folder(self, tmp_path):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()

        folder = LibraryFolderFactory(path=str(old_dir))
        result = update_library_folder_path(folder_id=folder.pk, path=str(new_dir))

        assert result.path == str(new_dir)
        folder.refresh_from_db()
        assert folder.path == str(new_dir)

    def test_publishes_folder_path_updated_event(self, tmp_path, captured_logs):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()

        folder = LibraryFolderFactory(path=str(old_dir))
        update_library_folder_path(folder_id=folder.pk, path=str(new_dir))

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_PATH_UPDATED]
        assert len(matching) == 1
        assert matching[0]["folder_id"] == folder.pk
        assert matching[0]["path"] == str(new_dir)

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
