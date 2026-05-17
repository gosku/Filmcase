import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0027_protect_image_recipe_fk"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecipeGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, default="", max_length=100)),
                ("group_type", models.CharField(max_length=50)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="RecipeGroupMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group_type", models.CharField(max_length=50)),
                ("position", models.PositiveIntegerField(blank=True, null=True)),
                ("added_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="data.recipegroup",
                    ),
                ),
                (
                    "recipe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="group_memberships",
                        to="data.fujifilmrecipe",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="recipegroupmember",
            constraint=models.UniqueConstraint(
                fields=["group", "recipe"],
                name="unique_recipe_per_group",
            ),
        ),
        migrations.AddConstraint(
            model_name="recipegroupmember",
            constraint=models.UniqueConstraint(
                fields=["recipe"],
                condition=models.Q(group_type="VERSION_LINE"),
                name="unique_version_line_per_recipe",
            ),
        ),
    ]
