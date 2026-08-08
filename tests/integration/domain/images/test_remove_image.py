from pathlib import Path

import pytest
from django.test import override_settings

from src.data import models
from src.domain.images import events
from src.domain.images.operations import remove_image
from src.domain.images.thumbnails.queries import thumbnail_cache_path
from tests.factories import (
    FujifilmExifFactory,
    FujifilmRecipeFactory,
    ImageFactory,
    RecipeCardFactory,
)


@pytest.mark.django_db
class TestRemoveImage:
    def test_removes_the_catalog_entry(self):
        image = ImageFactory()

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        assert not models.Image.objects.filter(pk=image.pk).exists()

    def test_never_deletes_the_file_on_disk(self, tmp_path):
        photo = tmp_path / "DSCF0001.JPG"
        photo.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=str(photo))

        remove_image(image=image, reason=events.REMOVE_REASON_FOLDER_REMOVED)

        assert photo.exists()
        assert photo.read_bytes() == b"\xff\xd8"

    def test_deletes_the_exif_row_it_leaves_orphaned(self):
        exif = FujifilmExifFactory()
        image = ImageFactory(fujifilm_exif=exif)

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        assert not models.FujifilmExif.objects.filter(pk=exif.pk).exists()

    def test_keeps_an_exif_row_another_image_still_uses(self):
        exif = FujifilmExifFactory()
        image = ImageFactory(fujifilm_exif=exif)
        ImageFactory(fujifilm_exif=exif)

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        assert models.FujifilmExif.objects.filter(pk=exif.pk).exists()

    def test_keeps_the_recipe_even_when_no_image_is_left(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_clears_the_recipe_cover_it_pointed_at(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)
        recipe.cover_image = image
        recipe.save(update_fields=["cover_image"])

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        recipe.refresh_from_db()
        assert recipe.cover_image_id is None

    def test_keeps_recipe_cards_that_referenced_it(self):
        image = ImageFactory()
        card = RecipeCardFactory(image=image)

        remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

        card.refresh_from_db()
        assert card.image_id is None

    def test_deletes_the_cached_thumbnails(self, tmp_path):
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path, THUMBNAIL_WIDTHS=(600,)):
            cache_path = thumbnail_cache_path(original_path=Path(image.filepath), width=600)
            cache_path.write_bytes(b"\xff\xd8")

            remove_image(image=image, reason=events.REMOVE_REASON_FILE_MISSING)

            assert not cache_path.exists()

    def test_publishes_image_removed_with_the_reason(self, captured_logs):
        image = ImageFactory()
        image_id, filepath = image.pk, image.filepath

        remove_image(image=image, reason=events.REMOVE_REASON_FOLDER_REMOVED)

        matching = [e for e in captured_logs if e.get("event_type") == events.IMAGE_REMOVED]
        assert len(matching) == 1
        assert matching[0]["image_id"] == image_id
        assert matching[0]["filepath"] == filepath
        assert matching[0]["reason"] == events.REMOVE_REASON_FOLDER_REMOVED
