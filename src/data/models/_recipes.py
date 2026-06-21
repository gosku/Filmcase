from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from django.db import models
from django.utils import timezone

_RECIPE_NAME_MAX_LEN = 25

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


class Sensor(models.Model):
    """
    A Fujifilm sensor generation a recipe is compatible with.

    Seeded once by migration from :data:`src.data.sensors.SENSOR_NAMES`. The
    table is read-only at the application layer — adding or removing a sensor
    requires a code change to ``SENSOR_NAMES`` and a corresponding migration.
    """

    name = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name"], name="unique_sensor_name"),
        ]

    def __str__(self) -> str:
        return f"#{self.id} {self.name}"


class FujifilmRecipe(models.Model):
    name = models.CharField(max_length=_RECIPE_NAME_MAX_LEN, blank=True, default="")
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

    sensors = models.ManyToManyField(Sensor, related_name="recipes", blank=True)
    # Denormalised canonical join of the linked sensor names. Exists so the
    # unique constraint below can include the sensor set (M2M columns cannot
    # appear in a UniqueConstraint directly). Must stay in lock-step with the
    # ``sensors`` M2M — a follow-up commit introduces the mutator that
    # guarantees this. The empty string is the signature used by recipes with
    # no sensors attached, which keeps the pre-existing settings-only dedup
    # behaviour in place.
    sensor_signature = models.CharField(max_length=255, blank=True, default="")

    description = models.TextField(blank=True, default="")

    cover_image = models.ForeignKey(
        "Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cover_for_recipes",
    )

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
                    "sensor_signature",
                ],
                name="unique_fujifilm_recipe",
                nulls_distinct=False,
            )
        ]

    @classmethod
    def get_or_create(
        cls,
        *,
        film_simulation: str,
        dynamic_range: str,
        d_range_priority: str,
        grain_roughness: str,
        grain_size: str,
        color_chrome_effect: str,
        color_chrome_fx_blue: str,
        white_balance: str,
        white_balance_red: int,
        white_balance_blue: int,
        highlight: object,
        shadow: object,
        color: object,
        sharpness: object,
        high_iso_nr: object,
        clarity: object,
        monochromatic_color_warm_cool: object,
        monochromatic_color_magenta_green: object,
        sensor_signature: str = "",
        name: str = "",
        description: str = "",
    ) -> "tuple[FujifilmRecipe, bool]":
        # name and description are passed via defaults= so they only apply on
        # the create path; matching an existing recipe keeps that recipe's
        # current values for both fields. sensor_signature participates in
        # the lookup because it's part of the recipe's UniqueConstraint --
        # the caller is responsible for computing it (see
        # src.domain.recipes.sensors.compute_sensor_signature) and for then
        # attaching the M2M via set_recipe_sensors so the M2M and the
        # denormalised signature stay in lock-step.
        return cls.objects.get_or_create(
            film_simulation=film_simulation,
            dynamic_range=dynamic_range,
            d_range_priority=d_range_priority,
            grain_roughness=grain_roughness,
            grain_size=grain_size,
            color_chrome_effect=color_chrome_effect,
            color_chrome_fx_blue=color_chrome_fx_blue,
            white_balance=white_balance,
            white_balance_red=white_balance_red,
            white_balance_blue=white_balance_blue,
            highlight=highlight,
            shadow=shadow,
            color=color,
            sharpness=sharpness,
            high_iso_nr=high_iso_nr,
            clarity=clarity,
            monochromatic_color_warm_cool=monochromatic_color_warm_cool,
            monochromatic_color_magenta_green=monochromatic_color_magenta_green,
            sensor_signature=sensor_signature,
            defaults={"name": name, "description": description},
        )

    def set_cover_image(self, *, image_id: int) -> None:
        self.cover_image_id = image_id
        self.save(update_fields=["cover_image_id"])

    def set_name(self, *, name: str) -> None:
        self.name = name
        self.save(update_fields=["name"])

    def set_description(self, *, description: str) -> None:
        self.description = description
        self.save(update_fields=["description"])

    def set_sensor_signature(self, *, sensor_signature: str) -> None:
        self.sensor_signature = sensor_signature
        self.save(update_fields=["sensor_signature"])

    def set_sensors(self, *, sensors: Iterable["Sensor"]) -> None:
        self.sensors.set(sensors)

    def update_settings(
        self,
        *,
        film_simulation: str,
        dynamic_range: str,
        d_range_priority: str,
        grain_roughness: str,
        grain_size: str,
        color_chrome_effect: str,
        color_chrome_fx_blue: str,
        white_balance: str,
        white_balance_red: int,
        white_balance_blue: int,
        highlight: Decimal | None,
        shadow: Decimal | None,
        color: Decimal | None,
        sharpness: Decimal | None,
        high_iso_nr: Decimal | None,
        clarity: Decimal | None,
        monochromatic_color_warm_cool: Decimal | None,
        monochromatic_color_magenta_green: Decimal | None,
        sensor_signature: str,
        name: str,
        description: str,
    ) -> None:
        self.film_simulation = film_simulation
        self.dynamic_range = dynamic_range
        self.d_range_priority = d_range_priority
        self.grain_roughness = grain_roughness
        self.grain_size = grain_size
        self.color_chrome_effect = color_chrome_effect
        self.color_chrome_fx_blue = color_chrome_fx_blue
        self.white_balance = white_balance
        self.white_balance_red = white_balance_red
        self.white_balance_blue = white_balance_blue
        self.highlight = highlight
        self.shadow = shadow
        self.color = color
        self.sharpness = sharpness
        self.high_iso_nr = high_iso_nr
        self.clarity = clarity
        self.monochromatic_color_warm_cool = monochromatic_color_warm_cool
        self.monochromatic_color_magenta_green = monochromatic_color_magenta_green
        self.sensor_signature = sensor_signature
        self.name = name
        self.description = description
        self.save(update_fields=[
            "film_simulation", "dynamic_range", "d_range_priority",
            "grain_roughness", "grain_size", "color_chrome_effect",
            "color_chrome_fx_blue", "white_balance", "white_balance_red",
            "white_balance_blue", "highlight", "shadow", "color",
            "sharpness", "high_iso_nr", "clarity",
            "monochromatic_color_warm_cool", "monochromatic_color_magenta_green",
            "sensor_signature", "name", "description",
        ])

    def __str__(self) -> str:
        return f"#{self.id} {self.name}"


