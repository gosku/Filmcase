import pytest

from src.domain.library.queries import (
    LibraryFolderNotFound,
    count_exclusively_owned_images,
    get_exclusively_owned_image_ids,
)
from tests.factories import ImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestGetExclusivelyOwnedImageIds:
    def test_returns_images_under_the_folder(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == [image.pk]

    def test_excludes_images_outside_the_folder(self):
        folder = LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/elsewhere/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == []

    def test_excludes_images_a_nested_registered_folder_also_covers(self):
        outer = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")
        only_in_outer = ImageFactory(filepath="/photos/2023/DSCF0002.JPG")

        result = get_exclusively_owned_image_ids(folder_id=outer.pk)

        assert result == [only_in_outer.pk]

    def test_excludes_images_an_enclosing_registered_folder_also_covers(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=inner.pk)

        assert result == []

    def test_returns_images_when_the_only_other_folder_is_unrelated(self):
        folder = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/scans")
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == [image.pk]

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            get_exclusively_owned_image_ids(folder_id=9999)

        assert exc_info.value.folder_id == 9999


@pytest.mark.django_db
class TestCountExclusivelyOwnedImages:
    def test_counts_only_images_no_other_folder_covers(self):
        outer = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")
        ImageFactory(filepath="/photos/2023/DSCF0002.JPG")

        assert count_exclusively_owned_images(folder_id=outer.pk) == 1

    def test_counts_zero_for_a_folder_fully_covered_by_another(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        assert count_exclusively_owned_images(folder_id=inner.pk) == 0
