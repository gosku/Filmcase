import pytest

from src.data import models
from src.domain.library import events
from src.domain.library.operations import (
    FolderAlreadyInLibrary,
    SyncAlreadyInProgress,
    add_library_folder,
    begin_pruning,
    complete_sync_run,
    fail_sync_run,
    interrupt_active_sync_runs,
    remove_library_folder,
    start_sync_run,
    update_library_folder_path,
)
from src.domain.library.queries import FolderNotFound, LibraryFolderNotFound
from tests.factories import ImageFactory, LibraryFolderFactory, SyncRunFactory


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
        remove_library_folder(folder_id=folder.pk, delete_images=False)
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_publishes_folder_removed_event(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        remove_library_folder(folder_id=folder.pk, delete_images=False)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_REMOVED]
        assert len(matching) == 1
        assert matching[0]["folder_id"] == folder.pk
        assert matching[0]["path"] == str(tmp_path)

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            remove_library_folder(folder_id=99999, delete_images=False)
        assert exc_info.value.folder_id == 99999

    def test_keeps_the_images_when_only_the_folder_is_removed(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image = ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"))

        removed = remove_library_folder(folder_id=folder.pk, delete_images=False)

        assert removed == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_removes_the_images_when_asked_to(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image = ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"))

        removed = remove_library_folder(folder_id=folder.pk, delete_images=True)

        assert removed == 1
        assert not models.Image.objects.filter(pk=image.pk).exists()

    def test_never_deletes_the_image_files(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = tmp_path / "DSCF0001.JPG"
        photo.write_bytes(b"\xff\xd8")
        ImageFactory(filepath=str(photo))

        remove_library_folder(folder_id=folder.pk, delete_images=True)

        assert photo.exists()

    def test_keeps_images_a_second_registered_folder_still_covers(self, tmp_path):
        outer = LibraryFolderFactory(path=str(tmp_path))
        inner_dir = tmp_path / "2024"
        LibraryFolderFactory(path=str(inner_dir))
        shared = ImageFactory(filepath=str(inner_dir / "DSCF0001.JPG"))
        only_outer = ImageFactory(filepath=str(tmp_path / "DSCF0002.JPG"))

        removed = remove_library_folder(folder_id=outer.pk, delete_images=True)

        assert removed == 1
        assert models.Image.objects.filter(pk=shared.pk).exists()
        assert not models.Image.objects.filter(pk=only_outer.pk).exists()

    def test_publishes_folder_images_removed_when_images_go(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"))

        remove_library_folder(folder_id=folder.pk, delete_images=True)

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_IMAGES_REMOVED
        ]
        assert len(matching) == 1
        assert matching[0]["removed"] == 1

    def test_publishes_no_images_removed_event_when_none_go(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))

        remove_library_folder(folder_id=folder.pk, delete_images=True)

        assert [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_FOLDER_IMAGES_REMOVED
        ] == []


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

    def test_remembers_where_the_folder_pointed_before(self, tmp_path):
        old_dir = tmp_path / "photos"
        new_dir = old_dir / "2024"
        new_dir.mkdir(parents=True)
        folder = LibraryFolderFactory(path=str(old_dir))

        update_library_folder_path(folder_id=folder.pk, path=str(new_dir))

        folder.refresh_from_db()
        assert folder.previous_path == str(old_dir)

    def test_a_second_change_keeps_the_original_territory(self, tmp_path):
        # /photos -> /photos/2024 -> /photos/2024/january must still remember
        # /photos, which is where the stranded images actually are.
        original = tmp_path / "photos"
        middle = original / "2024"
        innermost = middle / "january"
        innermost.mkdir(parents=True)
        folder = LibraryFolderFactory(path=str(original))

        update_library_folder_path(folder_id=folder.pk, path=str(middle))
        update_library_folder_path(folder_id=folder.pk, path=str(innermost))

        folder.refresh_from_db()
        assert folder.previous_path == str(original)

    def test_records_afresh_once_the_previous_path_has_been_cleared(self, tmp_path):
        first = tmp_path / "a"
        second = tmp_path / "b"
        third = tmp_path / "c"
        for d in (first, second, third):
            d.mkdir()
        folder = LibraryFolderFactory(path=str(first))

        update_library_folder_path(folder_id=folder.pk, path=str(second))
        folder.refresh_from_db()
        folder.clear_previous_path()
        update_library_folder_path(folder_id=folder.pk, path=str(third))

        folder.refresh_from_db()
        assert folder.previous_path == str(second)

    def test_remembers_nothing_when_the_path_is_unchanged(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path))

        folder.refresh_from_db()
        assert folder.previous_path == ""

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


@pytest.mark.django_db
class TestStartSyncRun:
    def test_creates_scanning_run(self):
        folder = LibraryFolderFactory()

        run = start_sync_run(folder=folder)

        assert models.SyncRun.objects.filter(pk=run.pk).exists()
        assert run.state == models.SyncRun.STATE_SCANNING
        assert run.folder_id == folder.pk

    def test_publishes_sync_run_started_event(self, captured_logs):
        folder = LibraryFolderFactory()

        run = start_sync_run(folder=folder)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_STARTED]
        assert len(matching) == 1
        assert matching[0]["run_id"] == run.pk
        assert matching[0]["folder_id"] == folder.pk

    def test_raises_when_folder_already_has_active_run(self):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)

        with pytest.raises(SyncAlreadyInProgress) as exc_info:
            start_sync_run(folder=folder)
        assert exc_info.value.folder_id == folder.pk

    def test_allows_new_run_after_previous_completed(self):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED)

        run = start_sync_run(folder=folder)

        assert run.state == models.SyncRun.STATE_SCANNING


