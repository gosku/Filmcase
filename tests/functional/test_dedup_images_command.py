import shutil
from pathlib import Path

import pytest
from django.core.management import call_command

from src.data import models
from src.domain.images import events
from tests.factories import (
    FujifilmExifFactory,
    FujifilmRecipeFactory,
    ImageFactory,
    RecipeCardFactory,
)

FIXTURE_IMAGE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "images" / "XS107114.JPG"
)


def _copy_fixture(destination: Path) -> str:
    """Copy the fixture image to *destination*, creating parent folders."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_IMAGE, destination)
    return str(destination)


@pytest.mark.django_db
class TestDedupImagesCommand:
    def test_merges_duplicate_rows_into_one(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "photography" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "favorites" / "XS107114.JPG")
        ImageFactory(content_hash="", filepath=path_a)
        ImageFactory(content_hash="", filepath=path_b)

        call_command("dedup_images")

        assert models.Image.objects.count() == 1
        assert models.Image.objects.get().content_hash != ""

    def test_survivor_keeps_album_membership_and_highest_rating(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "b" / "XS107114.JPG")
        keeper = ImageFactory(content_hash="", filepath=path_a, in_album=False, rating=2)
        ImageFactory(content_hash="", filepath=path_b, in_album=True, rating=5)

        call_command("dedup_images")

        keeper.refresh_from_db()
        assert keeper.in_album is True
        assert keeper.rating == 5

    def test_repoints_cover_image_and_recipe_card_references(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "b" / "XS107114.JPG")
        keeper = ImageFactory(content_hash="", filepath=path_a)
        loser = ImageFactory(content_hash="", filepath=path_b)
        recipe = FujifilmRecipeFactory(cover_image=loser)
        card = RecipeCardFactory(image=loser)

        call_command("dedup_images")

        recipe.refresh_from_db()
        card.refresh_from_db()
        assert recipe.cover_image_id == keeper.pk
        assert card.image_id == keeper.pk

    def test_deletes_a_fujifilm_exif_orphaned_by_a_merge(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "b" / "XS107114.JPG")
        ImageFactory(content_hash="", filepath=path_a, fujifilm_exif=FujifilmExifFactory())
        orphaned_exif = FujifilmExifFactory()
        ImageFactory(content_hash="", filepath=path_b, fujifilm_exif=orphaned_exif)

        call_command("dedup_images")

        assert not models.FujifilmExif.objects.filter(pk=orphaned_exif.pk).exists()

    def test_leaves_the_recipe_untouched(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "b" / "XS107114.JPG")
        recipe = FujifilmRecipeFactory()
        ImageFactory(content_hash="", filepath=path_a, fujifilm_recipe=recipe)
        ImageFactory(content_hash="", filepath=path_b, fujifilm_recipe=recipe)

        call_command("dedup_images")

        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_skips_images_whose_file_is_missing(self, captured_logs):
        ImageFactory(content_hash="", filepath="/nonexistent/missing.jpg")

        call_command("dedup_images")

        image = models.Image.objects.get()
        assert image.content_hash == ""
        skipped = [
            e for e in captured_logs
            if e.get("event_type") == events.IMAGE_DEDUP_FILE_MISSING
        ]
        assert len(skipped) == 1

    def test_is_idempotent(self, tmp_path):
        path_a = _copy_fixture(tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(tmp_path / "b" / "XS107114.JPG")
        ImageFactory(content_hash="", filepath=path_a)
        ImageFactory(content_hash="", filepath=path_b)

        call_command("dedup_images")
        call_command("dedup_images")

        assert models.Image.objects.count() == 1
