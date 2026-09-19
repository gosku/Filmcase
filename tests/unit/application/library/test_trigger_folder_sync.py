from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from src.application.usecases.library.trigger_folder_sync import (
    CeleryWorkerUnavailable,
    resume_folder_scan,
    trigger_folder_sync,
)
from src.domain.library.operations import SyncAlreadyInProgress
from src.domain.library.queries import LibraryFolderNotFound

MODULE = "src.application.usecases.library.trigger_folder_sync"


def _folder(pk: int = 7) -> MagicMock:
    folder = MagicMock()
    folder.pk = pk
    return folder


def _run(pk: int = 42) -> MagicMock:
    run = MagicMock()
    run.pk = pk
    return run


class TestTriggerFolderSync:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_starts_run_and_enqueues_scan_when_worker_available(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.library_operations.start_sync_run", return_value=_run()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=True),
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
        ):
            trigger_folder_sync(folder_id=7)

        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args.kwargs["task_name"] == "src.interfaces.tasks.sync_folder_scan_task"
        assert mock_enqueue.call_args.kwargs["kwargs"] == {"sync_run_id": 42}
        mock_bg.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_raises_and_starts_no_run_when_worker_unavailable(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=False),
            patch(f"{MODULE}.library_operations.start_sync_run") as mock_start,
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
        ):
            with pytest.raises(CeleryWorkerUnavailable):
                trigger_folder_sync(folder_id=7)

        mock_start.assert_not_called()
        mock_enqueue.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_resumes_scan_in_background_in_lite_mode(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.library_operations.start_sync_run", return_value=_run()),
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
            patch(f"{MODULE}.workertasks.is_celery_worker_available") as mock_worker,
        ):
            trigger_folder_sync(folder_id=7)

        mock_bg.assert_called_once_with(resume_folder_scan, sync_run_id=42)
        mock_worker.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_does_nothing_when_folder_is_gone(self):
        with (
            patch(
                f"{MODULE}.library_queries.get_library_folder",
                side_effect=LibraryFolderNotFound(folder_id=7),
            ),
            patch(f"{MODULE}.library_operations.start_sync_run") as mock_start,
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
        ):
            trigger_folder_sync(folder_id=7)

        mock_start.assert_not_called()
        mock_enqueue.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_does_nothing_when_a_run_is_already_active(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=_folder()),
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=True),
            patch(
                f"{MODULE}.library_operations.start_sync_run",
                side_effect=SyncAlreadyInProgress(folder_id=7),
            ),
            patch(f"{MODULE}.workertasks.enqueue_task") as mock_enqueue,
        ):
            trigger_folder_sync(folder_id=7)

        mock_enqueue.assert_not_called()
