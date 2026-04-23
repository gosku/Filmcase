from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.data import models
from src.domain.images.operations import process_image

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
SAMPLE_IMAGE = str(FIXTURES_DIR / "XS107508.jpg")


@pytest.mark.django_db
class TestProcessImageEndToEnd:
    """End-to-end tests that run exiftool against a real Fujifilm image."""

    def test_extracts_and_stores_recipe(self):
        image = process_image(image_path=SAMPLE_IMAGE)

        assert image.pk is not None
        assert image.filename == "XS107508.jpg"
        assert image.filepath == SAMPLE_IMAGE

        # Camera
        assert image.camera_make == "FUJIFILM"
        assert image.camera_model == "X-S10"

        # Shooting settings
        assert image.quality == "FINE"
        assert image.flash_mode == "Not Attached"
        assert image.flash_exposure_comp == "0"
        assert image.focus_mode == "Auto"
        assert image.shutter_type == "Mechanical"
        assert image.lens_modulation_optimizer == "On"
        assert image.picture_mode == "Aperture-priority AE"
        assert image.drive_mode == "Single"

        # Exposure
        assert image.iso == "1600"
        assert image.exposure_compensation == "+0.33"

        # Date
        assert image.taken_at == datetime(2026, 3, 9, 9, 29, 32, tzinfo=timezone(timedelta(hours=11)))

        # Recipe
        assert image.fujifilm_exif is not None
        assert image.fujifilm_exif.film_simulation == "Classic Negative"
        assert image.fujifilm_exif.dynamic_range == "Standard"
        assert image.fujifilm_exif.dynamic_range_setting == "Manual"
        assert image.fujifilm_exif.development_dynamic_range == "400"
        assert image.fujifilm_exif.white_balance == "Auto"
        assert image.fujifilm_exif.white_balance_fine_tune == "Red +3, Blue -5"
        assert image.fujifilm_exif.highlight_tone == "0 (normal)"
        assert image.fujifilm_exif.shadow_tone == "+1 (medium hard)"
        assert image.fujifilm_exif.color == "+4 (highest)"
        assert image.fujifilm_exif.sharpness == "-1 (medium soft)"
        assert image.fujifilm_exif.noise_reduction == "-4 (weakest)"
        assert image.fujifilm_exif.clarity == "0"
        assert image.fujifilm_exif.color_chrome_effect == "Off"
        assert image.fujifilm_exif.color_chrome_fx_blue == "Strong"
        assert image.fujifilm_exif.grain_effect_roughness == "Off"
        assert image.fujifilm_exif.grain_effect_size == "Off"

    def test_is_idempotent(self):
        image1 = process_image(image_path=SAMPLE_IMAGE)
        image2 = process_image(image_path=SAMPLE_IMAGE)

        assert image1.pk == image2.pk
        assert models.Image.objects.filter(filepath=SAMPLE_IMAGE).count() == 1

    def test_persists_to_database(self):
        process_image(image_path=SAMPLE_IMAGE)

        from_db = models.Image.objects.get(filepath=SAMPLE_IMAGE)
        assert from_db.fujifilm_exif.film_simulation == "Classic Negative"
        assert from_db.camera_make == "FUJIFILM"
