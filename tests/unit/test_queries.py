import os
import subprocess
from unittest.mock import patch

import pytest

from src.domain.queries import _normalize_wb_fine_tune, collect_image_paths, read_image_exif

SAMPLE_EXIFTOOL_OUTPUT = """\
[ExifTool]      ExifTool Version Number         : 12.76
[File]          File Name                       : XS107114.JPG
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
[ExifIFD]       Sharpness                       : Soft
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
[FujiFilm]      Auto Dynamic Range              : 100%
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
[ExifIFD]       Date/Time Original              : 2025:12:31 12:23:57
[Composite]     Date/Time Original              : 2025:12:31 12:23:57+11:00
"""


class TestReadImageExif:
    def test_parses_relevant_fields(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")

        with patch("src.domain.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=SAMPLE_EXIFTOOL_OUTPUT,
                stderr="",
            )
            metadata = read_image_exif(image_path)

        # Standard fields
        assert metadata.camera_make == "FUJIFILM"
        assert metadata.iso == "640"
        assert metadata.exposure_compensation == "+0.33"

        # Shooting settings
        assert metadata.quality == "FINE"
        assert metadata.flash_mode == "Not Attached"
        assert metadata.flash_exposure_comp == "0"
        assert metadata.focus_mode == "Auto"
        assert metadata.shutter_type == "Mechanical"
        assert metadata.lens_modulation_optimizer == "On"
        assert metadata.picture_mode == "Aperture-priority AE"
        assert metadata.drive_mode == "Single"
        assert metadata.image_stabilization == "Sensor-shift; On (mode 1, continuous); 0"

        # Creative / recipe
        assert metadata.film_simulation == "Classic Negative"
        assert metadata.dynamic_range == "Standard"
        assert metadata.dynamic_range_setting == "Manual"
        assert metadata.development_dynamic_range == "400"
        assert metadata.white_balance == "Kelvin"
        assert metadata.white_balance_fine_tune == "Red +3, Blue -5"
        assert metadata.color_temperature == "6050"
        assert metadata.highlight_tone == "0 (normal)"
        assert metadata.shadow_tone == "+1 (medium hard)"
        assert metadata.color == "+4 (highest)"
        assert metadata.sharpness == "-1 (medium soft)"
        assert metadata.noise_reduction == "-4 (weakest)"
        assert metadata.clarity == "0"
        assert metadata.color_chrome_effect == "Off"
        assert metadata.color_chrome_fx_blue == "Strong"
        assert metadata.grain_effect_roughness == "Off"
        assert metadata.grain_effect_size == "Off"
        assert metadata.bw_adjustment == "0"
        assert metadata.bw_magenta_green == "0"
        assert metadata.d_range_priority == "Fixed"
        assert metadata.d_range_priority_auto == "Strong"
        assert metadata.auto_dynamic_range == "100%"

        # Autofocus
        assert metadata.af_mode == "Zone"
        assert metadata.focus_pixel == "3557 1645"
        assert metadata.af_s_priority == "Release"
        assert metadata.af_c_priority == "Release"
        assert metadata.focus_mode_2 == "AF-S"
        assert metadata.pre_af == "Off"
        assert metadata.af_area_mode == "Zone"
        assert metadata.af_area_point_size == "n/a"
        assert metadata.af_area_zone_size == "3 x 3"
        assert metadata.af_c_setting == "Set 6 (custom 0x112)"
        assert metadata.af_c_tracking_sensitivity == "2"
        assert metadata.af_c_speed_tracking_sensitivity == "1"
        assert metadata.af_c_zone_area_switching == "Auto"

        # Drive / misc
        assert metadata.slow_sync == "Off"
        assert metadata.auto_bracketing == "Off"
        assert metadata.drive_speed == "n/a"
        assert metadata.crop_mode == "n/a"
        assert metadata.flicker_reduction == "Off (0x0030)"

        # Shot metadata
        assert metadata.sequence_number == "0"
        assert metadata.exposure_count == "1"
        assert metadata.image_generation == "Original Image"
        assert metadata.image_count == "16074"
        assert metadata.scene_recognition == "Backlit Portrait"

        # Warnings
        assert metadata.blur_warning == "None"
        assert metadata.focus_warning == "Good"
        assert metadata.exposure_warning == "Good"

        # Lens info
        assert metadata.min_focal_length == "16"
        assert metadata.max_focal_length == "80"
        assert metadata.max_aperture_at_min_focal == "4"
        assert metadata.max_aperture_at_max_focal == "4"

        # Camera hardware
        assert metadata.version == "0130"
        assert metadata.internal_serial_number == "FF02B6275695     Y56201 2020:12:02 C6B310316B40"
        assert metadata.fuji_model == "X-S10_0100"
        assert metadata.fuji_model_2 == "X-S10_0100"

        # Face detection
        assert metadata.faces_detected == "1"
        assert metadata.num_face_elements == "1"
        assert metadata.face_element_positions == "1176 1165 3067 3057"
        assert metadata.face_element_selected == "1504 1461 1881 1838"
        assert metadata.face_element_types == "Face"
        assert metadata.face_positions == "1176 1165 3067 3057"

    def test_prefers_fujifilm_group_for_sharpness(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")

        with patch("src.domain.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=SAMPLE_EXIFTOOL_OUTPUT,
                stderr="",
            )
            metadata = read_image_exif(image_path)

        # ExifIFD has "Soft" but FujiFilm group should win
        assert metadata.sharpness == "-1 (medium soft)"

    def test_prefers_composite_group_for_date_taken(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")

        with patch("src.domain.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout=SAMPLE_EXIFTOOL_OUTPUT,
                stderr="",
            )
            metadata = read_image_exif(image_path)

        # ExifIFD has no timezone but Composite has +11:00 — Composite should win
        assert metadata.date_taken == "2025:12:31 12:23:57+11:00"

    def test_ignores_irrelevant_fields(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")

        with patch("src.domain.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=0,
                stdout="ExifTool Version Number         : 12.76\nFile Name                       : test.jpg\n",
                stderr="",
            )
            metadata = read_image_exif(image_path)

        assert not hasattr(metadata, "exiftool_version_number")
        assert not hasattr(metadata, "file_name")

    def test_raises_on_exiftool_failure(self, tmp_path):
        image_path = str(tmp_path / "test.jpg")

        with patch("src.domain.queries.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["exiftool", image_path],
                returncode=1,
                stdout="",
                stderr="File not found",
            )
            with pytest.raises(RuntimeError, match="exiftool failed"):
                read_image_exif(image_path)


class TestNormaliseWbFineTune:
    def test_divides_values_by_20(self):
        assert _normalize_wb_fine_tune("Red +60, Blue -100") == "Red +3, Blue -5"

    def test_handles_zero(self):
        assert _normalize_wb_fine_tune("Red +20, Blue +0") == "Red +1, Blue +0"

    def test_handles_negative_red(self):
        assert _normalize_wb_fine_tune("Red -40, Blue +60") == "Red -2, Blue +3"


class TestCollectImagePaths:
    def test_returns_jpg_files(self, tmp_path):
        (tmp_path / "photo1.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "photo2.JPG").write_bytes(b"\xff\xd8")
        (tmp_path / "photo3.jpeg").write_bytes(b"\xff\xd8")
        (tmp_path / "document.pdf").write_bytes(b"%PDF")

        paths = collect_image_paths(str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert "photo1.jpg" in filenames
        assert "photo2.JPG" in filenames
        assert "photo3.jpeg" in filenames
        assert "document.pdf" not in filenames

    def test_returns_sorted_paths(self, tmp_path):
        (tmp_path / "c.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "a.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "b.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert filenames == sorted(filenames)

    def test_finds_files_recursively(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.jpg").write_bytes(b"\xff\xd8")
        (sub / "nested.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert "top.jpg" in filenames
        assert "nested.jpg" in filenames

    def test_returns_absolute_paths(self, tmp_path):
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(str(tmp_path))

        for p in paths:
            assert os.path.isabs(p)

    def test_empty_folder_returns_empty_list(self, tmp_path):
        paths = collect_image_paths(str(tmp_path))
        assert paths == []

    def test_nonexistent_folder_raises(self):
        with pytest.raises(FileNotFoundError):
            collect_image_paths("/nonexistent/folder")
