import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.data import models
from src.domain.images import events
from src.domain.images.queries import NoFilmSimulationError
from src.domain.recipes.operations import get_or_create_recipe_from_filepath

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "images"
FIXTURE_IMAGE = str(FIXTURES_DIR / "XS107114.JPG")

NON_FUJIFILM_EXIFTOOL_OUTPUT = "[IFD0]          Make                            : Canon\n"

NO_FILM_MODE_EXIFTOOL_OUTPUT = """\
[IFD0]          Make                            : FUJIFILM
[IFD0]          Camera Model Name               : X-S10
[ExifIFD]       ISO                             : 640
[Composite]     Date/Time Original              : 2025:12:31 12:23:57+11:00
"""


@pytest.mark.django_db
class TestGetOrCreateRecipeFromFilepath:
    def test_creates_recipe_from_fixture_image(self):
        recipe = get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)

        assert isinstance(recipe, models.FujifilmRecipe)
        assert recipe.pk is not None
        assert recipe.film_simulation == "Classic Negative"

    def test_publishes_recipe_created_event(self, captured_logs):
        recipe = get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert len(created_events) == 1
        assert created_events[0]["recipe_id"] == recipe.pk
        assert created_events[0]["film_simulation"] == recipe.film_simulation

    def test_does_not_publish_event_when_recipe_already_exists(self, captured_logs):
        get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)
        captured_logs.clear()
        get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert created_events == []

    def test_returns_existing_recipe_when_called_twice(self):
        first = get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)
        second = get_or_create_recipe_from_filepath(filepath=FIXTURE_IMAGE)

        assert first.pk == second.pk

    def test_raises_for_non_fujifilm_image(self, tmp_path):
        image_path = str(tmp_path / "canon.jpg")
        (tmp_path / "canon.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        with patch("src.domain.images.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=NON_FUJIFILM_EXIFTOOL_OUTPUT,
                stderr="",
            )
            with pytest.raises(NoFilmSimulationError):
                get_or_create_recipe_from_filepath(filepath=image_path)

    def test_raises_for_missing_film_simulation(self, tmp_path):
        image_path = str(tmp_path / "no_film_mode.jpg")
        (tmp_path / "no_film_mode.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        with patch("src.domain.images.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=NO_FILM_MODE_EXIFTOOL_OUTPUT,
                stderr="",
            )
            with pytest.raises(NoFilmSimulationError):
                get_or_create_recipe_from_filepath(filepath=image_path)
