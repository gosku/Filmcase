from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

from src.data import models
from src.domain.images import events

FIXTURES_DIR = str(Path(__file__).resolve().parent.parent / "fixtures" / "images")


@pytest.mark.django_db
class TestProcessImagesCommand:
    def test_processes_all_images_in_folder(self, capsys, captured_logs):
        call_command("process_images", FIXTURES_DIR)

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
            call_command("process_images", FIXTURES_DIR)

        assert models.Image.objects.count() == 6
        captured = capsys.readouterr()
        assert "Successfully processed 7 images." in captured.out
