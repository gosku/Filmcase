from unittest.mock import patch

import pytest
from django.test import override_settings

from src.application.usecases.images.rate_images import rate_images_in_folder
from src.domain.images import events
from src.domain.images.operations import UnableToRateImage
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestRateImagesInFolderEvents:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_publishes_rating_failed_event_for_each_unratable_image(self, captured_logs):
        image_a = ImageFactory(filepath="/shots/a.jpg")
        image_b = ImageFactory(filepath="/shots/b.jpg")

        def fail_for_a(*, image_path: str, rating: int):
            if "a.jpg" in image_path:
                raise UnableToRateImage(image_path)
            from src.domain.images.operations import set_image_rating
            set_image_rating(image=image_b, rating=rating)

        with patch("src.domain.images.queries.collect_image_paths", return_value=[image_a.filepath, image_b.filepath]):
            with patch("src.application.usecases.images.rate_images.operations.rate_image", side_effect=fail_for_a):
                result = rate_images_in_folder(folder="/shots", rating=3)

        failed_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_FAILED]
        assert len(failed_events) == 1
        assert failed_events[0]["image_path"] == image_a.filepath

        assert image_a.filepath in result.skipped
        assert image_b.filepath in result.rated

    @override_settings(IMAGE_MAX_RATING=5)
    def test_publishes_one_failed_event_per_unratable_image(self, captured_logs):
        paths = ["/shots/a.jpg", "/shots/b.jpg", "/shots/c.jpg"]

        with patch("src.domain.images.queries.collect_image_paths", return_value=paths):
            with patch("src.application.usecases.images.rate_images.operations.rate_image", side_effect=UnableToRateImage("/shots/a.jpg")):
                result = rate_images_in_folder(folder="/shots", rating=3)

        failed_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_FAILED]
        assert len(failed_events) == 3
        assert len(result.skipped) == 3
        assert len(result.rated) == 0
