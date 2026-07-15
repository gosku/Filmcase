from unittest import mock

import pytest
from django.test import override_settings

from src.domain.images import operations
from src.domain.images.operations import InvalidImageRatingError, set_images_rating


class TestSetImagesRatingValidation:
    def test_raises_when_rating_is_negative(self) -> None:
        with pytest.raises(InvalidImageRatingError) as exc_info:
            set_images_rating(image_ids=[1, 2], rating=-1)
        assert exc_info.value.rating == -1

    @override_settings(IMAGE_MAX_RATING=5)
    def test_raises_when_rating_exceeds_max(self) -> None:
        with pytest.raises(InvalidImageRatingError) as exc_info:
            set_images_rating(image_ids=[1, 2], rating=6)
        assert exc_info.value.rating == 6

    @override_settings(IMAGE_MAX_RATING=5)
    def test_does_not_touch_db_when_rating_is_invalid(self) -> None:
        with mock.patch.object(operations.models.Image, "objects") as objects:
            with pytest.raises(InvalidImageRatingError):
                set_images_rating(image_ids=[1, 2], rating=6)
        objects.filter.assert_not_called()

    @override_settings(IMAGE_MAX_RATING=5)
    def test_does_not_publish_events_when_rating_is_invalid(self) -> None:
        with mock.patch.object(operations.events, "publish_event") as publish_event:
            with pytest.raises(InvalidImageRatingError):
                set_images_rating(image_ids=[1, 2], rating=6)
        publish_event.assert_not_called()
