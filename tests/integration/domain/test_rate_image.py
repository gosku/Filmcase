from unittest.mock import patch

import pytest
from django.test import override_settings

from src.domain.images import events, queries
from src.domain.images.operations import UnableToRateImage, rate_image
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestRateImageSuccess:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_persists_rating_to_db(self):
        image = ImageFactory()
        with patch("src.domain.images.operations.queries.find_image_for_path", return_value=image):
            rate_image(image_path="/any/path.jpg", rating=3)
        image.refresh_from_db()
        assert image.rating == 3

    @override_settings(IMAGE_MAX_RATING=5)
    def test_publishes_image_rating_set_event(self, captured_logs):
        image = ImageFactory()
        with patch("src.domain.images.operations.queries.find_image_for_path", return_value=image):
            rate_image(image_path="/any/path.jpg", rating=4)

        rating_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_SET]
        assert len(rating_events) == 1
        assert rating_events[0]["image_id"] == image.pk
        assert rating_events[0]["rating"] == 4


class TestRateImageFailure:
    def test_raises_unable_to_rate_image_when_not_found(self):
        with patch("src.domain.images.operations.queries.find_image_for_path", side_effect=queries.ImageNotFound()):
            with pytest.raises(UnableToRateImage) as exc_info:
                rate_image(image_path="/missing/path.jpg", rating=3)
        assert exc_info.value.image_path == "/missing/path.jpg"

    def test_raises_unable_to_rate_image_when_match_is_ambiguous(self):
        with patch("src.domain.images.operations.queries.find_image_for_path", side_effect=queries.AmbiguousImageMatch()):
            with pytest.raises(UnableToRateImage) as exc_info:
                rate_image(image_path="/ambiguous/path.jpg", rating=3)
        assert exc_info.value.image_path == "/ambiguous/path.jpg"

    @pytest.mark.django_db
    @override_settings(IMAGE_MAX_RATING=5)
    def test_raises_unable_to_rate_image_when_rating_is_invalid(self):
        image = ImageFactory()
        with patch("src.domain.images.operations.queries.find_image_for_path", return_value=image):
            with pytest.raises(UnableToRateImage) as exc_info:
                rate_image(image_path="/any/path.jpg", rating=99)
        assert exc_info.value.image_path == "/any/path.jpg"
