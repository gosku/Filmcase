from datetime import timedelta

import pytest
from django.utils import timezone as dj_tz

from src.data import models
from src.domain.images.queries import get_image_detail
from tests.factories import ImageFactory


def _ordered_images(count: int) -> list[models.Image]:
    """
    Build *count* images whose newest-first order is the returned list order.

    ``get_image_detail`` orders by ``-taken_at``, so a decreasing ``taken_at``
    makes the first image the newest and keeps the sequence deterministic.
    """
    base = dj_tz.now()
    return [ImageFactory(taken_at=base - timedelta(minutes=i)) for i in range(count)]


@pytest.mark.django_db
class TestGetImageDetailNeighbours:
    def test_middle_image_has_both_one_and_two_step_neighbours(self):
        images = _ordered_images(5)

        detail = get_image_detail(image_id=images[2].pk, active_filters={}, rating_first=False)

        assert detail.prev_id == images[1].pk
        assert detail.next_id == images[3].pk
        assert detail.prev2_id == images[0].pk
        assert detail.next2_id == images[4].pk

    def test_first_image_has_no_previous_neighbours(self):
        images = _ordered_images(5)

        detail = get_image_detail(image_id=images[0].pk, active_filters={}, rating_first=False)

        assert detail.prev_id is None
        assert detail.prev2_id is None
        assert detail.next_id == images[1].pk
        assert detail.next2_id == images[2].pk

    def test_second_image_has_a_previous_but_no_two_step_previous(self):
        images = _ordered_images(5)

        detail = get_image_detail(image_id=images[1].pk, active_filters={}, rating_first=False)

        assert detail.prev_id == images[0].pk
        assert detail.prev2_id is None
        assert detail.next2_id == images[3].pk

    def test_last_image_has_no_next_neighbours(self):
        images = _ordered_images(5)

        detail = get_image_detail(image_id=images[4].pk, active_filters={}, rating_first=False)

        assert detail.next_id is None
        assert detail.next2_id is None
        assert detail.prev_id == images[3].pk
        assert detail.prev2_id == images[2].pk

    def test_second_to_last_image_has_a_next_but_no_two_step_next(self):
        images = _ordered_images(5)

        detail = get_image_detail(image_id=images[3].pk, active_filters={}, rating_first=False)

        assert detail.next_id == images[4].pk
        assert detail.next2_id is None
        assert detail.prev2_id == images[1].pk
