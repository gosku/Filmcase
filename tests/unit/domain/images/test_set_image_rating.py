import pytest
from django.test import override_settings

from src.domain.images.operations import InvalidImageRatingError, set_image_rating
from tests.factories import ImageFactory


class TestSetImageRatingValidation:
    def test_raises_when_rating_is_negative(self):
        image = ImageFactory.build()
        with pytest.raises(InvalidImageRatingError) as exc_info:
            set_image_rating(image=image, rating=-1)
        assert exc_info.value.rating == -1

    @override_settings(IMAGE_MAX_RATING=5)
    def test_raises_when_rating_exceeds_max(self):
        image = ImageFactory.build()
        with pytest.raises(InvalidImageRatingError) as exc_info:
            set_image_rating(image=image, rating=6)
        assert exc_info.value.rating == 6

    @override_settings(IMAGE_MAX_RATING=10)
    def test_raises_when_rating_exceeds_custom_max(self):
        image = ImageFactory.build()
        with pytest.raises(InvalidImageRatingError) as exc_info:
            set_image_rating(image=image, rating=11)
        assert exc_info.value.rating == 11

    @override_settings(IMAGE_MAX_RATING=5)
    def test_does_not_raise_at_boundary_values(self):
        image = ImageFactory.build()
        # 0 and IMAGE_MAX_RATING are both valid — no exception expected.
        # We patch save to avoid hitting the DB from a .build() instance.
        image.save = lambda **kw: None  # type: ignore[method-assign]
        set_image_rating(image=image, rating=0)
        set_image_rating(image=image, rating=5)
