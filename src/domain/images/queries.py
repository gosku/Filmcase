import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist

from src.data.models import Image
from src.domain.images.dataclasses import FujifilmRecipeData, ImageExifData
from src.domain.images import recipe_values

class ImageNotFound(Exception):
    """Raised when no DB record matches the given image file."""


class AmbiguousImageMatch(Exception):
    """Raised when multiple DB records match the given image file."""


EXIFTOOL_FIELD_MAP = {
    # Standard fields (non-FujiFilm group)
    "Make": "camera_make",
    "Camera Model Name": "camera_model",
    "ISO": "iso",
    "Exposure Compensation": "exposure_compensation",
    "Date/Time Original": "date_taken",
    "F Number": "aperture",
    "Exposure Time": "shutter_speed",
    "Focal Length": "focal_length",

    # Shooting settings (FujiFilm group, stored on Image)
    "Quality": "quality",
    "Fuji Flash Mode": "flash_mode",
    "Flash Exposure Comp": "flash_exposure_comp",
    "Focus Mode": "focus_mode",
    "Shutter Type": "shutter_type",
    "Lens Modulation Optimizer": "lens_modulation_optimizer",
    "Picture Mode": "picture_mode",
    "Drive Mode": "drive_mode",
    "Image Stabilization": "image_stabilization",

    # Creative / recipe settings (FujiFilm group, stored on FujifilmExif)
    "Film Mode": "film_simulation",
    "Dynamic Range": "dynamic_range",
    "Dynamic Range Setting": "dynamic_range_setting",
    "Development Dynamic Range": "development_dynamic_range",
    "White Balance": "white_balance",
    "White Balance Fine Tune": "white_balance_fine_tune",
    "Color Temperature": "color_temperature",
    "Highlight Tone": "highlight_tone",
    "Shadow Tone": "shadow_tone",
    "Saturation": "color",
    "Sharpness": "sharpness",
    "Noise Reduction": "noise_reduction",
    "Clarity": "clarity",
    "Color Chrome Effect": "color_chrome_effect",
    "Color Chrome FX Blue": "color_chrome_fx_blue",
    "Grain Effect Roughness": "grain_effect_roughness",
    "Grain Effect Size": "grain_effect_size",
    "BW Adjustment": "bw_adjustment",
    "BW Magenta Green": "bw_magenta_green",
    "D Range Priority": "d_range_priority",
    "D Range Priority Auto": "d_range_priority_auto",
    "Auto Dynamic Range": "auto_dynamic_range",

    # Autofocus settings (FujiFilm group, stored on FujifilmExif)
    "AF Mode": "af_mode",
    "Focus Pixel": "focus_pixel",
    "AF-S Priority": "af_s_priority",
    "AF-C Priority": "af_c_priority",
    "Focus Mode 2": "focus_mode_2",
    "Pre AF": "pre_af",
    "AF Area Mode": "af_area_mode",
    "AF Area Point Size": "af_area_point_size",
    "AF Area Zone Size": "af_area_zone_size",
    "AF-C Setting": "af_c_setting",
    "AF-C Tracking Sensitivity": "af_c_tracking_sensitivity",
    "AF-C Speed Tracking Sensitivity": "af_c_speed_tracking_sensitivity",
    "AF-C Zone Area Switching": "af_c_zone_area_switching",

    # Drive / flash / stabilization (FujiFilm group, stored on FujifilmExif)
    "Slow Sync": "slow_sync",
    "Auto Bracketing": "auto_bracketing",
    "Drive Speed": "drive_speed",
    "Crop Mode": "crop_mode",
    "Flicker Reduction": "flicker_reduction",

    # Shot metadata (FujiFilm group, stored on FujifilmExif)
    "Sequence Number": "sequence_number",
    "Exposure Count": "exposure_count",
    "Image Generation": "image_generation",
    "Image Count": "image_count",
    "Scene Recognition": "scene_recognition",

    # Warnings / status (FujiFilm group, stored on FujifilmExif)
    "Blur Warning": "blur_warning",
    "Focus Warning": "focus_warning",
    "Exposure Warning": "exposure_warning",

    # Lens info (FujiFilm group, stored on FujifilmExif)
    "Min Focal Length": "min_focal_length",
    "Max Focal Length": "max_focal_length",
    "Max Aperture At Min Focal": "max_aperture_at_min_focal",
    "Max Aperture At Max Focal": "max_aperture_at_max_focal",

    # Camera hardware info (FujiFilm group, stored on FujifilmExif)
    "Version": "version",
    "Internal Serial Number": "internal_serial_number",
    "Fuji Model": "fuji_model",
    "Fuji Model 2": "fuji_model_2",

    # Face detection (FujiFilm group, stored on FujifilmExif)
    "Faces Detected": "faces_detected",
    "Num Face Elements": "num_face_elements",
    "Face Element Positions": "face_element_positions",
    "Face Element Selected": "face_element_selected",
    "Face Element Types": "face_element_types",
    "Face Positions": "face_positions",
}

