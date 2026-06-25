from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import models
from django.utils import timezone

from ._recipes import _RECIPE_NAME_MAX_LEN, FujifilmRecipe


class FujifilmExif(models.Model):
    name = models.CharField(max_length=_RECIPE_NAME_MAX_LEN, blank=True, default="")

    # Creative / recipe settings
    film_simulation = models.CharField(max_length=100, blank=True, default="")
    dynamic_range = models.CharField(max_length=100, blank=True, default="")
    dynamic_range_setting = models.CharField(max_length=100, blank=True, default="")
    development_dynamic_range = models.CharField(max_length=50, blank=True, default="")
    white_balance = models.CharField(max_length=100, blank=True, default="")
    white_balance_fine_tune = models.CharField(max_length=200, blank=True, default="")
    color_temperature = models.CharField(max_length=50, blank=True, default="")
    highlight_tone = models.CharField(max_length=100, blank=True, default="")
    shadow_tone = models.CharField(max_length=100, blank=True, default="")
    color = models.CharField(max_length=100, blank=True, default="")
    sharpness = models.CharField(max_length=100, blank=True, default="")
    noise_reduction = models.CharField(max_length=100, blank=True, default="")
    clarity = models.CharField(max_length=100, blank=True, default="")
    color_chrome_effect = models.CharField(max_length=100, blank=True, default="")
    color_chrome_fx_blue = models.CharField(max_length=100, blank=True, default="")
    grain_effect_roughness = models.CharField(max_length=100, blank=True, default="")
    grain_effect_size = models.CharField(max_length=100, blank=True, default="")
    bw_adjustment = models.CharField(max_length=50, blank=True, default="")
    bw_magenta_green = models.CharField(max_length=50, blank=True, default="")
    d_range_priority = models.CharField(max_length=100, blank=True, default="")
    d_range_priority_auto = models.CharField(max_length=100, blank=True, default="")
    auto_dynamic_range = models.CharField(max_length=50, blank=True, default="")

    # Autofocus settings
    af_mode = models.CharField(max_length=100, blank=True, default="")
    focus_pixel = models.CharField(max_length=100, blank=True, default="")
    af_s_priority = models.CharField(max_length=100, blank=True, default="")
    af_c_priority = models.CharField(max_length=100, blank=True, default="")
    focus_mode_2 = models.CharField(max_length=100, blank=True, default="")
    pre_af = models.CharField(max_length=50, blank=True, default="")
    af_area_mode = models.CharField(max_length=100, blank=True, default="")
    af_area_point_size = models.CharField(max_length=50, blank=True, default="")
    af_area_zone_size = models.CharField(max_length=50, blank=True, default="")
    af_c_setting = models.CharField(max_length=100, blank=True, default="")
    af_c_tracking_sensitivity = models.CharField(max_length=50, blank=True, default="")
    af_c_speed_tracking_sensitivity = models.CharField(max_length=50, blank=True, default="")
    af_c_zone_area_switching = models.CharField(max_length=100, blank=True, default="")

    # Drive / flash / stabilization
    slow_sync = models.CharField(max_length=50, blank=True, default="")
    auto_bracketing = models.CharField(max_length=100, blank=True, default="")
    drive_speed = models.CharField(max_length=50, blank=True, default="")
    crop_mode = models.CharField(max_length=50, blank=True, default="")
    flicker_reduction = models.CharField(max_length=100, blank=True, default="")

    # Shot metadata
    sequence_number = models.CharField(max_length=50, blank=True, default="")
    exposure_count = models.CharField(max_length=50, blank=True, default="")
    image_generation = models.CharField(max_length=100, blank=True, default="")
    image_count = models.CharField(max_length=50, blank=True, default="")
    scene_recognition = models.CharField(max_length=100, blank=True, default="")

    # Warnings / status
    blur_warning = models.CharField(max_length=50, blank=True, default="")
    focus_warning = models.CharField(max_length=50, blank=True, default="")
    exposure_warning = models.CharField(max_length=50, blank=True, default="")

    # Lens info
    min_focal_length = models.CharField(max_length=50, blank=True, default="")
    max_focal_length = models.CharField(max_length=50, blank=True, default="")
    max_aperture_at_min_focal = models.CharField(max_length=50, blank=True, default="")
    max_aperture_at_max_focal = models.CharField(max_length=50, blank=True, default="")

    # Camera hardware info
    version = models.CharField(max_length=50, blank=True, default="")
    internal_serial_number = models.CharField(max_length=100, blank=True, default="")
    fuji_model = models.CharField(max_length=100, blank=True, default="")
    fuji_model_2 = models.CharField(max_length=100, blank=True, default="")

    # Face detection
    faces_detected = models.CharField(max_length=50, blank=True, default="")
    num_face_elements = models.CharField(max_length=50, blank=True, default="")
    face_element_positions = models.CharField(max_length=500, blank=True, default="")
    face_element_selected = models.CharField(max_length=500, blank=True, default="")
    face_element_types = models.CharField(max_length=200, blank=True, default="")
    face_positions = models.CharField(max_length=500, blank=True, default="")

    @classmethod
    def get_or_create(cls, **fields: Any) -> "FujifilmExif":
        obj, _ = cls.objects.get_or_create(**fields)
        return obj

    def __str__(self) -> str:
        label = self.name or self.film_simulation or "Unknown"
        return f"#{self.id} {label}"


