import pytest
import time_machine

from src.data import models
from src.domain.library.queries import (
    FolderNotFound,
    LibraryFolderNotFound,
    SyncRunNotFound,
    get_active_sync_run,
    get_all_library_folders,
    get_latest_sync_run,
    get_library_folder,
    get_sync_run,
    list_subdirectories,
)
from tests.factories import LibraryFolderFactory, SyncRunFactory


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

    def test_excludes_directories_matching_an_ignored_prefix(self, tmp_path):
        # @eaDir matches the default '@' prefix, so it is not offered when browsing.
        (tmp_path / "visible").mkdir()
        (tmp_path / "@eaDir").mkdir()

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


@pytest.mark.django_db
class TestGetLatestSyncRun:
    def test_returns_none_when_folder_never_synced(self):
        folder = LibraryFolderFactory()
        assert get_latest_sync_run(folder_id=folder.pk) is None

    def test_returns_the_most_recently_started_run(self):
        folder = LibraryFolderFactory()
        # Only one run may be active per folder, so the earlier one is terminal.
        with time_machine.travel("2026-07-01", tick=False):
            SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED)
        with time_machine.travel("2026-07-02", tick=False):
            latest = SyncRunFactory(folder=folder)

        result = get_latest_sync_run(folder_id=folder.pk)

        assert result is not None
        assert result.pk == latest.pk

    def test_ignores_runs_for_other_folders(self):
        folder = LibraryFolderFactory()
        other = LibraryFolderFactory()
        SyncRunFactory(folder=other)

        assert get_latest_sync_run(folder_id=folder.pk) is None


@pytest.mark.django_db
class TestGetSyncRun:
    def test_returns_run_by_id(self):
        run = SyncRunFactory()
        result = get_sync_run(run_id=run.pk)
        assert result.pk == run.pk

    def test_raises_sync_run_not_found_for_unknown_id(self):
        with pytest.raises(SyncRunNotFound) as exc_info:
            get_sync_run(run_id=99999)
        assert exc_info.value.run_id == 99999


@pytest.mark.django_db
class TestGetActiveSyncRun:
    def test_returns_none_when_no_run_active(self):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED)

        assert get_active_sync_run(folder_id=folder.pk) is None

    def test_returns_scanning_run(self):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_SCANNING)

        result = get_active_sync_run(folder_id=folder.pk)

        assert result is not None
        assert result.pk == run.pk

    def test_returns_processing_run(self):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=3)

        result = get_active_sync_run(folder_id=folder.pk)

        assert result is not None
        assert result.pk == run.pk

    def test_ignores_active_runs_for_other_folders(self):
        folder = LibraryFolderFactory()
        other = LibraryFolderFactory()
        SyncRunFactory(folder=other, state=models.SyncRun.STATE_PROCESSING, total=1)

        assert get_active_sync_run(folder_id=folder.pk) is None
