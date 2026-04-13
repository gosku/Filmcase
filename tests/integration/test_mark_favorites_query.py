from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from src.domain.images.queries import AmbiguousImageMatch, ImageNotFound, find_image_for_path
from src.domain.images.operations import process_image
from tests.factories import FujifilmExifFactory, ImageFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FIXTURE_IMAGE = str(FIXTURES_DIR / "XS107114.JPG")

# UTC equivalent of the fixture image's DateTimeOriginal (2025-12-31T12:23:57+11:00)
FIXTURE_DATE_UTC = datetime(2025, 12, 31, 1, 23, 57, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestFindImageForPath:
    def test_returns_matching_image(self):
        image = process_image(image_path=FIXTURE_IMAGE)

        result = find_image_for_path(image_path=FIXTURE_IMAGE)

        assert result.pk == image.pk

    def test_raises_image_not_found_when_no_record_in_db(self):
        with pytest.raises(ImageNotFound):
            find_image_for_path(image_path=FIXTURE_IMAGE)

    def test_raises_ambiguous_image_match_when_multiple_records(self):
        ImageFactory(filename="XS107114.JPG", filepath="/a/XS107114.JPG", taken_at=FIXTURE_DATE_UTC)
        ImageFactory(filename="XS107114.JPG", filepath="/b/XS107114.JPG", taken_at=FIXTURE_DATE_UTC)

        with pytest.raises(AmbiguousImageMatch):
            find_image_for_path(image_path=FIXTURE_IMAGE)

    def test_by_filepath_resolves_duplicate_filename_and_date(self):
        # Two records share the same filename and taken_at (e.g. original + Favorites copy).
        # _by_filepath matches the exact path immediately without reaching the EXIF strategies.
        exif = FujifilmExifFactory(image_count="18069", film_simulation="Classic Negative", white_balance_fine_tune="Red +3, Blue -5")
        image_favorites = ImageFactory(filename="XS107114.JPG", filepath=FIXTURE_IMAGE, taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif)
        ImageFactory(filename="XS107114.JPG", filepath="/other/folder/XS107114.JPG", taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif)

        result = find_image_for_path(image_path=FIXTURE_IMAGE)

        assert result.pk == image_favorites.pk

    def test_by_filename_and_date_finds_image_at_different_path(self):
        # No DB record at the exact fixture path, but one matches filename + taken_at.
        # _by_filepath misses; _by_filename_and_date succeeds.
        image = ImageFactory(filename="XS107114.JPG", filepath="/other/folder/XS107114.JPG", taken_at=FIXTURE_DATE_UTC)

        result = find_image_for_path(image_path=FIXTURE_IMAGE)

        assert result.pk == image.pk

    def test_continues_to_next_strategy_after_multiple_matches(self):
        # _by_filepath: no match — fixture path not in DB.
        # _by_filename_and_date: no match — records have different filenames.
        # _by_date_and_image_count: multiple — both records share image_count.
        # _by_date_film_and_wb: 1 match — film_simulation differs.
        exif_a = FujifilmExifFactory(image_count="18069", film_simulation="Classic Negative", white_balance_fine_tune="Red +3, Blue -5")
        exif_b = FujifilmExifFactory(image_count="18069", film_simulation="Classic Chrome", white_balance_fine_tune="Red +0, Blue +0")
        image_a = ImageFactory(filename="BURST001.JPG", filepath="/a/BURST001.JPG", taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif_a)
        ImageFactory(filename="BURST002.JPG", filepath="/b/BURST002.JPG", taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif_b)

        # Fixture image has film_simulation="Classic Negative" and matching WB fine tune
        result = find_image_for_path(image_path=FIXTURE_IMAGE)

        assert result.pk == image_a.pk

    def test_disambiguates_burst_shots_by_image_count(self):
        # _by_filepath: no match — fixture path not in DB.
        # _by_filename_and_date: no match — records have different filenames.
        # _by_date_and_image_count: 1 match — only image_count="18069" matches the fixture.
        exif_a = FujifilmExifFactory(image_count="18069")
        exif_b = FujifilmExifFactory(image_count="18070")
        image_a = ImageFactory(filename="BURST001.JPG", filepath="/a/BURST001.JPG", taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif_a)
        ImageFactory(filename="BURST002.JPG", filepath="/b/BURST002.JPG", taken_at=FIXTURE_DATE_UTC, fujifilm_exif=exif_b)

        result = find_image_for_path(image_path=FIXTURE_IMAGE)

        assert result.pk == image_a.pk
