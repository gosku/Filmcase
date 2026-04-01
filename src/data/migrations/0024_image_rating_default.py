from django.db import migrations, models


def _set_null_ratings_to_zero(apps, schema_editor):
    Image = apps.get_model("data", "Image")
    Image.objects.filter(rating__isnull=True).update(rating=0)


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0023_add_image_rating"),
    ]

    operations = [
        migrations.AlterField(
            model_name="image",
            name="rating",
            field=models.IntegerField(default=0),
        ),
    ]
