"""
Unit tests for src.domain.operations.

These tests mock exiftool and verify that process_image correctly stores
all FujiFilm EXIF fields into the database.
"""
import subprocess
from unittest.mock import patch

import pytest

from src.data import models
from src.domain.images.operations import NoFilmSimulationError, process_image

# Complete exiftool output covering every field mapped in EXIFTOOL_FIELD_MAP,
# including all 45 new FujiFilm EXIF fields.
ALL_FIELDS_EXIFTOOL_OUTPUT = """\
[IFD0]          Make                            : FUJIFILM
[IFD0]          Camera Model Name               : X-S10
[FujiFilm]      Version                         : 0130
[FujiFilm]      Internal Serial Number          : FF02B6275695     Y56201 2020:12:02 C6B310316B40
[FujiFilm]      Film Mode                       : Classic Negative
[FujiFilm]      Quality                         : FINE
[FujiFilm]      Dynamic Range                   : Standard
[FujiFilm]      Dynamic Range Setting           : Manual
[FujiFilm]      Development Dynamic Range       : 400
[FujiFilm]      White Balance                   : Kelvin
[FujiFilm]      White Balance Fine Tune         : Red +60, Blue -100
[FujiFilm]      Color Temperature               : 6050
[FujiFilm]      Highlight Tone                  : 0 (normal)
[FujiFilm]      Shadow Tone                     : +1 (medium hard)
[FujiFilm]      Saturation                      : +4 (highest)
[FujiFilm]      Sharpness                       : -1 (medium soft)
[FujiFilm]      Noise Reduction                 : -4 (weakest)
[FujiFilm]      Clarity                         : 0
[FujiFilm]      Color Chrome Effect             : Off
[FujiFilm]      Color Chrome FX Blue            : Strong
[FujiFilm]      Grain Effect Roughness          : Off
[FujiFilm]      Grain Effect Size               : Off
[FujiFilm]      BW Adjustment                   : 0
[FujiFilm]      BW Magenta Green                : 0
[FujiFilm]      D Range Priority                : Fixed
[FujiFilm]      D Range Priority Auto           : Strong
[FujiFilm]      Auto Dynamic Range              : 200%
[FujiFilm]      AF Mode                         : Zone
[FujiFilm]      Focus Pixel                     : 3557 1645
[FujiFilm]      AF-S Priority                   : Release
[FujiFilm]      AF-C Priority                   : Release
[FujiFilm]      Focus Mode 2                    : AF-S
[FujiFilm]      Pre AF                          : Off
[FujiFilm]      AF Area Mode                    : Zone
[FujiFilm]      AF Area Point Size              : n/a
[FujiFilm]      AF Area Zone Size               : 3 x 3
[FujiFilm]      AF-C Setting                    : Set 6 (custom 0x112)
[FujiFilm]      AF-C Tracking Sensitivity       : 2
[FujiFilm]      AF-C Speed Tracking Sensitivity : 1
[FujiFilm]      AF-C Zone Area Switching        : Auto
[FujiFilm]      Fuji Flash Mode                 : Not Attached
[FujiFilm]      Flash Exposure Comp             : 0
[FujiFilm]      Focus Mode                      : Auto
[FujiFilm]      Shutter Type                    : Mechanical
[FujiFilm]      Lens Modulation Optimizer       : On
[FujiFilm]      Picture Mode                    : Aperture-priority AE
[FujiFilm]      Drive Mode                      : Single
[FujiFilm]      Image Stabilization             : Sensor-shift; On (mode 1, continuous); 0
[FujiFilm]      Slow Sync                       : Off
[FujiFilm]      Auto Bracketing                 : Off
[FujiFilm]      Drive Speed                     : n/a
[FujiFilm]      Crop Mode                       : n/a
[FujiFilm]      Flicker Reduction               : Off (0x0030)
[FujiFilm]      Sequence Number                 : 0
[FujiFilm]      Exposure Count                  : 1
[FujiFilm]      Image Generation                : Original Image
[FujiFilm]      Image Count                     : 16074
[FujiFilm]      Scene Recognition               : Backlit Portrait
[FujiFilm]      Blur Warning                    : None
[FujiFilm]      Focus Warning                   : Good
[FujiFilm]      Exposure Warning                : Good
[FujiFilm]      Min Focal Length                : 16
[FujiFilm]      Max Focal Length                : 80
[FujiFilm]      Max Aperture At Min Focal       : 4
[FujiFilm]      Max Aperture At Max Focal       : 4
[FujiFilm]      Fuji Model                      : X-S10_0100
[FujiFilm]      Fuji Model 2                    : X-S10_0100
[FujiFilm]      Faces Detected                  : 1
[FujiFilm]      Num Face Elements               : 1
[FujiFilm]      Face Element Positions          : 1176 1165 3067 3057
[FujiFilm]      Face Element Selected           : 1504 1461 1881 1838
[FujiFilm]      Face Element Types              : Face
[FujiFilm]      Face Positions                  : 1176 1165 3067 3057
[ExifIFD]       ISO                             : 640
[ExifIFD]       Exposure Compensation           : +0.33
[Composite]     Date/Time Original              : 2025:12:31 12:23:57+11:00
"""


