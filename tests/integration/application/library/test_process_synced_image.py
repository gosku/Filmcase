import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.usecases.library.process_synced_image import process_synced_image
from src.data import models
from tests.factories import SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"


@pytest.mark.django_db
class TestProcessSyncedImage:
    def test_imports_image_and_records_processed(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.processed == 1
        assert run.skipped == 0
        assert run.errors == 0
        assert models.Image.objects.filter(filepath=str(image_path)).exists()

    def test_records_skipped_for_non_fujifilm_image(self, tmp_path):
        image_path = tmp_path / NON_FUJIFILM_FIXTURE.name
        shutil.copy(NON_FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.skipped == 1
        assert run.processed == 0

    def test_records_error_and_continues_on_unexpected_failure(self):
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        with patch(
            "src.application.usecases.library.process_synced_image.image_operations.process_image",
            side_effect=ValueError("boom"),
        ):
            process_synced_image(image_path="/whatever.jpg", sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.errors == 1
        assert run.processed == 0

    def test_completes_run_when_all_images_accounted_for(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_COMPLETED
        assert run.finished_at is not None

    def test_leaves_run_processing_while_images_remain(self, tmp_path):
        image_path = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=2)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.state == models.SyncRun.STATE_PROCESSING

    def test_returns_silently_when_run_missing(self):
        # No exception should escape when the run (and its folder) is already gone.
        process_synced_image(image_path="/whatever.jpg", sync_run_id=99999)
