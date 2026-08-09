from datetime import datetime, timezone

import pytest

from src.data import models
from src.domain.library.queries import (
    IgnoredImageNotFound,
    count_ignored_images_by_reason,
    get_ignored_counts_by_folder,
    get_ignored_fingerprints,
    get_ignored_image,
    get_ignored_images,
)
from tests.factories import IgnoredImageFactory, LibraryFolderFactory

MODIFIED_AT = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestGetIgnoredFingerprints:
    def test_returns_size_and_modification_time_keyed_by_path(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/other.jpg",
            file_size=1234,
            file_modified_at=MODIFIED_AT,
        )

        result = get_ignored_fingerprints(folder_id=folder.pk)

        assert set(result) == {"/photos/other.jpg"}
        assert result["/photos/other.jpg"].file_size == 1234
        assert result["/photos/other.jpg"].file_modified_at == MODIFIED_AT

    def test_excludes_records_belonging_to_another_folder(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=LibraryFolderFactory(), filepath="/elsewhere/other.jpg")

        assert get_ignored_fingerprints(folder_id=folder.pk) == {}

    def test_returns_an_empty_mapping_for_a_folder_with_no_records(self):
        folder = LibraryFolderFactory()

        assert get_ignored_fingerprints(folder_id=folder.pk) == {}


@pytest.mark.django_db
class TestGetIgnoredImage:
    def test_returns_the_matching_record(self):
        ignored = IgnoredImageFactory()

        assert get_ignored_image(ignored_id=ignored.pk).pk == ignored.pk

    def test_raises_ignored_image_not_found_for_unknown_id(self):
        with pytest.raises(IgnoredImageNotFound) as exc_info:
            get_ignored_image(ignored_id=9999)

        assert exc_info.value.ignored_id == 9999


@pytest.mark.django_db
class TestGetIgnoredImages:
    def test_returns_the_folders_records_ordered_by_path(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=folder, filepath="/photos/b.jpg")
        IgnoredImageFactory(folder=folder, filepath="/photos/a.jpg")

        result = get_ignored_images(folder_id=folder.pk)

        assert [i.filepath for i in result] == ["/photos/a.jpg", "/photos/b.jpg"]

    def test_limits_to_one_reason_when_asked(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/a.jpg",
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
        )
        errored = IgnoredImageFactory(
            folder=folder,
            filepath="/photos/b.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        result = get_ignored_images(folder_id=folder.pk, reason=models.IgnoredImage.REASON_ERROR)

        assert [i.pk for i in result] == [errored.pk]

    def test_excludes_another_folders_records(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=LibraryFolderFactory())

        assert list(get_ignored_images(folder_id=folder.pk)) == []


@pytest.mark.django_db
class TestCountIgnoredImagesByReason:
    def test_counts_each_reason_separately(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/a.jpg",
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
        )
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/b.jpg",
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
        )
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/c.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        assert count_ignored_images_by_reason(folder_id=folder.pk) == {
            models.IgnoredImage.REASON_NO_FILM_SIMULATION: 2,
            models.IgnoredImage.REASON_ERROR: 1,
        }

    def test_returns_an_empty_mapping_when_nothing_is_ignored(self):
        assert count_ignored_images_by_reason(folder_id=LibraryFolderFactory().pk) == {}


@pytest.mark.django_db
class TestGetIgnoredCountsByFolder:
    def test_counts_records_per_folder(self):
        first = LibraryFolderFactory()
        second = LibraryFolderFactory()
        IgnoredImageFactory(folder=first, filepath="/a/1.jpg")
        IgnoredImageFactory(folder=first, filepath="/a/2.jpg")
        IgnoredImageFactory(folder=second, filepath="/b/1.jpg")

        assert get_ignored_counts_by_folder() == {first.pk: 2, second.pk: 1}

    def test_omits_folders_with_no_records(self):
        LibraryFolderFactory()

        assert get_ignored_counts_by_folder() == {}
