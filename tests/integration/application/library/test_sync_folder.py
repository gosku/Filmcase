import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.library.sync_folder import sync_folder
from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory, SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"


@pytest.mark.django_db
class TestSyncFolderLiteMode:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_imports_new_image_and_completes_run(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_folder(folder_id=folder.pk)

        run = models.SyncRun.objects.get(folder=folder)
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert run.total == 1
        assert run.processed == 1
        assert models.Image.objects.filter(filepath=str(image_path)).exists()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_completes_run_with_zero_total_when_no_new_files(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_folder(folder_id=folder.pk)

        run = models.SyncRun.objects.get(folder=folder)
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert run.total == 0

    @override_settings(USE_ASYNC_TASKS=False)
    def test_ignores_already_known_images(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        ImageFactory(filepath=str(image_path))
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_folder(folder_id=folder.pk)

        run = models.SyncRun.objects.get(folder=folder)
        assert run.total == 0
        assert run.state == models.SyncRun.STATE_COMPLETED

    @override_settings(USE_ASYNC_TASKS=False)
    def test_updates_folder_timestamps(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_folder(folder_id=folder.pk)

        folder.refresh_from_db()
        assert folder.last_checked_at is not None
        assert folder.last_processed_at is not None

    @override_settings(USE_ASYNC_TASKS=False)
    def test_fails_run_and_stamps_check_time_when_folder_missing(self, tmp_path):
        missing = tmp_path / "gone"
        folder = LibraryFolderFactory(path=str(missing))

        sync_folder(folder_id=folder.pk)

        run = models.SyncRun.objects.get(folder=folder)
        assert run.state == models.SyncRun.STATE_FAILED
        folder.refresh_from_db()
        assert folder.last_checked_at is not None


@pytest.mark.django_db
class TestSyncFolderAsyncMode:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_enqueues_a_task_per_new_image_and_leaves_run_processing(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        folder = LibraryFolderFactory(path=str(tmp_path))

        with patch("src.application.usecases.library.sync_folder.workertasks.enqueue_task") as mock_enqueue:
            sync_folder(folder_id=folder.pk)

        run = models.SyncRun.objects.get(folder=folder)
        assert run.state == models.SyncRun.STATE_PROCESSING
        assert run.total == 1
        mock_enqueue.assert_called_once()
        kwargs = mock_enqueue.call_args.kwargs
        assert kwargs["task_name"] == "src.interfaces.tasks.sync_process_image_task"
        assert kwargs["kwargs"] == {"image_path": str(image_path), "sync_run_id": run.pk}


@pytest.mark.django_db
class TestSyncFolderGuards:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_does_nothing_when_folder_already_has_active_run(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=5)

        sync_folder(folder_id=folder.pk)

        assert models.SyncRun.objects.filter(folder=folder).count() == 1

    @override_settings(USE_ASYNC_TASKS=False)
    def test_returns_without_creating_a_run_when_folder_missing(self):
        sync_folder(folder_id=99999)

        assert models.SyncRun.objects.count() == 0


@pytest.mark.django_db
class TestSyncFolderDoesNotReExamineIgnoredImages:
    """
    The regression this guards: a file the sync cannot import leaves no catalog
    entry, so before this it was rediscovered and re-read on every single sync.
    """

    @pytest.fixture(autouse=True)
    def _lite_mode(self, settings):
        settings.USE_ASYNC_TASKS = False

    def _folder_with_a_non_fujifilm_file(self, tmp_path):
        photo = tmp_path / NON_FUJIFILM_FIXTURE.name
        shutil.copy(NON_FUJIFILM_FIXTURE, photo)
        return LibraryFolderFactory(path=str(tmp_path)), photo

    def test_the_second_sync_finds_nothing_to_do(self, tmp_path):
        folder, _ = self._folder_with_a_non_fujifilm_file(tmp_path)

        sync_folder(folder_id=folder.pk)
        sync_folder(folder_id=folder.pk)

        runs = list(models.SyncRun.objects.order_by("id"))
        assert runs[0].total == 1
        assert runs[0].skipped == 1
        assert runs[1].total == 0
        assert runs[1].skipped == 0

    def test_it_stays_ignored_however_often_the_sync_runs(self, tmp_path):
        folder, _ = self._folder_with_a_non_fujifilm_file(tmp_path)

        for _ in range(4):
            sync_folder(folder_id=folder.pk)

        assert [r.total for r in models.SyncRun.objects.order_by("id")] == [1, 0, 0, 0]
        assert models.IgnoredImage.objects.count() == 1

    def test_a_file_that_changes_is_examined_again(self, tmp_path):
        folder, photo = self._folder_with_a_non_fujifilm_file(tmp_path)
        sync_folder(folder_id=folder.pk)

        # A different file now occupies that path.
        shutil.copy(FUJIFILM_FIXTURE, photo)
        sync_folder(folder_id=folder.pk)

        runs = list(models.SyncRun.objects.order_by("id"))
        assert runs[1].total == 1
        assert runs[1].processed == 1
        assert models.Image.objects.count() == 1
        assert models.IgnoredImage.objects.count() == 0

    def test_a_file_whose_timestamp_alone_moves_is_examined_again(self, tmp_path):
        folder, photo = self._folder_with_a_non_fujifilm_file(tmp_path)
        sync_folder(folder_id=folder.pk)

        later = photo.stat().st_mtime + 120
        os.utime(photo, (later, later))
        sync_folder(folder_id=folder.pk)

        runs = list(models.SyncRun.objects.order_by("id"))
        assert runs[1].total == 1
        assert runs[1].skipped == 1
        # Re-recorded with the new fingerprint, so it settles again rather than
        # being re-examined for ever.
        assert models.IgnoredImage.objects.count() == 1
        sync_folder(folder_id=folder.pk)
        assert models.SyncRun.objects.order_by("id").last().total == 0

    def test_forgetting_the_record_brings_the_file_back(self, tmp_path):
        folder, _ = self._folder_with_a_non_fujifilm_file(tmp_path)
        sync_folder(folder_id=folder.pk)

        models.IgnoredImage.objects.all().delete()
        sync_folder(folder_id=folder.pk)

        assert models.SyncRun.objects.order_by("id").last().total == 1

    def test_an_importable_file_is_unaffected(self, tmp_path):
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 1
        assert models.IgnoredImage.objects.count() == 0
