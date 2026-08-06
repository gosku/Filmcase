import shutil
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

from src.data import models
from src.domain.images import events

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
# The camera set this file's Saturation, so its EXIF cannot produce a valid recipe.
CAMERA_CONTROLLED_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "recipe" / "film_simulation_eterna.jpg"
)


@pytest.mark.django_db
class TestProcessImagesCommand:
    def test_processes_all_images_in_folder(self, capsys, captured_logs):
        call_command("process_images", str(FIXTURES_DIR))

        assert models.Image.objects.count() == 6

        captured = capsys.readouterr()
        assert "Successfully enqueued 7 tasks." in captured.out

        # Verify task lifecycle events: enqueued, started, completed for each image
        enqueued = [e for e in captured_logs if e.get("event_type") == events.TASK_IMAGE_ENQUEUED]
        started = [e for e in captured_logs if e.get("event_type") == events.TASK_IMAGE_STARTED]
        completed = [e for e in captured_logs if e.get("event_type") == events.TASK_IMAGE_COMPLETED]
        created = [e for e in captured_logs if e.get("event_type") == events.RECIPE_IMAGE_CREATED]

        assert len(enqueued) == 7
        assert len(started) == 7
        assert len(completed) == 6
        assert len(created) == 6


@pytest.mark.django_db
class TestProcessImagesCommandSync:
    def test_processes_images_sequentially(self, capsys):
        with override_settings(USE_ASYNC_TASKS=False):
            call_command("process_images", str(FIXTURES_DIR))

        assert models.Image.objects.count() == 6
        captured = capsys.readouterr()
        assert "Successfully processed 6 of 7 images." in captured.out


@pytest.mark.django_db
class TestProcessImagesCommandSkips:
    def test_reports_skipped_images_without_aborting_the_run(self, capsys, tmp_path):
        shutil.copy(FIXTURES_DIR / "XS107114.JPG", tmp_path / "good.jpg")
        shutil.copy(CAMERA_CONTROLLED_FIXTURE, tmp_path / "camera_controlled.jpg")

        with override_settings(USE_ASYNC_TASKS=False):
            call_command("process_images", str(tmp_path))

        # The valid image is still imported: the unusable one must not abort the run.
        assert models.Image.objects.count() == 1
        captured = capsys.readouterr()
        assert "Successfully processed 1 of 2 images." in captured.out
        assert "Skipped 1 image(s) that cannot produce a recipe." in captured.out
        assert "camera_controlled.jpg" not in captured.out

    def test_lists_skipped_paths_at_higher_verbosity(self, capsys, tmp_path):
        shutil.copy(CAMERA_CONTROLLED_FIXTURE, tmp_path / "camera_controlled.jpg")

        with override_settings(USE_ASYNC_TASKS=False):
            call_command("process_images", str(tmp_path), verbosity=2)

        assert models.Image.objects.count() == 0
        captured = capsys.readouterr()
        assert "skipped: " in captured.out
        assert "camera_controlled.jpg" in captured.out

    def test_publishes_an_import_skipped_event(self, tmp_path, captured_logs):
        shutil.copy(CAMERA_CONTROLLED_FIXTURE, tmp_path / "camera_controlled.jpg")

        with override_settings(USE_ASYNC_TASKS=False):
            call_command("process_images", str(tmp_path))

        skipped = [e for e in captured_logs if e.get("event_type") == events.IMAGE_IMPORT_SKIPPED]
        assert len(skipped) == 1
        assert skipped[0]["reason"] == events.SKIP_REASON_INVALID_RECIPE_DATA
        assert skipped[0]["recipe_field"] == "color"
