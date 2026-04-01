import pytest

from src.domain.images import events
from src.domain.images.operations import set_image_rating
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestSetImageRatingPersistence:
    def test_persists_rating_to_db(self):
        image = ImageFactory()
        set_image_rating(image=image, rating=3)
        image.refresh_from_db()
        assert image.rating == 3

    def test_publishes_image_rating_set_event(self, captured_logs):
        image = ImageFactory()
        set_image_rating(image=image, rating=4)

        rating_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_SET]
        assert len(rating_events) == 1
        assert rating_events[0]["image_id"] == image.pk
        assert rating_events[0]["rating"] == 4
