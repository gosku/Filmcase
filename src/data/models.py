from django.core.exceptions import ValidationError
from django.db import models

from src.domain.images import dataclasses as image_dataclasses


def _validate_recipe_name(value):
    if value and (len(value) > image_dataclasses.RECIPE_NAME_MAX_LEN or not value.isascii()):
        raise ValidationError(
            f"Recipe name must be ≤{image_dataclasses.RECIPE_NAME_MAX_LEN} ASCII characters."
        )

RECIPE_FIELDS = (
    "film_simulation",
    "dynamic_range",
    "dynamic_range_setting",
    "development_dynamic_range",
    "white_balance",
    "white_balance_fine_tune",
    "color_temperature",
    "highlight_tone",
    "shadow_tone",
    "color",
    "sharpness",
    "noise_reduction",
    "clarity",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "grain_effect_roughness",
    "grain_effect_size",
    # New FujiFilm EXIF fields
    "version",
    "internal_serial_number",
    "af_mode",
    "focus_pixel",
    "af_s_priority",
    "af_c_priority",
    "focus_mode_2",
    "pre_af",
    "af_area_mode",
    "af_area_point_size",
    "af_area_zone_size",
    "af_c_setting",
    "af_c_tracking_sensitivity",
    "af_c_speed_tracking_sensitivity",
    "af_c_zone_area_switching",
    "slow_sync",
    "exposure_count",
    "crop_mode",
    "auto_bracketing",
    "sequence_number",
    "drive_speed",
    "blur_warning",
    "focus_warning",
    "exposure_warning",
    "auto_dynamic_range",
    "d_range_priority",
    "d_range_priority_auto",
    "min_focal_length",
    "max_focal_length",
    "max_aperture_at_min_focal",
    "max_aperture_at_max_focal",
    "image_generation",
    "image_count",
    "flicker_reduction",
    "fuji_model",
    "fuji_model_2",
    "faces_detected",
    "num_face_elements",
    "face_element_positions",
    "face_element_selected",
    "face_element_types",
    "face_positions",
    "scene_recognition",
    "bw_adjustment",
    "bw_magenta_green",
)


class FujifilmExif(models.Model):
    name = models.CharField(max_length=image_dataclasses.RECIPE_NAME_MAX_LEN, blank=True, default="", validators=[_validate_recipe_name])

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

    # Factories

    @classmethod
    def get_or_create(cls, **fields) -> "FujifilmExif":
        obj, _ = cls.objects.get_or_create(**fields)  # type: ignore[attr-defined]
        return obj

    @classmethod
    def create(cls, **fields) -> "FujifilmExif":
        return cls.objects.create(**fields)  # type: ignore[attr-defined]

    # Properties

    def __str__(self):
        label = self.name or self.film_simulation or "Unknown"
        return f"#{self.id} {label}"  # type: ignore[attr-defined]


class FujifilmRecipe(models.Model):
    name = models.CharField(max_length=image_dataclasses.RECIPE_NAME_MAX_LEN, blank=True, default="", validators=[_validate_recipe_name])
    film_simulation = models.CharField(max_length=100)
    dynamic_range = models.CharField(max_length=100)
    d_range_priority = models.CharField(max_length=50, default="Off")
    grain_roughness = models.CharField(max_length=100)
    grain_size = models.CharField(max_length=100)
    color_chrome_effect = models.CharField(max_length=100)
    color_chrome_fx_blue = models.CharField(max_length=100)
    white_balance = models.CharField(max_length=100)
    white_balance_red = models.IntegerField()
    white_balance_blue = models.IntegerField()
    highlight = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    shadow = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    color = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    sharpness = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    high_iso_nr = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    clarity = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    monochromatic_color_warm_cool = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    monochromatic_color_magenta_green = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "film_simulation", "dynamic_range", "d_range_priority",
                    "grain_roughness", "grain_size", "color_chrome_effect",
                    "color_chrome_fx_blue", "white_balance", "white_balance_red",
                    "white_balance_blue", "highlight", "shadow", "color",
                    "sharpness", "high_iso_nr", "clarity",
                    "monochromatic_color_warm_cool", "monochromatic_color_magenta_green",
                ],
                name="unique_fujifilm_recipe",
                nulls_distinct=False,
            )
        ]

    # Factories

    @classmethod
    def get_or_create(cls, **fields) -> "FujifilmRecipe":
        obj, _ = cls.objects.get_or_create(**fields)  # type: ignore[attr-defined]
        return obj

    # Properties

    def __str__(self):
        return f"#{self.id} {self.name}"  # type: ignore[attr-defined]


class ImageQuerySet(models.QuerySet):
    def without_recipe(self) -> "ImageQuerySet":
        return self.filter(fujifilm_recipe__isnull=True)

    def with_kelvin_white_balance(self) -> "ImageQuerySet":
        return self.filter(fujifilm_exif__white_balance="Kelvin")


class Image(models.Model):
    objects = models.Manager.from_queryset(ImageQuerySet)()
    filename = models.CharField(max_length=255)
    filepath = models.CharField(max_length=1024, unique=True)

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

    created_at = models.DateTimeField(auto_now_add=True)

    fujifilm_exif = models.ForeignKey(
        FujifilmExif,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="images",
    )
    fujifilm_recipe = models.ForeignKey(
        FujifilmRecipe,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="images",
    )

    is_favorite = models.BooleanField(default=False)
    in_album = models.BooleanField(default=False)

    # Factories

    @classmethod
    def create(cls, **fields) -> "Image":
        return cls.objects.create(**fields)

    @classmethod
    def update_or_create(cls, *, filepath: str, **defaults) -> tuple["Image", bool]:
        return cls.objects.update_or_create(filepath=filepath, defaults=defaults)

    # Mutators

    def set_as_favorite(self):
        self.is_favorite = True
        self.save()

    def set_as_in_album(self):
        self.in_album = True
        self.save()

    # Properties

    def __str__(self):
        return f"#{self.id} {self.filename}"  # type: ignore[attr-defined]
