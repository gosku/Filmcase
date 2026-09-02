from decimal import Decimal

from django import forms
from django.conf import settings as django_settings
from django.core import validators

from src.data import sensors as sensors_module
from src.data.camera import constants as camera_constants
from src.domain.camera import device_config
from src.domain.recipes import constants as recipe_constants
from src.domain.settings.dataclasses import AppSettings


def _choices(values: list[str]) -> list[tuple[str, str]]:
    return [(v, v) for v in values]


_FILM_SIM_CHOICES = _choices(list(camera_constants.FILM_SIMULATION_TO_PTP))
_WB_CHOICES = _choices(list(camera_constants.WHITE_BALANCE_TO_PTP))
_DR_CHOICES = _choices(list(camera_constants.DRANGE_MODE_TO_PTP))
_DR_PRIORITY_CHOICES = _choices(["Off", "Weak", "Strong", "Auto"])
_CCE_CHOICES = _choices(["Off", "Weak", "Strong"])
_CFX_CHOICES = _choices(["Off", "Weak", "Strong"])
_GRAIN_ROUGHNESS_CHOICES = _choices(["Off", "Weak", "Strong"])
_GRAIN_SIZE_CHOICES = _choices(["Off", "Small", "Large"])
_SENSOR_CHOICES = _choices(list(sensors_module.SENSOR_NAMES))

_HALF = Decimal("0.5")


