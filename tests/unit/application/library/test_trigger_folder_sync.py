from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.library.trigger_folder_sync import (
    CeleryWorkerUnavailable,
    trigger_folder_sync,
)

MODULE = "src.application.usecases.library.trigger_folder_sync"


class TestTriggerFolderSync:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_runs_sync_inline_when_worker_available(self):
        with (
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=True),
            patch(f"{MODULE}.sync_folder") as mock_sync,
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
        ):
            trigger_folder_sync(folder_id=7)

        mock_sync.assert_called_once_with(folder_id=7)
        mock_bg.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_raises_and_does_not_sync_when_worker_unavailable(self):
        with (
            patch(f"{MODULE}.workertasks.is_celery_worker_available", return_value=False),
            patch(f"{MODULE}.sync_folder") as mock_sync,
        ):
            with pytest.raises(CeleryWorkerUnavailable):
                trigger_folder_sync(folder_id=7)

        mock_sync.assert_not_called()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_runs_sync_in_background_in_lite_mode(self):
        with (
            patch(f"{MODULE}.background.run_in_background") as mock_bg,
            patch(f"{MODULE}.sync_folder") as mock_sync,
            patch(f"{MODULE}.workertasks.is_celery_worker_available") as mock_worker,
        ):
            trigger_folder_sync(folder_id=7)

        mock_bg.assert_called_once_with(mock_sync, folder_id=7)
        mock_worker.assert_not_called()
