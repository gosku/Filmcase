import shutil
from pathlib import Path

import pytest

from src.data import models
from unittest import mock

from src.interfaces import tasks as interface_tasks
from src.interfaces.tasks import (
    finalize_sync_run_task,
    sync_dispatch_image_batch_task,
    sync_process_image_batch_task,
    sync_process_image_task,
)
from tests.factories import ImageFactory, LibraryFolderFactory, SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
SECOND_FIXTURE = FIXTURES_DIR / "XS107209.jpg"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"


@pytest.mark.django_db
class TestSyncProcessImageTask:
    def test_processes_the_image_and_records_progress_against_run(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        sync_process_image_task.apply(
            kwargs={"image_path": str(image_path), "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 1
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert models.Image.objects.filter(filepath=str(image_path)).exists()

    def test_completes_the_run_only_once_every_image_has_reported(self, tmp_path):
        first = tmp_path / FUJIFILM_FIXTURE.name
        second = tmp_path / SECOND_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, first)
        shutil.copy(SECOND_FIXTURE, second)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        sync_process_image_task.apply(
            kwargs={"image_path": str(first), "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 1
        assert run.state == models.SyncRun.STATE_PROCESSING

        sync_process_image_task.apply(
            kwargs={"image_path": str(second), "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 2
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert models.Image.objects.count() == 2

    def test_records_an_image_it_cannot_import_as_skipped(self, tmp_path):
        rejected = tmp_path / NON_FUJIFILM_FIXTURE.name
        shutil.copy(NON_FUJIFILM_FIXTURE, rejected)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        sync_process_image_task.apply(
            kwargs={"image_path": str(rejected), "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 0
        assert run.skipped == 1
        assert models.IgnoredImage.objects.count() == 1


@pytest.mark.django_db
class TestSyncDispatchImageBatchTask:
    def test_publishes_one_task_per_image_in_the_batch(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        with mock.patch.object(interface_tasks.workertasks, "enqueue_tasks") as mock_enqueue:
            sync_dispatch_image_batch_task.apply(
                kwargs={"image_paths": ["/a.jpg", "/b.jpg"], "sync_run_id": run.pk}
            ).get()

        kwargs = mock_enqueue.call_args.kwargs
        assert kwargs["task_name"] == "src.interfaces.tasks.sync_process_image_task"
        assert kwargs["kwargs_list"] == [
            {"image_path": "/a.jpg", "sync_run_id": run.pk},
            {"image_path": "/b.jpg", "sync_run_id": run.pk},
        ]

    def test_processes_nothing_itself(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        with mock.patch.object(interface_tasks.workertasks, "enqueue_tasks"):
            sync_dispatch_image_batch_task.apply(
                kwargs={"image_paths": [str(image_path)], "sync_run_id": run.pk}
            ).get()

        run.refresh_from_db()
        assert run.processed == 0
        assert not models.Image.objects.exists()

    def test_an_empty_batch_dispatches_nothing(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=0)

        with mock.patch.object(interface_tasks.workertasks, "enqueue_tasks") as mock_enqueue:
            sync_dispatch_image_batch_task.apply(
                kwargs={"image_paths": [], "sync_run_id": run.pk}
            ).get()

        assert mock_enqueue.call_args.kwargs["kwargs_list"] == []


@pytest.mark.django_db
class TestSyncProcessImageBatchTask:
    def test_dispatches_rather_than_processes_so_in_flight_messages_still_run(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        with mock.patch.object(interface_tasks.workertasks, "enqueue_tasks") as mock_enqueue:
            sync_process_image_batch_task.apply(
                kwargs={"image_paths": ["/a.jpg"], "sync_run_id": run.pk}
            ).get()

        kwargs = mock_enqueue.call_args.kwargs
        assert kwargs["task_name"] == "src.interfaces.tasks.sync_process_image_task"
        assert kwargs["kwargs_list"] == [{"image_path": "/a.jpg", "sync_run_id": run.pk}]


@pytest.mark.django_db
class TestFinalizeSyncRunTask:
    def test_finishes_the_run_and_removes_what_is_gone(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=0)
        image = ImageFactory(filepath=str(tmp_path / "gone.jpg"))

        finalize_sync_run_task.apply(kwargs={"sync_run_id": run.pk}).get()

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert run.removed == 1
        assert not models.Image.objects.filter(pk=image.pk).exists()

    def test_does_nothing_for_a_run_that_no_longer_exists(self):
        finalize_sync_run_task.apply(kwargs={"sync_run_id": 9999}).get()
