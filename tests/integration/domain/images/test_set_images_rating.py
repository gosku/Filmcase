import pytest
from django.test import override_settings

from src.domain.images import events
from src.domain.images.operations import set_images_rating
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestSetImagesRatingPersistence:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_updates_every_selected_image(self) -> None:
        images = [ImageFactory(rating=0) for _ in range(3)]

        updated = set_images_rating(image_ids=[image.pk for image in images], rating=4)

        assert updated == 3
        for image in images:
            image.refresh_from_db()
            assert image.rating == 4

    @override_settings(IMAGE_MAX_RATING=5)
    def test_leaves_unselected_images_untouched(self) -> None:
        selected = ImageFactory(rating=0)
        other = ImageFactory(rating=2)

        set_images_rating(image_ids=[selected.pk], rating=5)

        other.refresh_from_db()
        assert other.rating == 2

    @override_settings(IMAGE_MAX_RATING=5)
    def test_ignores_non_existent_ids(self) -> None:
        image = ImageFactory(rating=0)
        missing_id = image.pk + 1000

        updated = set_images_rating(image_ids=[image.pk, missing_id], rating=3)

        assert updated == 1
        image.refresh_from_db()
        assert image.rating == 3

    @override_settings(IMAGE_MAX_RATING=5)
    def test_clears_rating_when_set_to_zero(self) -> None:
        image = ImageFactory(rating=4)

        set_images_rating(image_ids=[image.pk], rating=0)

        image.refresh_from_db()
        assert image.rating == 0

    @override_settings(IMAGE_MAX_RATING=5)
    def test_empty_image_ids_is_a_no_op(self, captured_logs) -> None:
        updated = set_images_rating(image_ids=[], rating=3)

        assert updated == 0
        rating_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_SET]
        assert rating_events == []


@pytest.mark.django_db
class TestSetImagesRatingEvents:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_publishes_one_event_per_updated_image(self, captured_logs) -> None:
        images = [ImageFactory(rating=0) for _ in range(3)]
        missing_id = max(image.pk for image in images) + 1000

        set_images_rating(image_ids=[*[image.pk for image in images], missing_id], rating=4)

        rating_events = [e for e in captured_logs if e.get("event_type") == events.IMAGE_RATING_SET]
        assert {e["image_id"] for e in rating_events} == {image.pk for image in images}
        assert all(e["rating"] == 4 for e in rating_events)
        assert missing_id not in {e["image_id"] for e in rating_events}
