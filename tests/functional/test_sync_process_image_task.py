import shutil
from pathlib import Path

import pytest

from src.data import models
from src.interfaces.tasks import sync_process_image_task
from tests.factories import SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"


@pytest.mark.django_db
class TestSyncProcessImageTask:
    def test_processes_image_and_records_progress_against_run(self, tmp_path):
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