@pytest.mark.django_db
class TestCompleteSyncRun:
    def test_transitions_processing_run_to_completed(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        result = complete_sync_run(run=run)

        assert result is True
        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert run.finished_at is not None

    def test_publishes_sync_run_completed_event(self, captured_logs):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        complete_sync_run(run=run)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_COMPLETED]
        assert len(matching) == 1
        assert matching[0]["run_id"] == run.pk
        assert matching[0]["folder_id"] == run.folder_id

    def test_returns_false_and_publishes_nothing_when_already_completed(self, captured_logs):
        run = SyncRunFactory(state=models.SyncRun.STATE_COMPLETED, total=1)

        result = complete_sync_run(run=run)

        assert result is False
        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_COMPLETED]
        assert matching == []

    def test_transitions_a_pruning_run_to_completed(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PRUNING, total=1)

        assert complete_sync_run(run=run) is True

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_COMPLETED


@pytest.mark.django_db
class TestBeginPruning:
    def test_transitions_a_processing_run_to_pruning(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        assert begin_pruning(run=run) is True

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_PRUNING
        assert run.finished_at is None

    def test_leaves_the_folder_locked_against_a_second_sync_while_pruning(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        begin_pruning(run=run)

        run.refresh_from_db()
        assert run.state in models.SyncRun.ACTIVE_STATES

    def test_only_the_first_caller_wins(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)
        contender = models.SyncRun.objects.get(pk=run.pk)

        assert begin_pruning(run=run) is True
        assert begin_pruning(run=contender) is False

    def test_does_not_start_from_a_failed_run(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_FAILED, total=1)

        assert begin_pruning(run=run) is False

    def test_publishes_prune_started_only_for_the_winner(self, captured_logs):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)
        contender = models.SyncRun.objects.get(pk=run.pk)

        begin_pruning(run=run)
        begin_pruning(run=contender)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_PRUNE_STARTED]
        assert len(matching) == 1
        assert matching[0]["run_id"] == run.pk


@pytest.mark.django_db
class TestFailSyncRun:
    def test_marks_run_failed_with_message(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_SCANNING)

        fail_sync_run(
            run=run,
            reason=models.SyncRun.FAILED_FOLDER_MISSING,
            message="folder no longer exists",
        )

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_FAILED
        assert run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING
        assert run.error_message == "folder no longer exists"
        assert run.finished_at is not None

    def test_publishes_sync_run_failed_event(self, captured_logs):
        run = SyncRunFactory(state=models.SyncRun.STATE_SCANNING)

        fail_sync_run(run=run, reason=models.SyncRun.FAILED_FOLDER_MISSING, message="boom")

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_FAILED]
        assert len(matching) == 1
        assert matching[0]["run_id"] == run.pk
        assert matching[0]["folder_id"] == run.folder_id
        assert matching[0]["reason"] == "boom"


@pytest.mark.django_db
class TestInterruptActiveSyncRuns:
    def test_marks_scanning_and_processing_runs_interrupted(self):
        scanning = SyncRunFactory(state=models.SyncRun.STATE_SCANNING)
        processing = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        count = interrupt_active_sync_runs()

        assert count == 2
        for run in (scanning, processing):
            run.refresh_from_db()
            assert run.state == models.SyncRun.STATE_INTERRUPTED
            assert run.finished_at is not None

    def test_leaves_terminal_runs_untouched(self):
        completed = SyncRunFactory(state=models.SyncRun.STATE_COMPLETED)

        count = interrupt_active_sync_runs()

        assert count == 0
        completed.refresh_from_db()
        assert completed.state == models.SyncRun.STATE_COMPLETED

    def test_publishes_event_with_count_when_runs_interrupted(self, captured_logs):
        SyncRunFactory(state=models.SyncRun.STATE_SCANNING)

        interrupt_active_sync_runs()

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_INTERRUPTED]
        assert len(matching) == 1
        assert matching[0]["count"] == 1

    def test_publishes_nothing_when_no_active_runs(self, captured_logs):
        interrupt_active_sync_runs()

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_RUN_INTERRUPTED]
        assert matching == []