class RecipeCard(models.Model):
    filepath = models.CharField(max_length=1024)
    template = models.CharField(max_length=50)
    image = models.ForeignKey(
        "Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recipe_cards",
    )
    recipe = models.ForeignKey(
        "FujifilmRecipe",
        on_delete=models.CASCADE,
        related_name="cards",
    )
    created_at = models.DateTimeField(default=timezone.now)

    @classmethod
    def create(
        cls,
        *,
        filepath: str,
        template: str,
        recipe_id: int,
        image_id: int | None,
    ) -> "RecipeCard":
        return cls.objects.create(
            filepath=filepath,
            template=template,
            recipe_id=recipe_id,
            image_id=image_id,
        )

    def __str__(self) -> str:
        return f"#{self.id} card for recipe #{self.recipe_id}"


_GROUP_TYPE_VERSION_LINE = "VERSION_LINE"
_GROUP_TYPE_FAMILY = "FAMILY"


class RecipeGroup(models.Model):
    GROUP_TYPE_VERSION_LINE = _GROUP_TYPE_VERSION_LINE
    GROUP_TYPE_FAMILY = _GROUP_TYPE_FAMILY

    name = models.CharField(max_length=100, blank=True, default="")
    group_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def new_version_line(cls, *, name: str = "") -> "RecipeGroup":
        return cls.objects.create(group_type=_GROUP_TYPE_VERSION_LINE, name=name)

    @classmethod
    def new_family(cls, *, name: str) -> "RecipeGroup":
        return cls.objects.create(group_type=_GROUP_TYPE_FAMILY, name=name)

    def __str__(self) -> str:
        return f"#{self.id} {self.group_type} {self.name!r}"


class RecipeGroupMember(models.Model):
    group = models.ForeignKey(
        RecipeGroup,
        on_delete=models.CASCADE,
        related_name="members",
    )
    recipe = models.ForeignKey(
        FujifilmRecipe,
        on_delete=models.CASCADE,
        related_name="group_memberships",
    )
    group_type = models.CharField(max_length=50)
    position = models.PositiveIntegerField(null=True, blank=True)
    added_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "recipe"],
                name="unique_recipe_per_group",
            ),
            models.UniqueConstraint(
                fields=["recipe"],
                condition=models.Q(group_type=_GROUP_TYPE_VERSION_LINE),
                name="unique_version_line_per_recipe",
            ),
        ]

    @classmethod
    def new(
        cls,
        *,
        group: RecipeGroup,
        recipe_id: int,
        position: int | None,
        added_at: datetime,
    ) -> "RecipeGroupMember":
        return cls.objects.create(
            group=group,
            recipe_id=recipe_id,
            group_type=group.group_type,
            position=position,
            added_at=added_at,
        )

    def __str__(self) -> str:
        return f"#{self.id} recipe #{self.recipe_id} in group #{self.group_id}"
