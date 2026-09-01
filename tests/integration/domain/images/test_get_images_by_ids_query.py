import pytest

from src.domain.images.queries import get_images_by_ids
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestGetImagesByIds:
    def test_returns_the_matching_images_ordered_by_id(self):
        first = ImageFactory(filepath="/photos/a.jpg")
        second = ImageFactory(filepath="/photos/b.jpg")

        result = get_images_by_ids(image_ids=[second.pk, first.pk])

        assert [image.pk for image in result] == [first.pk, second.pk]

    def test_omits_ids_with_no_matching_row(self):
        image = ImageFactory(filepath="/photos/a.jpg")

        result = get_images_by_ids(image_ids=[image.pk, 9999])

        assert [image.pk for image in result] == [image.pk]

    def test_returns_empty_for_no_ids(self):
        assert get_images_by_ids(image_ids=[]) == []
