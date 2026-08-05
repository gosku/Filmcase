import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.usecases.library.process_synced_image import process_synced_image
from src.data import models
from src.domain.images import events
from tests.factories import SyncRunFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"
# The camera set this file's Saturation, so its EXIF cannot produce a valid recipe.
CAMERA_CONTROLLED_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "fixtures" / "recipe" / "film_simulation_eterna.jpg"
)


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

    def test_records_skipped_for_an_image_that_fails_recipe_validation(self, tmp_path):
        image_path = tmp_path / CAMERA_CONTROLLED_FIXTURE.name
        shutil.copy(CAMERA_CONTROLLED_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.skipped == 1
        assert run.errors == 0
        assert run.processed == 0

    def test_publishes_an_import_skipped_event_for_invalid_recipe_data(self, tmp_path, captured_logs):
        image_path = tmp_path / CAMERA_CONTROLLED_FIXTURE.name
        shutil.copy(CAMERA_CONTROLLED_FIXTURE, image_path)
        run = SyncRunFactory(state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(image_path), sync_run_id=run.pk)

        skipped = [e for e in captured_logs if e.get("event_type") == events.IMAGE_IMPORT_SKIPPED]
        assert len(skipped) == 1
        assert skipped[0]["reason"] == events.SKIP_REASON_INVALID_RECIPE_DATA
        assert skipped[0]["recipe_field"] == "color"

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
