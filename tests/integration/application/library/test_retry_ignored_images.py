import pytest

from src.application.usecases.library.retry_ignored_images import (
    IgnoredImageNotFound,
    LibraryFolderNotFound,
    retry_ignored_image,
    retry_ignored_images,
)
from src.data import models
from tests.factories import IgnoredImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestRetryIgnoredImages:
    def test_forgets_every_record_in_the_folder(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=folder, filepath="/a/1.jpg")
        IgnoredImageFactory(folder=folder, filepath="/a/2.jpg")

        result = retry_ignored_images(folder_id=folder.pk)

        assert result.forgotten == 2
        assert models.IgnoredImage.objects.count() == 0

    def test_forgets_only_the_requested_reason(self):
        folder = LibraryFolderFactory()
        kept = IgnoredImageFactory(
            folder=folder,
            filepath="/a/1.jpg",
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
        )
        IgnoredImageFactory(
            folder=folder,
            filepath="/a/2.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        result = retry_ignored_images(folder_id=folder.pk, reason=models.IgnoredImage.REASON_ERROR)

        assert result.forgotten == 1
        assert list(models.IgnoredImage.objects.values_list("pk", flat=True)) == [kept.pk]

    def test_reports_zero_when_there_is_nothing_to_forget(self):
        folder = LibraryFolderFactory()

        assert retry_ignored_images(folder_id=folder.pk).forgotten == 0

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            retry_ignored_images(folder_id=9999)

        assert exc_info.value.folder_id == 9999


@pytest.mark.django_db
class TestRetryIgnoredImage:
    def test_forgets_the_record_and_reports_its_path(self):
        ignored = IgnoredImageFactory(filepath="/photos/other.jpg")

        result = retry_ignored_image(ignored_id=ignored.pk)

        assert result.filepath == "/photos/other.jpg"
        assert models.IgnoredImage.objects.count() == 0

    def test_raises_ignored_image_not_found_for_unknown_id(self):
        with pytest.raises(IgnoredImageNotFound) as exc_info:
            retry_ignored_image(ignored_id=9999)

        assert exc_info.value.ignored_id == 9999