class ImageQuerySet(models.QuerySet["Image"]):
    def without_recipe(self) -> "ImageQuerySet":
        return self.filter(fujifilm_recipe__isnull=True)

    def with_kelvin_white_balance(self) -> "ImageQuerySet":
        return self.filter(fujifilm_exif__white_balance="Kelvin")


class Image(models.Model):
    objects = models.Manager.from_queryset(ImageQuerySet)()
    filename = models.CharField(max_length=255)
    filepath = models.CharField(max_length=1024)
    content_hash = models.CharField(max_length=64, blank=True, default="")

    # Camera info
    camera_make = models.CharField(max_length=100, blank=True, default="")
    camera_model = models.CharField(max_length=100, blank=True, default="")

    # Shooting settings
    quality = models.CharField(max_length=50, blank=True, default="")
    flash_mode = models.CharField(max_length=100, blank=True, default="")
    flash_exposure_comp = models.CharField(max_length=50, blank=True, default="")
    focus_mode = models.CharField(max_length=100, blank=True, default="")
    shutter_type = models.CharField(max_length=100, blank=True, default="")
    lens_modulation_optimizer = models.CharField(max_length=50, blank=True, default="")
    picture_mode = models.CharField(max_length=100, blank=True, default="")
    drive_mode = models.CharField(max_length=100, blank=True, default="")
    image_stabilization = models.CharField(max_length=200, blank=True, default="")

    # Exposure info
    iso = models.CharField(max_length=50, blank=True, default="")
    exposure_compensation = models.CharField(max_length=50, blank=True, default="")
    aperture = models.CharField(max_length=50, blank=True, default="")
    shutter_speed = models.CharField(max_length=50, blank=True, default="")
    focal_length = models.CharField(max_length=50, blank=True, default="")

    # Date
    taken_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    fujifilm_exif = models.ForeignKey(
        "FujifilmExif",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="images",
    )
    fujifilm_recipe = models.ForeignKey(
        "FujifilmRecipe",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="images",
    )

    is_favorite = models.BooleanField(default=False)
    in_album = models.BooleanField(default=False)
    rating = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["filepath"], name="unique_image_filepath"),
            models.UniqueConstraint(
                fields=["content_hash"],
                condition=~models.Q(content_hash=""),
                name="unique_image_content_hash",
            ),
        ]

    @classmethod
    def create(
        cls,
        *,
        filepath: str,
        filename: str,
        taken_at: datetime | None,
        content_hash: str,
        fujifilm_exif: "FujifilmExif | None",
        fujifilm_recipe: FujifilmRecipe | None,
        **image_fields: object,
    ) -> "Image":
        return cls.objects.create(
            filepath=filepath,
            filename=filename,
            taken_at=taken_at,
            content_hash=content_hash,
            fujifilm_exif=fujifilm_exif,
            fujifilm_recipe=fujifilm_recipe,
            **image_fields,
        )

    def set_content_hash(self, *, content_hash: str) -> None:
        self.content_hash = content_hash
        self.save(update_fields=["content_hash"])

    def set_as_favorite(self) -> None:
        self.is_favorite = True
        self.save(update_fields=["is_favorite"])

    def set_as_in_album(self) -> None:
        self.in_album = True
        self.save(update_fields=["in_album"])

    def set_rating(self, value: int) -> None:
        self.rating = value
        self.save(update_fields=["rating"])

    def __str__(self) -> str:
        return f"#{self.id} {self.filename}"
