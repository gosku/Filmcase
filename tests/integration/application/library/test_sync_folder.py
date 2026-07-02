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
