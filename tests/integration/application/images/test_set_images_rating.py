import pytest
from django.test import override_settings

from src.application.usecases.images import set_images_rating as uc
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestSetImagesRatingPersistence:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_rates_all_selected_images(self) -> None:
        images = [ImageFactory(rating=0) for _ in range(3)]

        result = uc.set_images_rating(image_ids=[image.pk for image in images], rating=4)

        assert result.rated_count == 3
        assert result.requested_count == 3
        assert result.not_found_count == 0
        for image in images:
            image.refresh_from_db()
            assert image.rating == 4

    @override_settings(IMAGE_MAX_RATING=5)
    def test_reports_not_found_for_missing_ids(self) -> None:
        image = ImageFactory(rating=0)
        missing_id = image.pk + 1000

        result = uc.set_images_rating(image_ids=[image.pk, missing_id], rating=2)

        assert result.rated_count == 1
        assert result.requested_count == 2
        assert result.not_found_count == 1
