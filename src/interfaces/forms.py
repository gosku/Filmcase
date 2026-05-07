from decimal import Decimal

from django import forms
from django.core import validators

from src.data.camera import constants as camera_constants
from src.domain.recipes import constants as recipe_constants


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
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-2")),
            validators.MaxValueValidator(Decimal("4")),
        ],
    )
    shadow = forms.DecimalField(
        initial=0,
        validators=[
            validators.MinValueValidator(Decimal("-2")),
            validators.MaxValueValidator(Decimal("4")),
        ],
    )
    color = forms.IntegerField(
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