@pytest.mark.django_db
class TestProcessImageAllFields:
    """Verify that process_image stores every FujiFilm EXIF field in the database."""

    def _run(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")
        (tmp_path / "test.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        with patch("src.domain.images.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=ALL_FIELDS_EXIFTOOL_OUTPUT,
                stderr="",
            )
            return process_image(image_path=image_path)

    def test_image_standard_fields_stored(self, tmp_path):
        image = self._run(tmp_path)

        assert image.camera_make == "FUJIFILM"
        assert image.camera_model == "X-S10"
        assert image.iso == "640"
        assert image.exposure_compensation == "+0.33"

    def test_image_shooting_fields_stored(self, tmp_path):
        image = self._run(tmp_path)

        assert image.quality == "FINE"
        assert image.flash_mode == "Not Attached"
        assert image.flash_exposure_comp == "0"
        assert image.focus_mode == "Auto"
        assert image.shutter_type == "Mechanical"
        assert image.lens_modulation_optimizer == "On"
        assert image.picture_mode == "Aperture-priority AE"
        assert image.drive_mode == "Single"
        assert image.image_stabilization == "Sensor-shift; On (mode 1, continuous); 0"

    def test_fujifilmexif_creative_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.film_simulation == "Classic Negative"
        assert exif.dynamic_range == "Standard"
        assert exif.dynamic_range_setting == "Manual"
        assert exif.development_dynamic_range == "400"
        assert exif.white_balance == "Kelvin"
        assert exif.white_balance_fine_tune == "Red +3, Blue -5"
        assert exif.color_temperature == "6050"
        assert exif.highlight_tone == "0 (normal)"
        assert exif.shadow_tone == "+1 (medium hard)"
        assert exif.color == "+4 (highest)"
        assert exif.sharpness == "-1 (medium soft)"
        assert exif.noise_reduction == "-4 (weakest)"
        assert exif.clarity == "0"
        assert exif.color_chrome_effect == "Off"
        assert exif.color_chrome_fx_blue == "Strong"
        assert exif.grain_effect_roughness == "Off"
        assert exif.grain_effect_size == "Off"
        assert exif.bw_adjustment == "0"
        assert exif.bw_magenta_green == "0"
        assert exif.d_range_priority == "Fixed"
        assert exif.d_range_priority_auto == "Strong"
        assert exif.auto_dynamic_range == "200%"

    def test_fujifilmexif_autofocus_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.af_mode == "Zone"
        assert exif.focus_pixel == "3557 1645"
        assert exif.af_s_priority == "Release"
        assert exif.af_c_priority == "Release"
        assert exif.focus_mode_2 == "AF-S"
        assert exif.pre_af == "Off"
        assert exif.af_area_mode == "Zone"
        assert exif.af_area_point_size == "n/a"
        assert exif.af_area_zone_size == "3 x 3"
        assert exif.af_c_setting == "Set 6 (custom 0x112)"
        assert exif.af_c_tracking_sensitivity == "2"
        assert exif.af_c_speed_tracking_sensitivity == "1"
        assert exif.af_c_zone_area_switching == "Auto"

    def test_fujifilmexif_drive_and_misc_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.slow_sync == "Off"
        assert exif.auto_bracketing == "Off"
        assert exif.drive_speed == "n/a"
        assert exif.crop_mode == "n/a"
        assert exif.flicker_reduction == "Off (0x0030)"

    def test_fujifilmexif_shot_metadata_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.sequence_number == "0"
        assert exif.exposure_count == "1"
        assert exif.image_generation == "Original Image"
        assert exif.image_count == "16074"
        assert exif.scene_recognition == "Backlit Portrait"

    def test_fujifilmexif_warning_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.blur_warning == "None"
        assert exif.focus_warning == "Good"
        assert exif.exposure_warning == "Good"

    def test_fujifilmexif_lens_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.min_focal_length == "16"
        assert exif.max_focal_length == "80"
        assert exif.max_aperture_at_min_focal == "4"
        assert exif.max_aperture_at_max_focal == "4"

    def test_fujifilmexif_hardware_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.version == "0130"
        assert exif.internal_serial_number == "FF02B6275695     Y56201 2020:12:02 C6B310316B40"
        assert exif.fuji_model == "X-S10_0100"
        assert exif.fuji_model_2 == "X-S10_0100"

    def test_fujifilmexif_face_detection_fields_stored(self, tmp_path):
        image = self._run(tmp_path)
        exif = image.fujifilm_exif

        assert exif.faces_detected == "1"
        assert exif.num_face_elements == "1"
        assert exif.face_element_positions == "1176 1165 3067 3057"
        assert exif.face_element_selected == "1504 1461 1881 1838"
        assert exif.face_element_types == "Face"
        assert exif.face_positions == "1176 1165 3067 3057"

    def test_fujifilmexif_persisted_to_database(self, tmp_path):
        image = self._run(tmp_path)

        exif_from_db = models.FujifilmExif.objects.get(pk=image.fujifilm_exif.pk)
        assert exif_from_db.film_simulation == "Classic Negative"
        assert exif_from_db.af_mode == "Zone"
        assert exif_from_db.faces_detected == "1"
        assert exif_from_db.version == "0130"
        assert exif_from_db.blur_warning == "None"
        assert exif_from_db.min_focal_length == "16"
        assert exif_from_db.scene_recognition == "Backlit Portrait"

    def test_raises_for_non_fujifilm_image(self, tmp_path):
        image_path = str(tmp_path / "canon.jpg")
        (tmp_path / "canon.jpg").write_bytes(b"\xff\xd8\xff\xd9")

        non_fuji_output = "[IFD0]          Make                            : Canon\n"

        with patch("src.domain.images.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=non_fuji_output,
                stderr="",
            )
            with pytest.raises(NoFilmSimulationError):
                process_image(image_path=image_path)
