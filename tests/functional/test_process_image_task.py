import shutil
from pathlib import Path

import pytest

from src.data import models
from src.domain.images import events
from src.interfaces.tasks import process_image_task

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"
# The camera set this file's Saturation, so its EXIF cannot produce a valid recipe.
CAMERA_CONTROLLED_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "recipe" / "film_simulation_eterna.jpg"
)


def _skip_events(captured_logs):
    return [e for e in captured_logs if e.get("event_type") == events.IMAGE_IMPORT_SKIPPED]


def _run_task(fixture: Path, tmp_path: Path) -> str:
    image_path = tmp_path / fixture.name
    shutil.copy(fixture, image_path)
    return process_image_task.apply(kwargs={"image_path": str(image_path)}).get()


@pytest.mark.django_db
class TestProcessImageTask:
    def test_processes_a_valid_image(self, tmp_path):
        result = _run_task(FUJIFILM_FIXTURE, tmp_path)

        assert "Processed" in result
        assert models.Image.objects.count() == 1

    def test_skips_an_image_whose_recipe_data_is_invalid(self, tmp_path):
        result = _run_task(CAMERA_CONTROLLED_FIXTURE, tmp_path)

        assert "Skipped" in result
        assert "invalid recipe data" in result
        assert models.Image.objects.count() == 0

    def test_skips_an_image_with_no_film_simulation(self, tmp_path):
        result = _run_task(NON_FUJIFILM_FIXTURE, tmp_path)

        assert "Skipped" in result
        assert "no film simulation" in result
        assert models.Image.objects.count() == 0

    def test_publishes_an_import_skipped_event_for_invalid_recipe_data(self, tmp_path, captured_logs):
        _run_task(CAMERA_CONTROLLED_FIXTURE, tmp_path)

        skipped = _skip_events(captured_logs)
        assert len(skipped) == 1
        assert skipped[0]["reason"] == events.SKIP_REASON_INVALID_RECIPE_DATA
        assert skipped[0]["recipe_field"] == "color"

    def test_publishes_an_import_skipped_event_for_no_film_simulation(self, tmp_path, captured_logs):
        _run_task(NON_FUJIFILM_FIXTURE, tmp_path)

        skipped = _skip_events(captured_logs)
        assert len(skipped) == 1
        assert skipped[0]["reason"] == events.SKIP_REASON_NO_FILM_SIMULATION
