import attrs

from src.data import models


@attrs.frozen
class FixResult:
    updated_in_place: tuple[int, ...]
    merged: tuple[int, ...]


def fix_empty_grain_recipes() -> FixResult:
    """Fix FujifilmRecipe rows where grain_roughness is 'Off' but grain_size is ''.

    Two cases are handled:

    - **Unique row**: no existing recipe with the same settings but grain_size
      'Off' — the buggy row is updated in place.
    - **Duplicate row**: a correct recipe (grain_size 'Off') already exists —
      all Image FK references are reassigned to the correct row, and the buggy
      row is deleted.

    Returns a FixResult with the IDs that were updated or merged.
    """
    buggy_qs = models.FujifilmRecipe.objects.filter(grain_roughness="Off", grain_size="")

    updated_in_place: list[int] = []
    merged: list[int] = []

    for buggy in buggy_qs:
        correct_kwargs = dict(
            film_simulation=buggy.film_simulation,
            dynamic_range=buggy.dynamic_range,
            d_range_priority=buggy.d_range_priority,
            grain_roughness=buggy.grain_roughness,
            grain_size="Off",
            color_chrome_effect=buggy.color_chrome_effect,
            color_chrome_fx_blue=buggy.color_chrome_fx_blue,
            white_balance=buggy.white_balance,
            white_balance_red=buggy.white_balance_red,
            white_balance_blue=buggy.white_balance_blue,
            highlight=buggy.highlight,
            shadow=buggy.shadow,
            color=buggy.color,
            sharpness=buggy.sharpness,
            high_iso_nr=buggy.high_iso_nr,
            clarity=buggy.clarity,
            monochromatic_color_warm_cool=buggy.monochromatic_color_warm_cool,
            monochromatic_color_magenta_green=buggy.monochromatic_color_magenta_green,
        )

        try:
            correct = models.FujifilmRecipe.objects.get(**correct_kwargs)
        except models.FujifilmRecipe.DoesNotExist:
            buggy.grain_size = "Off"
            buggy.save(update_fields=["grain_size"])
            updated_in_place.append(buggy.id)
        else:
            if buggy.name and not correct.name:
                correct.name = buggy.name
                correct.save(update_fields=["name"])
            models.Image.objects.filter(fujifilm_recipe=buggy).update(fujifilm_recipe=correct)
            buggy_id = buggy.id
            buggy.delete()
            merged.append(buggy_id)

    return FixResult(
        updated_in_place=tuple(updated_in_place),
        merged=tuple(merged),
    )
