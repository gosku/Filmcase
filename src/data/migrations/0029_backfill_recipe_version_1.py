from typing import Any

from django.db import migrations
from django.utils import timezone


def backfill_version_1(apps: Any, schema_editor: Any) -> None:
    FujifilmRecipe = apps.get_model("data", "FujifilmRecipe")
    RecipeGroup = apps.get_model("data", "RecipeGroup")
    RecipeGroupMember = apps.get_model("data", "RecipeGroupMember")
    now = timezone.now()

    for recipe in FujifilmRecipe.objects.all():
        earliest_image = recipe.images.order_by("created_at", "id").first()
        added_at = earliest_image.created_at if earliest_image else now

        group = RecipeGroup.objects.create(group_type="VERSION_LINE", name="")
        RecipeGroupMember.objects.create(
            group=group,
            recipe=recipe,
            group_type="VERSION_LINE",
            position=1,
            added_at=added_at,
        )


def reverse_backfill(apps: Any, schema_editor: Any) -> None:
    RecipeGroup = apps.get_model("data", "RecipeGroup")
    RecipeGroup.objects.filter(group_type="VERSION_LINE").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0028_recipegroup_recipegroupmember"),
    ]

    operations = [
        migrations.RunPython(backfill_version_1, reverse_code=reverse_backfill),
    ]
