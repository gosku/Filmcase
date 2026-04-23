"""
Factory Boy factories for the three core Django models.

Usage::

    from tests.factories import ImageFactory, FujifilmExifFactory, FujifilmRecipeFactory

    # Minimal — all required fields filled with sensible defaults:
    image = ImageFactory()
    exif  = FujifilmExifFactory(film_simulation="Classic Negative")

    # With a related exif object:
    image = ImageFactory(fujifilm_exif=FujifilmExifFactory())

    # Override anything:
    image = ImageFactory(is_favorite=True, camera_model="X-T5")
"""

import factory

from src.data import models


class FujifilmExifFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FujifilmExif

    # All model fields are blank=True, default="" so the only reason to set
    # defaults here is readability.  Override per-test for anything specific.
    film_simulation = "Provia"


class FujifilmRecipeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.FujifilmRecipe

    film_simulation     = "Provia"
    dynamic_range       = "DR100"
    d_range_priority    = "Off"
    grain_roughness     = "Off"
    grain_size          = "Off"
    color_chrome_effect = "Off"
    color_chrome_fx_blue = "Off"
    white_balance       = "Auto"
    white_balance_red   = factory.Sequence(lambda n: n)
    white_balance_blue  = 0
    # Nullable Decimal fields left as None (model default)


class ImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Image

    # filepath has a unique constraint, so use a sequence to avoid collisions.
    filename = factory.Sequence(lambda n: f"image_{n:04d}.jpg")
    filepath = factory.Sequence(lambda n: f"/shots/image_{n:04d}.jpg")

    camera_make  = "FUJIFILM"
    camera_model = "X-S10"
    # All other fields are blank=True, default="" or have a model-level default.


class RecipeCardFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.RecipeCard

    filepath = factory.Sequence(lambda n: f"/recipe_cards/card_{n:04d}.jpg")
    template = "long_label"
    recipe = factory.SubFactory(FujifilmRecipeFactory)
