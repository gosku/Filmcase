from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Change tonal / numeric recipe fields from IntegerField to
    DecimalField(max_digits=4, decimal_places=1) so that Fujifilm half-step
    values (e.g. highlight -1.5, shadow +1.5) can be stored without rounding.
    """

    dependencies = [
        ("data", "0018_add_aperture_shutter_speed_focal_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="highlight",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="shadow",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="color",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="sharpness",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="high_iso_nr",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="clarity",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="monochromatic_color_warm_cool",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
        migrations.AlterField(
            model_name="fujifilmrecipe",
            name="monochromatic_color_magenta_green",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True),
        ),
    ]
