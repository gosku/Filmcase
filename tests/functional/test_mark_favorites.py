import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from src.data.models import Image
from src.domain.images import operations

FIXTURES_DIR = str(Path(__file__).resolve().parent.parent / "fixtures" / "images")


@pytest.mark.django_db
class TestRateImagesCommand:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_rates_matching_images_in_folder(self, capsys):
        call_command("process_images_sync", FIXTURES_DIR)
        total = Image.objects.count()
        assert total > 0

        call_command("rate_images", FIXTURES_DIR, "--rating=3")

        assert Image.objects.filter(rating=3).count() == total

    @override_settings(IMAGE_MAX_RATING=5)
    def test_skips_unimported_image_that_is_not_in_db(self, tmp_path, capsys):
        fixture_image = Path(FIXTURES_DIR) / "XS107114.JPG"
        shutil.copy(fixture_image, tmp_path / fixture_image.name)

        call_command("rate_images", str(tmp_path), "--rating=3")

        captured = capsys.readouterr()
        assert "Skipped" in captured.err
        assert "unable to rate image" in captured.err
        assert Image.objects.count() == 0

    @override_settings(IMAGE_MAX_RATING=5)
    def test_skips_image_that_cannot_be_rated(self, tmp_path, capsys):
        fixture_image = Path(FIXTURES_DIR) / "XS107114.JPG"
        shutil.copy(fixture_image, tmp_path / fixture_image.name)

        with patch("src.application.usecases.images.rate_images.operations.rate_image", side_effect=operations.UnableToRateImage("dummy")):
            call_command("rate_images", str(tmp_path), "--rating=3")

        captured = capsys.readouterr()
        assert "Skipped" in captured.err
        assert "unable to rate image" in captured.err
        assert Image.objects.count() == 0

    @override_settings(IMAGE_MAX_RATING=5)
    def test_does_not_affect_other_images(self, capsys):
        call_command("process_images_sync", FIXTURES_DIR)

        fixture_image = Path(FIXTURES_DIR) / "XS107114.JPG"

        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(fixture_image, Path(tmp) / fixture_image.name)
            call_command("rate_images", tmp, "--rating=3")

        rated = Image.objects.filter(rating=3)
        unrated = Image.objects.filter(rating=0)
        assert rated.count() == 1
        assert rated.first().filename == "XS107114.JPG"
        assert unrated.count() == Image.objects.count() - 1
