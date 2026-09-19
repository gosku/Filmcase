from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.library.run_folder_removal import run_folder_removal
from src.data import models
from src.domain.library.operations import start_removal_run
from tests.factories import ImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestRunFolderRemovalLiteMode:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_removes_owned_images_and_deletes_the_folder(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/a.jpg")
        run = start_removal_run(folder=folder)

        run_folder_removal(sync_run_id=run.pk)

        assert not models.Image.objects.filter(pk=image.pk).exists()
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_deletes_the_folder_immediately_when_nothing_is_owned(self):
        folder = LibraryFolderFactory(path="/photos")
        run = start_removal_run(folder=folder)

        run_folder_removal(sync_run_id=run.pk)

        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_keeps_images_another_folder_still_covers(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        image = ImageFactory(filepath="/photos/2024/a.jpg")
        run = start_removal_run(folder=inner)

        run_folder_removal(sync_run_id=run.pk)

        assert models.Image.objects.filter(pk=image.pk).exists()
        assert not models.LibraryFolder.objects.filter(pk=inner.pk).exists()


@pytest.mark.django_db
class TestRunFolderRemovalAsyncMode:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_records_the_total_and_dispatches_one_task_per_owned_image(self):
        folder = LibraryFolderFactory(path="/photos")
        first = ImageFactory(filepath="/photos/a.jpg")
        second = ImageFactory(filepath="/photos/b.jpg")
        run = start_removal_run(folder=folder)

        with patch(
            "src.application.usecases.library.run_folder_removal.workertasks.enqueue_tasks"
        ) as mock_enqueue:
            run_folder_removal(sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.total == 2
        assert run.state == models.SyncRun.STATE_REMOVING
        assert models.LibraryFolder.objects.filter(pk=folder.pk).exists()
        kwargs = mock_enqueue.call_args.kwargs
        assert kwargs["task_name"] == "src.interfaces.tasks.remove_folder_image_task"
        assert kwargs["kwargs_list"] == [
            {"image_id": first.pk, "sync_run_id": run.pk},
            {"image_id": second.pk, "sync_run_id": run.pk},
        ]

    @override_settings(USE_ASYNC_TASKS=True)
    def test_does_nothing_when_the_run_is_gone(self):
        with patch(
            "src.application.usecases.library.run_folder_removal.workertasks.enqueue_tasks"
        ) as mock_enqueue:
            run_folder_removal(sync_run_id=999999)

        mock_enqueue.assert_not_called()
