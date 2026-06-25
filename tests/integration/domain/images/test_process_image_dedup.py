import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from django.db import IntegrityError

from src.data import models
from src.domain.images import queries
from src.domain.images.dataclasses import ImageExifData
from src.domain.images.operations import process_image
from tests.factories import FujifilmExifFactory, ImageFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FIXTURE_IMAGE = str(FIXTURES_DIR / "XS107114.JPG")
OTHER_FIXTURE_IMAGE = str(FIXTURES_DIR / "XS107209.jpg")

# Identity of XS107114.JPG, as read from its EXIF (see test_operations.py).
FIXTURE_SERIAL = "FF02B6275695     Y56201 2020:12:02 C6B310316B40"
FIXTURE_IMAGE_COUNT = "18069"
FIXTURE_TAKEN_AT = datetime(2025, 12, 31, 12, 23, 57, tzinfo=timezone(timedelta(hours=11)))


def _copy_fixture(*, destination: Path) -> str:
    """Copy XS107114.JPG to *destination*, creating parent folders, and return its path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_IMAGE, destination)
    return str(destination)


@pytest.mark.django_db
class TestProcessImageDeduplicates:
    def test_same_image_in_two_folders_creates_one_row(self, tmp_path):
        path_a = _copy_fixture(destination=tmp_path / "photography" / "XS107114.JPG")
        path_b = _copy_fixture(destination=tmp_path / "favorites" / "XS107114.JPG")

        image_a = process_image(image_path=path_a)
        image_b = process_image(image_path=path_b)

        assert image_a.pk == image_b.pk
        assert models.Image.objects.count() == 1

    def test_reimporting_the_same_path_creates_no_duplicate(self, tmp_path):
        path = _copy_fixture(destination=tmp_path / "XS107114.JPG")

        first = process_image(image_path=path)
        second = process_image(image_path=path)

        assert first.pk == second.pk
        assert models.Image.objects.count() == 1

    def test_a_hash_match_never_overrides_existing_data(self, tmp_path):
        path_a = _copy_fixture(destination=tmp_path / "a" / "XS107114.JPG")
        path_b = _copy_fixture(destination=tmp_path / "b" / "XS107114.JPG")

        image = process_image(image_path=path_a)
        models.Image.objects.filter(pk=image.pk).update(camera_model="EDITED-BY-HAND")

        process_image(image_path=path_b)

        image.refresh_from_db()
        assert image.camera_model == "EDITED-BY-HAND"
        assert models.Image.objects.count() == 1

    def test_different_files_with_identical_exif_create_separate_rows(self, tmp_path):
        # An edited copy (e.g. saved by Google Photos as XS107114~3.JPG) keeps
        # the original's EXIF but has different bytes, so it is a distinct row.
        original = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        edited = _copy_fixture(destination=tmp_path / "XS107114~3.JPG")
        with open(edited, "ab") as edited_file:
            edited_file.write(b"\x00")  # change the bytes, keep the EXIF

        process_image(image_path=original)
        process_image(image_path=edited)

        assert models.Image.objects.count() == 2

    def test_two_distinct_shots_create_separate_rows(self, tmp_path):
        path_one = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        path_two = str(tmp_path / "XS107209.jpg")
        shutil.copy(OTHER_FIXTURE_IMAGE, path_two)

        process_image(image_path=path_one)
        process_image(image_path=path_two)

        assert models.Image.objects.count() == 2

    def test_legacy_unhashed_row_at_same_path_has_its_hash_backfilled(self):
        legacy = ImageFactory(
            filepath=FIXTURE_IMAGE,
            filename="XS107114.JPG",
            content_hash="",
        )

        result = process_image(image_path=FIXTURE_IMAGE)

        assert result.pk == legacy.pk
        assert models.Image.objects.count() == 1
        legacy.refresh_from_db()
        assert legacy.content_hash == queries.compute_content_hash(image_path=FIXTURE_IMAGE)

    def test_exif_bridge_matches_a_moved_legacy_image_without_changing_its_path(self, tmp_path):
        exif = FujifilmExifFactory(
            internal_serial_number=FIXTURE_SERIAL,
            image_count=FIXTURE_IMAGE_COUNT,
        )
        legacy = ImageFactory(
            filepath="/old/location/XS107114.JPG",
            filename="XS107114.JPG",
            taken_at=FIXTURE_TAKEN_AT,
            content_hash="",
            fujifilm_exif=exif,
        )
        new_path = _copy_fixture(destination=tmp_path / "moved" / "XS107114.JPG")

        result = process_image(image_path=new_path)

        assert result.pk == legacy.pk
        assert models.Image.objects.count() == 1
        legacy.refresh_from_db()
        # The existing record's filepath is left untouched — the moved copy is
        # not created as a duplicate, but it also does not relocate the record.
        assert legacy.filepath == "/old/location/XS107114.JPG"
        assert legacy.content_hash == queries.compute_content_hash(image_path=new_path)

    def test_exif_bridge_does_not_merge_an_original_with_its_edited_copy(self, tmp_path):
        exif = FujifilmExifFactory(
            internal_serial_number=FIXTURE_SERIAL,
            image_count=FIXTURE_IMAGE_COUNT,
        )
        legacy_original = ImageFactory(
            filepath="/old/location/XS107114.JPG",
            filename="XS107114.JPG",
            taken_at=FIXTURE_TAKEN_AT,
            content_hash="",
            fujifilm_exif=exif,
        )
        legacy_edit = ImageFactory(
            filepath="/old/location/XS107114~3.JPG",
            filename="XS107114~3.JPG",
            taken_at=FIXTURE_TAKEN_AT,
            content_hash="",
            fujifilm_exif=exif,
        )
        moved_edit_path = _copy_fixture(destination=tmp_path / "moved" / "XS107114~3.JPG")

        result = process_image(image_path=moved_edit_path)

        assert result.pk == legacy_edit.pk
        legacy_original.refresh_from_db()
        assert legacy_original.content_hash == ""
        assert models.Image.objects.count() == 2


@pytest.mark.django_db
class TestComputeContentHash:
    def test_returns_the_sha256_of_the_file_bytes(self):
        expected = hashlib.sha256(Path(FIXTURE_IMAGE).read_bytes()).hexdigest()

        assert queries.compute_content_hash(image_path=FIXTURE_IMAGE) == expected


@pytest.mark.django_db
class TestImageContentHashConstraint:
    def test_rejects_a_second_row_with_the_same_non_empty_hash(self):
        ImageFactory(content_hash="a" * 64)

        with pytest.raises(IntegrityError):
            ImageFactory(content_hash="a" * 64)

    def test_allows_multiple_rows_with_an_empty_hash(self):
        ImageFactory(content_hash="")
        ImageFactory(content_hash="")

        assert models.Image.objects.filter(content_hash="").count() == 2


@pytest.mark.django_db
class TestFindExistingImageForImport:
    def test_returns_the_image_with_a_matching_content_hash(self):
        image = ImageFactory(content_hash="hash-a", filepath="/a/x.jpg", filename="x.jpg")

        result = queries.find_existing_image_for_import(
            content_hash="hash-a",
            filepath="/unrelated/path.jpg",
            exif=ImageExifData(),
            taken_at=None,
            filename="path.jpg",
        )

        assert result is not None
        assert result.pk == image.pk

    def test_returns_the_image_at_a_matching_filepath_when_the_hash_misses(self):
        image = ImageFactory(content_hash="", filepath="/a/x.jpg", filename="x.jpg")

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/a/x.jpg",
            exif=ImageExifData(),
            taken_at=None,
            filename="x.jpg",
        )

        assert result is not None
        assert result.pk == image.pk

    def test_prefers_a_hash_match_over_a_filepath_match(self):
        hash_match = ImageFactory(content_hash="hash-b", filepath="/a/x.jpg", filename="x.jpg")
        filepath_match = ImageFactory(content_hash="", filepath="/query/path.jpg", filename="path.jpg")

        result = queries.find_existing_image_for_import(
            content_hash="hash-b",
            filepath="/query/path.jpg",
            exif=ImageExifData(),
            taken_at=None,
            filename="path.jpg",
        )

        assert result is not None
        assert result.pk == hash_match.pk
        assert result.pk != filepath_match.pk

    def test_returns_an_unhashed_legacy_image_via_the_exif_bridge(self):
        exif_record = FujifilmExifFactory(internal_serial_number="SN1", image_count="100")
        legacy = ImageFactory(
            content_hash="",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=FIXTURE_TAKEN_AT,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x.jpg",
        )

        assert result is not None
        assert result.pk == legacy.pk

    def test_exif_bridge_requires_a_matching_filename(self):
        exif_record = FujifilmExifFactory(internal_serial_number="SN1", image_count="100")
        ImageFactory(
            content_hash="",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=FIXTURE_TAKEN_AT,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x~2.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x~2.jpg",
        )

        assert result is None

    def test_exif_bridge_ignores_rows_that_are_already_hashed(self):
        exif_record = FujifilmExifFactory(internal_serial_number="SN1", image_count="100")
        ImageFactory(
            content_hash="already-hashed",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=FIXTURE_TAKEN_AT,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x.jpg",
        )

        assert result is None

    def test_exif_bridge_skipped_when_the_serial_number_is_missing(self):
        # A legacy row that the bridge query would match if it ran.
        exif_record = FujifilmExifFactory(internal_serial_number="", image_count="100")
        ImageFactory(
            content_hash="",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=FIXTURE_TAKEN_AT,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x.jpg",
            exif=ImageExifData(internal_serial_number="", image_count="100"),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x.jpg",
        )

        assert result is None

    def test_exif_bridge_skipped_when_the_image_count_is_missing(self):
        exif_record = FujifilmExifFactory(internal_serial_number="SN1", image_count="")
        ImageFactory(
            content_hash="",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=FIXTURE_TAKEN_AT,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count=""),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x.jpg",
        )

        assert result is None

    def test_exif_bridge_skipped_when_the_taken_at_is_missing(self):
        exif_record = FujifilmExifFactory(internal_serial_number="SN1", image_count="100")
        ImageFactory(
            content_hash="",
            filepath="/old/x.jpg",
            filename="x.jpg",
            taken_at=None,
            fujifilm_exif=exif_record,
        )

        result = queries.find_existing_image_for_import(
            content_hash="fresh-hash",
            filepath="/new/x.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=None,
            filename="x.jpg",
        )

        assert result is None

    def test_returns_none_when_no_strategy_matches(self):
        result = queries.find_existing_image_for_import(
            content_hash="nothing",
            filepath="/nowhere/x.jpg",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=FIXTURE_TAKEN_AT,
            filename="x.jpg",
        )

        assert result is None
