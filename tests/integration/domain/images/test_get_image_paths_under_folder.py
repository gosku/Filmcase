import pytest

from src.domain.images.queries import get_image_paths_under_folder
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestGetImagePathsUnderFolder:
    def test_returns_images_stored_directly_in_the_folder(self):
        image = ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos")

        assert result == frozenset({image.filepath})

    def test_returns_images_stored_in_nested_subdirectories(self):
        image = ImageFactory(filepath="/photos/2024/spain/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos")

        assert result == frozenset({image.filepath})

    def test_excludes_images_outside_the_folder(self):
        ImageFactory(filepath="/elsewhere/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos")

        assert result == frozenset()

    def test_excludes_a_sibling_folder_sharing_the_name_as_a_prefix(self):
        # Without the separator in the prefix, "/photos" would also claim these.
        ImageFactory(filepath="/photos-old/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos")

        assert result == frozenset()

    def test_tolerates_a_folder_path_with_a_trailing_separator(self):
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos/")

        assert result == frozenset({image.filepath})

    def test_returns_an_empty_set_for_a_folder_with_no_images(self):
        ImageFactory(filepath="/elsewhere/DSCF0001.JPG")

        result = get_image_paths_under_folder(folder_path="/photos")

        assert result == frozenset()