class CreateRecipe(forms.Form):
    name = forms.CharField(max_length=25)
    film_simulation = forms.ChoiceField(choices=_FILM_SIM_CHOICES)
    dynamic_range = forms.ChoiceField(choices=_DR_CHOICES, required=False)
    d_range_priority = forms.ChoiceField(choices=_DR_PRIORITY_CHOICES)
    grain_roughness = forms.ChoiceField(choices=_GRAIN_ROUGHNESS_CHOICES)
    grain_size = forms.ChoiceField(choices=_GRAIN_SIZE_CHOICES)
    color_chrome_effect = forms.ChoiceField(choices=_CCE_CHOICES)
    color_chrome_fx_blue = forms.ChoiceField(choices=_CFX_CHOICES)
    white_balance = forms.ChoiceField(choices=_WB_CHOICES)
    kelvin_temperature = forms.IntegerField(
        required=False,
        initial=6500,
        validators=[
            validators.MinValueValidator(2500),
            validators.MaxValueValidator(10000),
        ],
    )
    white_balance_red = forms.IntegerField(
        initial=0,
        validators=[validators.MinValueValidator(-9), validators.MaxValueValidator(9)],
    )
    white_balance_blue = forms.IntegerField(
        initial=0,
        validators=[validators.MinValueValidator(-9), validators.MaxValueValidator(9)],
    )
    highlight = forms.DecimalField(
        required=False,
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-2")),
            validators.MaxValueValidator(Decimal("4")),
        ],
    )
    shadow = forms.DecimalField(
        required=False,
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-2")),
            validators.MaxValueValidator(Decimal("4")),
        ],
    )
    color = forms.IntegerField(
        required=False,
        initial=0,
        validators=[validators.MinValueValidator(-4), validators.MaxValueValidator(4)],
    )
    sharpness = forms.IntegerField(
        initial=0,
        validators=[validators.MinValueValidator(-4), validators.MaxValueValidator(4)],
    )
    high_iso_nr = forms.IntegerField(
        initial=0,
        validators=[validators.MinValueValidator(-4), validators.MaxValueValidator(4)],
    )
    clarity = forms.IntegerField(
        initial=0,
        validators=[validators.MinValueValidator(-5), validators.MaxValueValidator(5)],
    )
    monochromatic_color_warm_cool = forms.DecimalField(
        required=False,
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-9")),
            validators.MaxValueValidator(Decimal("9")),
        ],
    )
    monochromatic_color_magenta_green = forms.DecimalField(
        required=False,
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-9")),
            validators.MaxValueValidator(Decimal("9")),
        ],
    )
    sensors = forms.MultipleChoiceField(
        choices=_SENSOR_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_highlight(self) -> Decimal | None:
        value: Decimal | None = self.cleaned_data.get("highlight")
        if value is not None and value % _HALF != 0:
            raise forms.ValidationError("Must be a multiple of 0.5.")
        return value

    def clean_shadow(self) -> Decimal | None:
        value: Decimal | None = self.cleaned_data.get("shadow")
        if value is not None and value % _HALF != 0:
            raise forms.ValidationError("Must be a multiple of 0.5.")
        return value

    def clean(self) -> dict[str, object]:
        data: dict[str, object] = super().clean() or {}

        film_sim = data.get("film_simulation")
        grain_roughness = data.get("grain_roughness")
        d_range_priority = data.get("d_range_priority")
        wb = data.get("white_balance")

        # Monochromatic sliders are meaningless for colour film simulations.
        if film_sim is not None and film_sim not in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS:
            data["monochromatic_color_warm_cool"] = None
            data["monochromatic_color_magenta_green"] = None

        # Grain size is irrelevant when roughness is Off.
        if grain_roughness == "Off":
            data["grain_size"] = None

        # Dynamic range is managed automatically when D-Range Priority is active.
        # The field is required only when D-Range Priority is Off (the browser doesn't
        # submit disabled selects, so required=False at the field level).
        if d_range_priority is not None and d_range_priority != "Off":
            data["dynamic_range"] = None
        elif not data.get("dynamic_range") and "dynamic_range" not in self.errors:
            self.add_error("dynamic_range", "This field is required.")

        # Kelvin temperature is required when WB mode is Kelvin, forbidden otherwise.
        if wb == "Kelvin":
            if not data.get("kelvin_temperature") and "kelvin_temperature" not in self.errors:
                self.add_error("kelvin_temperature", "Temperature is required for Kelvin white balance.")
        elif wb is not None:
            data["kelvin_temperature"] = None

        return data


_TRANSPORT_CHOICES = [
    (device_config.TRANSPORT_SERVER, "Server (camera attached to this host)"),
    (device_config.TRANSPORT_BROWSER, "Browser (camera attached to your machine)"),
]

# Non-negative and strictly-positive validators reused across the timing/size fields.
_NON_NEGATIVE = [validators.MinValueValidator(0)]
_POSITIVE = [validators.MinValueValidator(1)]
_PERCENT = [validators.MinValueValidator(0), validators.MaxValueValidator(100)]
_FRACTION = [validators.MinValueValidator(0), validators.MaxValueValidator(1)]


class Preferences(forms.Form):
    """
    Edit the user-adjustable application settings backed by constance.

    Field names match the constance keys in lower snake case. Help text is
    filled in from ``settings.CONSTANCE_CONFIG`` so the descriptions have a
    single source of truth.
    """

    # Camera
    camera_transport = forms.ChoiceField(choices=_TRANSPORT_CHOICES)
    camera_verify_writes = forms.BooleanField(required=False)
    camera_post_read_delay_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_pre_write_delay_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_post_write_delay_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_post_cursor_delay_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_inter_slot_delay_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_max_retries = forms.IntegerField(validators=_NON_NEGATIVE)
    camera_retry_backoff_s = forms.FloatField(validators=_NON_NEGATIVE)
    camera_usb_timeout_ms = forms.IntegerField(validators=_POSITIVE)
    # Recipes
    recipe_explorer_page_size = forms.IntegerField(validators=_POSITIVE)
    recipe_graph_max_distance = forms.IntegerField(validators=_NON_NEGATIVE)
    recipe_card_aperture_scrim_top_opacity = forms.IntegerField(validators=_PERCENT)
    recipe_card_aperture_scrim_bottom_opacity = forms.IntegerField(validators=_PERCENT)
    # Images
    gallery_page_size = forms.IntegerField(validators=_POSITIVE)
    image_max_rating = forms.IntegerField(validators=_POSITIVE)
    thumbnail_widths = forms.CharField()
    # Library
    library_prune_guard_fraction = forms.FloatField(validators=_FRACTION)
    library_prune_guard_min_images = forms.IntegerField(validators=_NON_NEGATIVE)
    sync_image_batch_size = forms.IntegerField(validators=_POSITIVE)
    library_ignored_directory_prefixes = forms.CharField(required=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        config_descriptions = django_settings.CONSTANCE_CONFIG
        for field_name, field in self.fields.items():
            entry = config_descriptions.get(field_name.upper())
            if entry is not None:
                field.help_text = entry[1]

    @classmethod
    def initial_from(cls, values: AppSettings) -> dict[str, object]:
        """
        Build the initial form data from the current settings values.
        """
        return {
            "camera_transport": values.camera_transport,
            "camera_verify_writes": values.camera_verify_writes,
            "camera_post_read_delay_s": values.camera_post_read_delay_s,
            "camera_pre_write_delay_s": values.camera_pre_write_delay_s,
            "camera_post_write_delay_s": values.camera_post_write_delay_s,
            "camera_post_cursor_delay_s": values.camera_post_cursor_delay_s,
            "camera_inter_slot_delay_s": values.camera_inter_slot_delay_s,
            "camera_max_retries": values.camera_max_retries,
            "camera_retry_backoff_s": values.camera_retry_backoff_s,
            "camera_usb_timeout_ms": values.camera_usb_timeout_ms,
            "recipe_explorer_page_size": values.recipe_explorer_page_size,
            "recipe_graph_max_distance": values.recipe_graph_max_distance,
            "recipe_card_aperture_scrim_top_opacity": values.recipe_card_aperture_scrim_top_opacity,
            "recipe_card_aperture_scrim_bottom_opacity": values.recipe_card_aperture_scrim_bottom_opacity,
            "gallery_page_size": values.gallery_page_size,
            "image_max_rating": values.image_max_rating,
            "thumbnail_widths": ",".join(str(width) for width in values.thumbnail_widths),
            "library_prune_guard_fraction": values.library_prune_guard_fraction,
            "library_prune_guard_min_images": values.library_prune_guard_min_images,
            "sync_image_batch_size": values.sync_image_batch_size,
            "library_ignored_directory_prefixes": ",".join(values.library_ignored_directory_prefixes),
        }

    def clean_thumbnail_widths(self) -> tuple[int, ...]:
        raw: str = self.cleaned_data["thumbnail_widths"]
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise forms.ValidationError("Enter at least one width.")
        widths: list[int] = []
        for part in parts:
            try:
                width = int(part)
            except ValueError:
                raise forms.ValidationError("Widths must be whole numbers separated by commas, e.g. 600,1200.")
            if width <= 0:
                raise forms.ValidationError("Widths must be greater than zero.")
            widths.append(width)
        return tuple(widths)

    def clean_library_ignored_directory_prefixes(self) -> tuple[str, ...]:
        # An empty value is allowed: it means nothing is skipped. Blank entries
        # are dropped so a stray comma cannot introduce an empty prefix, which
        # would match every directory name.
        raw: str = self.cleaned_data["library_ignored_directory_prefixes"]
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    def to_app_settings(self) -> AppSettings:
        """
        Build an AppSettings from the cleaned form data.

        Only call this once the form has validated.
        """
        data = self.cleaned_data
        return AppSettings(
            camera_transport=data["camera_transport"],
            camera_verify_writes=data["camera_verify_writes"],
            camera_post_read_delay_s=data["camera_post_read_delay_s"],
            camera_pre_write_delay_s=data["camera_pre_write_delay_s"],
            camera_post_write_delay_s=data["camera_post_write_delay_s"],
            camera_post_cursor_delay_s=data["camera_post_cursor_delay_s"],
            camera_inter_slot_delay_s=data["camera_inter_slot_delay_s"],
            camera_max_retries=data["camera_max_retries"],
            camera_retry_backoff_s=data["camera_retry_backoff_s"],
            camera_usb_timeout_ms=data["camera_usb_timeout_ms"],
            recipe_explorer_page_size=data["recipe_explorer_page_size"],
            recipe_graph_max_distance=data["recipe_graph_max_distance"],
            recipe_card_aperture_scrim_top_opacity=data["recipe_card_aperture_scrim_top_opacity"],
            recipe_card_aperture_scrim_bottom_opacity=data["recipe_card_aperture_scrim_bottom_opacity"],
            gallery_page_size=data["gallery_page_size"],
            image_max_rating=data["image_max_rating"],
            thumbnail_widths=data["thumbnail_widths"],
            library_prune_guard_fraction=data["library_prune_guard_fraction"],
            library_prune_guard_min_images=data["library_prune_guard_min_images"],
            sync_image_batch_size=data["sync_image_batch_size"],
            library_ignored_directory_prefixes=data["library_ignored_directory_prefixes"],
        )