_EXIF_DATE_RE = re.compile(
    r"^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:([+-]\d{2}:\d{2}))?$"
)

_WB_FINE_TUNE_RE = re.compile(r"(Red|Blue)\s+([+-]?\d+)")

# Regex to strip the [Group] prefix added by exiftool -G1
# Group names can contain hyphens (e.g. XMP-crs), so use [^\]] instead of \w+.
_G1_PREFIX_RE = re.compile(r"^\[([^\]]+)\]\s+")

# When a field appears in multiple groups, use the value from this group.
# Default is FujiFilm; fields listed here override that default.
_DEFAULT_GROUP = "FujiFilm"
_GROUP_OVERRIDES = {
    "date_taken": "Composite",
    "aperture": "ExifIFD",
    "shutter_speed": "ExifIFD",
    "focal_length": "ExifIFD",
}


def parse_exif_date(*, value: str) -> datetime | None:
    """Parse an exiftool date string into a timezone-aware datetime."""
    m = _EXIF_DATE_RE.match(value.strip())
    if not m:
        return None
    year, month, day, hour, minute, second = (int(g) for g in m.groups()[:6])
    tz_str = m.group(7)
    if tz_str:
        sign = 1 if tz_str[0] == "+" else -1
        tz_h, tz_m = tz_str[1:].split(":")
        tz = timezone(timedelta(hours=sign * int(tz_h), minutes=sign * int(tz_m)))
    else:
        tz = timezone.utc
    return datetime(year, month, day, hour, minute, second, tzinfo=tz)


def _normalize_wb_fine_tune(*, raw: str) -> str:
    """Divide exiftool White Balance Fine Tune values by 20 to get camera values."""
    def _divide(m: re.Match) -> str:
        return f"{m.group(1)} {int(m.group(2)) // 20:+d}"
    return _WB_FINE_TUNE_RE.sub(_divide, raw)


