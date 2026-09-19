from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from src.application.usecases.library import remove_library_folder as remove_library_folder_uc
from src.application.usecases.library.trigger_folder_removal import (
    CeleryWorkerUnavailable,
    LibraryFolderNotFound,
    SyncAlreadyInProgress,
    run_folder_removal,
    trigger_folder_removal,
)
from src.domain.library.operations import SyncAlreadyInProgress as DomainSyncAlreadyInProgress
from src.domain.library.queries import LibraryFolderNotFound as DomainLibraryFolderNotFound

MODULE = "src.application.usecases.library.trigger_folder_removal"


def _folder(pk: int = 7) -> MagicMock:
    folder = MagicMock()
    folder.pk = pk
    return folder


def _run(pk: int = 42) -> MagicMock:
    run = MagicMock()
    run.pk = pk
    return run


class TestTriggerFolderRemovalWithoutImages:
    def test_removes_the_folder_synchronously(self):
        with patch(f"{MODULE}.remove_library_folder_uc.remove_library_folder") as mock_remove:
            trigger_folder_removal(folder_id=7, delete_images=False)

        mock_remove.assert_called_once_with(folder_id=7, delete_images=False)

    def test_translates_folder_not_found(self):
        with patch(
            f"{MODULE}.remove_library_folder_uc.remove_library_folder",
            side_effect=remove_library_folder_uc.LibraryFolderNotFound(folder_id=7),
        ):
            with pytest.raises(LibraryFolderNotFound):
                trigger_folder_removal(folder_id=7, delete_images=False)


class TestTriggerFolderRemovalWithImages:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_starts_run_and_enqueues_removal_when_worker_available(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=True),
            patch(f"{MODULE}.library_operations.start_removal_run", return_value=_run()),
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
        ):
            trigger_folder_removal(folder_id=7, delete_images=True)

        assert mock_enqueue.call_args.kwargs["task_name"] == "src.interfaces.tasks.remove_folder_images_task"
        assert mock_enqueue.call_args.kwargs["kwargs"] == {"sync_run_id": 42}
        mock_bg.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_raises_and_starts_no_run_when_worker_unavailable(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=False),
            patch(f"{MODULE}.library_operations.start_removal_run") as mock_start,
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
        ):
            with pytest.raises(CeleryWorkerUnavailable):
                trigger_folder_removal(folder_id=7, delete_images=True)

        mock_start.assert_not_called()
        mock_enqueue.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_runs_removal_in_background_in_lite_mode(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.library_operations.start_removal_run", return_value=_run()),
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
            patch(f"{MODULE}.workertasks.is_celery_worker_available") as mock_worker,
        ):
            trigger_folder_removal(folder_id=7, delete_images=True)

        mock_bg.assert_called_once_with(run_folder_removal, sync_run_id=42)
        mock_worker.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_translates_folder_not_found(self):
        with patch(
            f"{MODULE}.library_queries.get_library_folder",
            side_effect=DomainLibraryFolderNotFound(folder_id=7),
        ):
            with pytest.raises(LibraryFolderNotFound):
                trigger_folder_removal(folder_id=7, delete_images=True)

    @override_settings(USE_ASYNC_TASKS=True)
    def test_translates_sync_already_in_progress(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=True),
            patch(
                f"{MODULE}.library_operations.start_removal_run",
                side_effect=DomainSyncAlreadyInProgress(folder_id=7),
            ),
        ):
            with pytest.raises(SyncAlreadyInProgress):
                trigger_folder_removal(folder_id=7, delete_images=True)
