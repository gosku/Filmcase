import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.usecases.library.process_synced_image import process_synced_image
from src.data import models
from src.domain.images import events
from tests.factories import IgnoredImageFactory, LibraryFolderFactory, SyncRunFactory

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


@pytest.mark.django_db
class TestProcessSyncedImageRemembersFailures:
    def test_remembers_a_non_fujifilm_file(self, tmp_path):
        photo = tmp_path / NON_FUJIFILM_FIXTURE.name
        shutil.copy(NON_FUJIFILM_FIXTURE, photo)
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(photo), sync_run_id=run.pk)

        ignored = models.IgnoredImage.objects.get()
        assert ignored.filepath == str(photo)
        assert ignored.reason == models.IgnoredImage.REASON_NO_FILM_SIMULATION
        assert ignored.folder_id == folder.pk
        assert ignored.file_size == photo.stat().st_size

    def test_remembers_an_unexpected_failure_with_its_message(self, tmp_path):
        photo = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, photo)
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)

        with patch(
            "src.domain.images.operations.process_image",
            side_effect=OSError("disk went away"),
        ):
            process_synced_image(image_path=str(photo), sync_run_id=run.pk)

        ignored = models.IgnoredImage.objects.get()
        assert ignored.reason == models.IgnoredImage.REASON_ERROR
        assert ignored.detail == "OSError: disk went away"

    def test_remembers_nothing_for_a_successful_import(self, tmp_path):
        photo = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, photo)
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(photo), sync_run_id=run.pk)

        assert models.IgnoredImage.objects.count() == 0

    def test_a_file_that_vanished_does_not_break_the_run(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)

        process_synced_image(image_path=str(tmp_path / "gone.jpg"), sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.errors == 1
        assert models.IgnoredImage.objects.count() == 0

    def test_a_previously_ignored_file_that_imports_stops_being_ignored(self, tmp_path):
        photo = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, photo)
        folder = LibraryFolderFactory(path=str(tmp_path))
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=1)
        IgnoredImageFactory(folder=folder, filepath=str(photo))

        process_synced_image(image_path=str(photo), sync_run_id=run.pk)

        assert models.Image.objects.count() == 1
        assert models.IgnoredImage.objects.count() == 0