def read_image_exif(*, image_path: str) -> ImageExifData:
    """Run exiftool on the given image and return a dict of recipe-relevant fields."""
    result = subprocess.run(
        ["exiftool", "-a", "-G1", image_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"exiftool failed for {image_path}: {result.stderr}")

    # Collect all (group, value) occurrences per field
    all_values: dict[str, list[tuple[str, str]]] = {}
    for line in result.stdout.splitlines():
        m = _G1_PREFIX_RE.match(line)
        if not m:
            continue
        group = m.group(1)
        rest = line[m.end():]
        if ":" not in rest:
            continue
        key, _, val = rest.partition(":")
        key = key.strip()
        val = val.strip()
        if key in EXIFTOOL_FIELD_MAP:
            field = EXIFTOOL_FIELD_MAP[key]
            all_values.setdefault(field, []).append((group, val))

    metadata: dict[str, str] = {}
    for field, occurrences in all_values.items():
        preferred_group = _GROUP_OVERRIDES.get(field, _DEFAULT_GROUP)
        value = next((v for g, v in occurrences if g == preferred_group), occurrences[0][1])
        metadata[field] = value
    if "white_balance_fine_tune" in metadata:
        metadata["white_balance_fine_tune"] = _normalize_wb_fine_tune(
            raw=metadata["white_balance_fine_tune"]
        )
    if "shutter_speed" in metadata:
        metadata["shutter_speed"] = metadata["shutter_speed"] + "s"
    return ImageExifData(**metadata)


def exif_to_recipe(*, exif: ImageExifData) -> FujifilmRecipeData:
    """Convert an ImageExifData instance to a FujifilmRecipeData."""
    film_simulation = recipe_values.film_simulation_from_exif(film_simulation=exif.film_simulation, color=exif.color).display_name
    d_range_priority = recipe_values.d_range_priority_from_exif(d_range_priority=exif.d_range_priority, d_range_priority_auto=exif.d_range_priority_auto)
    dynamic_range = recipe_values.dynamic_range_from_exif(dynamic_range_setting=exif.dynamic_range_setting, development_dynamic_range=exif.development_dynamic_range) if d_range_priority.value == "Off" else ""
    wb_red, wb_blue = recipe_values.white_balance_fine_tune_from_exif(white_balance_fine_tune=exif.white_balance_fine_tune)
    return FujifilmRecipeData(
        film_simulation=film_simulation,
        dynamic_range=dynamic_range,
        d_range_priority=d_range_priority.value,
        grain_roughness=exif.grain_effect_roughness,
        grain_size=exif.grain_effect_size,
        color_chrome_effect=recipe_values.color_chrome_effect_from_exif(value=exif.color_chrome_effect).value,
        color_chrome_fx_blue=recipe_values.color_chrome_fx_blue_from_exif(value=exif.color_chrome_fx_blue).value,
        white_balance=recipe_values.white_balance_from_exif(white_balance=exif.white_balance, color_temperature=exif.color_temperature),
        white_balance_red=wb_red,
        white_balance_blue=wb_blue,
        highlight=recipe_values.highlight_from_exif(highlight_tone=exif.highlight_tone),
        shadow=recipe_values.shadow_from_exif(shadow_tone=exif.shadow_tone),
        color=recipe_values.color_from_exif(color=exif.color),
        sharpness=recipe_values.sharpness_from_exif(sharpness=exif.sharpness),
        high_iso_nr=recipe_values.noise_reduction_from_exif(noise_reduction=exif.noise_reduction),
        clarity=recipe_values.clarity_from_exif(clarity=exif.clarity),
        monochromatic_color_warm_cool=recipe_values.monochromatic_color_from_exif(value=exif.bw_adjustment),
        monochromatic_color_magenta_green=recipe_values.monochromatic_color_from_exif(value=exif.bw_magenta_green),
    )


def _by_filename_and_date(*, exif: ImageExifData, filename: str, date_taken: datetime | None) -> Image:
    return Image.objects.get(filename=filename, taken_at=date_taken)


def _by_date_film_and_wb(*, exif: ImageExifData, filename: str, date_taken: datetime | None) -> Image:
    return Image.objects.get(
        taken_at=date_taken,
        fujifilm_exif__film_simulation=exif.film_simulation,
        fujifilm_exif__white_balance_fine_tune=exif.white_balance_fine_tune,
    )


def _by_date_and_image_count(*, exif: ImageExifData, filename: str, date_taken: datetime | None) -> Image:
    return Image.objects.get(taken_at=date_taken, fujifilm_exif__image_count=exif.image_count)


def _by_date_and_film_simulation(*, exif: ImageExifData, filename: str, date_taken: datetime | None) -> Image:
    return Image.objects.get(taken_at=date_taken, fujifilm_exif__film_simulation=exif.film_simulation)


def _by_date_only(*, exif: ImageExifData, filename: str, date_taken: datetime | None) -> Image:
    return Image.objects.get(taken_at=date_taken)


_LOOKUP_STRATEGIES = [
    _by_filename_and_date,
    _by_date_and_image_count,
    _by_date_film_and_wb,
    # _by_date_and_film_simulation,
    # _by_date_only,
]


def find_image_for_path(*, image_path: str) -> Image:
    """Return the DB Image record that corresponds to the given image file.

    Strategies are tried in order; the first one that returns a unique match
    wins. To add a new strategy, append a function with the signature
    (exif, filename, date_taken) -> Image to _LOOKUP_STRATEGIES.

    Raises ImageNotFound if no strategy finds a match.
    Raises AmbiguousImageMatch if a strategy finds more than one match.
    """
    exif = read_image_exif(image_path=image_path)
    filename = Path(image_path).name
    date_taken = parse_exif_date(value=exif.date_taken) if exif.date_taken else None

    any_ambiguous = False
    for strategy in _LOOKUP_STRATEGIES:
        try:
            return strategy(exif=exif, filename=filename, date_taken=date_taken)
        except ObjectDoesNotExist:
            continue
        except MultipleObjectsReturned:
            any_ambiguous = True
            continue

    if any_ambiguous:
        raise AmbiguousImageMatch(image_path)
    raise ImageNotFound(image_path)


def collect_image_paths(*, folder: str) -> list[str]:
    """Return absolute paths of all JPG files inside *folder* (recursively)."""
    root = Path(folder)
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {folder}")

    extensions = {".jpg", ".jpeg"}
    paths: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            if Path(fname).suffix.lower() in extensions:
                paths.append(os.path.join(dirpath, fname))

    paths.sort()
    return paths
