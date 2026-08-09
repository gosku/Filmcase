import shutil
from pathlib import Path

import pytest

from src.data import models
from src.interfaces.tasks import finalize_sync_run_task, sync_process_image_batch_task
from tests.factories import ImageFactory, LibraryFolderFactory, SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
SECOND_FIXTURE = FIXTURES_DIR / "XS107209.jpg"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"


@pytest.mark.django_db
class TestSyncProcessImageBatchTask:
    def test_processes_a_single_image_and_records_progress_against_run(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        sync_process_image_batch_task.apply(
            kwargs={"image_paths": [str(image_path)], "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 1
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert models.Image.objects.filter(filepath=str(image_path)).exists()

    def test_processes_every_image_in_the_batch(self, tmp_path):
        first = tmp_path / FUJIFILM_FIXTURE.name
        second = tmp_path / SECOND_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, first)
        shutil.copy(SECOND_FIXTURE, second)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        sync_process_image_batch_task.apply(
            kwargs={"image_paths": [str(first), str(second)], "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 2
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert models.Image.objects.count() == 2

    def test_accounts_for_each_image_separately_within_a_batch(self, tmp_path):
        importable = tmp_path / FUJIFILM_FIXTURE.name
        rejected = tmp_path / NON_FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, importable)
        shutil.copy(NON_FUJIFILM_FIXTURE, rejected)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        sync_process_image_batch_task.apply(
            kwargs={"image_paths": [str(importable), str(rejected)], "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 1
        assert run.skipped == 1
        assert models.IgnoredImage.objects.count() == 1

    def test_an_empty_batch_does_nothing(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=0)

        sync_process_image_batch_task.apply(
            kwargs={"image_paths": [], "sync_run_id": run.pk}
        ).get()

        run.refresh_from_db()
        assert run.processed == 0


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
