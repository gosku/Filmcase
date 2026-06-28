import pytest

from src.domain.images.queries import get_all_known_image_paths
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestGetAllKnownImagePaths:
    def test_returns_empty_frozenset_when_no_images_in_db(self):
        result = get_all_known_image_paths()
        assert result == frozenset()

    def test_returns_frozenset_with_single_filepath(self):
        image = ImageFactory(filepath="/photos/img.jpg")
        result = get_all_known_image_paths()
        assert result == frozenset({image.filepath})

    def test_returns_all_filepaths_from_db(self):
        a = ImageFactory(filepath="/photos/a.jpg")
        b = ImageFactory(filepath="/photos/b.jpg")
        c = ImageFactory(filepath="/photos/c.jpg")
        result = get_all_known_image_paths()
        assert result == frozenset({a.filepath, b.filepath, c.filepath})

    def test_return_type_is_frozenset(self):
        ImageFactory(filepath="/photos/img.jpg")
        result = get_all_known_image_paths()
        assert isinstance(result, frozenset)
