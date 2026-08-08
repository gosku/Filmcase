import pytest

from src.application.usecases.library.remove_library_folder import (
    LibraryFolderNotFound,
    remove_library_folder,
)
from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestRemoveLibraryFolder:
    def test_deletes_folder_from_db(self):
        folder = LibraryFolderFactory()

        remove_library_folder(folder_id=folder.pk, delete_images=False)

        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            remove_library_folder(folder_id=99999, delete_images=False)
        assert exc_info.value.folder_id == 99999

    def test_reports_no_images_removed_when_only_the_folder_goes(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        result = remove_library_folder(folder_id=folder.pk, delete_images=False)

        assert result.images_removed == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_reports_how_many_images_left_the_gallery(self):
        folder = LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/photos/DSCF0001.JPG")
        ImageFactory(filepath="/photos/2024/DSCF0002.JPG")

        result = remove_library_folder(folder_id=folder.pk, delete_images=True)

        assert result.images_removed == 2
        assert models.Image.objects.count() == 0
