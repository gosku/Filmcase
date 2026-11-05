from typing import Any

from django.db import migrations

_EXIFTOOL_NAME = "Daylight Fluorescent"
_CAMERA_NAME = "Fluorescent 1"


def rename_to_camera_name(apps: Any, schema_editor: Any) -> None:
    # Older imports stored exiftool's "Daylight Fluorescent" label. The decoder
    # now stores the camera-display name "Fluorescent 1" (matching the PTP/SDK
    # whitelist), so bring existing rows onto the same representation.
    FujifilmRecipe = apps.get_model("data", "FujifilmRecipe")
    FujifilmRecipe.objects.filter(white_balance=_EXIFTOOL_NAME).update(
        white_balance=_CAMERA_NAME
    )


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0039_recipegroup_unique_collection_name_ci"),
    ]

    operations = [
        # Not reversible: after the rename, originally-"Daylight Fluorescent" rows
        # are indistinguishable from recipes already stored as "Fluorescent 1".
        migrations.RunPython(rename_to_camera_name, reverse_code=migrations.RunPython.noop),
    ]
