from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.data import models
from src.domain.images import timeline_queries
from src.domain.images.timeline_queries import Direction
from tests import factories

pytestmark = pytest.mark.django_db


def _dt(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _img(taken_at: datetime | None, *, rating: int = 0, recipe: object = None) -> models.Image:
    return factories.ImageFactory(taken_at=taken_at, rating=rating, fujifilm_recipe=recipe)


class TestGetImagesPage:
    def test_initial_page_returns_newest_first(self) -> None:
        old = _img(_dt(2020, 1, 1))
        mid = _img(_dt(2023, 6, 1))
        new = _img(_dt(2026, 3, 1))

        page = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=None, direction=Direction.OLDER, limit=10
        )

        assert [i.pk for i in page.images] == [new.pk, mid.pk, old.pk]
        assert page.has_newer is False
        assert page.has_older is False

    def test_older_paging_is_continuous_and_non_overlapping(self) -> None:
        images = [_img(_dt(2026, m, 1)) for m in range(1, 7)]  # Jan..Jun 2026

        first = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=None, direction=Direction.OLDER, limit=3
        )
        second = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=first.older_cursor, direction=Direction.OLDER, limit=3
        )

        newest_to_oldest = [i.pk for i in reversed(images)]
        assert [i.pk for i in first.images] == newest_to_oldest[:3]
        assert first.has_older is True
        assert [i.pk for i in second.images] == newest_to_oldest[3:]
        assert second.has_older is False

    def test_newer_paging_returns_newer_rows_in_natural_order(self) -> None:
        images = [_img(_dt(2026, m, 1)) for m in range(1, 7)]  # Jan..Jun 2026

        bottom = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=None, direction=Direction.OLDER, limit=3
        )  # Jun, May, Apr
        up = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=bottom.older_cursor, direction=Direction.NEWER, limit=2
        )

        # older_cursor of the first page points at Apr; scrolling up yields Jun, May.
        assert [i.pk for i in up.images] == [images[5].pk, images[4].pk]
        assert up.has_older is True

    def test_ties_broken_by_id(self) -> None:
        same = _dt(2026, 3, 1)
        a = _img(same)
        b = _img(same)

        page = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=None, direction=Direction.OLDER, limit=10
        )

        # Same taken_at: id ascending is the tiebreak, so lower id comes first.
        assert [i.pk for i in page.images] == [a.pk, b.pk]

    def test_undated_images_sort_after_dated_and_stay_reachable(self) -> None:
        dated = _img(_dt(2026, 1, 1))
        undated = _img(None)

        first = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=None, direction=Direction.OLDER, limit=1
        )
        second = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=first.older_cursor, direction=Direction.OLDER, limit=1
        )

        assert [i.pk for i in first.images] == [dated.pk]
        assert [i.pk for i in second.images] == [undated.pk]
        assert second.has_older is False


class TestRatingFirst:
    def test_region_is_the_unrated_tail(self) -> None:
        rated = _img(_dt(2026, 5, 1), rating=5)
        unrated_new = _img(_dt(2026, 4, 1), rating=0)
        unrated_old = _img(_dt(2020, 1, 1), rating=0)

        page = timeline_queries.get_images_page(
            active_filters={}, rating_first=True, cursor=None, direction=Direction.OLDER, limit=10
        )

        # Rated photos lead; the whole gallery still lists them first.
        assert [i.pk for i in page.images] == [rated.pk, unrated_new.pk, unrated_old.pk]

    def test_jump_lands_in_the_unrated_tail_after_rated(self) -> None:
        rated_dec = _img(_dt(2020, 12, 20), rating=4)
        unrated_dec = _img(_dt(2020, 12, 10), rating=0)
        _img(_dt(2026, 1, 1), rating=0)  # newer unrated, should not be in the landing

        page = timeline_queries.get_images_from_date(
            active_filters={}, rating_first=True, target=_dt(2021, 1, 1, 0), limit=10
        )

        assert [i.pk for i in page.images] == [unrated_dec.pk]
        assert rated_dec.pk not in [i.pk for i in page.images]
        assert page.has_newer is True


class TestGetImagesFromDate:
    def test_lands_at_newest_in_target_month(self) -> None:
        _img(_dt(2026, 1, 1))
        dec_early = _img(_dt(2020, 12, 5))
        dec_late = _img(_dt(2020, 12, 28))
        _img(_dt(2019, 6, 1))

        page = timeline_queries.get_images_from_date(
            active_filters={}, rating_first=False, target=_dt(2021, 1, 1, 0), limit=1
        )

        assert [i.pk for i in page.images] == [dec_late.pk]
        assert page.has_older is True
        assert page.has_newer is True
        # older_cursor continues into December, then earlier months.
        older = timeline_queries.get_images_page(
            active_filters={}, rating_first=False, cursor=page.older_cursor, direction=Direction.OLDER, limit=1
        )
        assert [i.pk for i in older.images] == [dec_early.pk]

    def test_empty_month_lands_at_closest_earlier_image(self) -> None:
        _img(_dt(2026, 1, 1))
        earlier = _img(_dt(2020, 8, 1))  # nothing in Dec 2020

        page = timeline_queries.get_images_from_date(
            active_filters={}, rating_first=False, target=_dt(2021, 1, 1, 0), limit=1
        )

        assert [i.pk for i in page.images] == [earlier.pk]


class TestGetTimelineDistribution:
    def test_counts_images_per_month(self) -> None:
        _img(_dt(2026, 3, 1))
        _img(_dt(2026, 3, 20))
        _img(_dt(2026, 1, 5))

        dist = timeline_queries.get_timeline_distribution(
            active_filters={}, rating_first=False, tz=ZoneInfo("UTC")
        )

        assert dist.months == (
            timeline_queries.TimelineMonth(year=2026, month=3, count=2),
            timeline_queries.TimelineMonth(year=2026, month=1, count=1),
        )
        assert dist.total == 3
        assert dist.undated_count == 0

    def test_reports_undated_separately(self) -> None:
        _img(_dt(2026, 3, 1))
        _img(None)
        _img(None)

        dist = timeline_queries.get_timeline_distribution(
            active_filters={}, rating_first=False, tz=ZoneInfo("UTC")
        )

        assert dist.total == 1
        assert dist.undated_count == 2

    def test_truncates_months_in_the_given_timezone(self) -> None:
        # 00:30 UTC on 1 March is still February in New York (UTC-5).
        _img(datetime(2026, 3, 1, 0, 30, tzinfo=timezone.utc))

        utc = timeline_queries.get_timeline_distribution(
            active_filters={}, rating_first=False, tz=ZoneInfo("UTC")
        )
        ny = timeline_queries.get_timeline_distribution(
            active_filters={}, rating_first=False, tz=ZoneInfo("America/New_York")
        )

        assert utc.months[0] == timeline_queries.TimelineMonth(year=2026, month=3, count=1)
        assert ny.months[0] == timeline_queries.TimelineMonth(year=2026, month=2, count=1)

    def test_rating_first_distribution_covers_only_the_unrated_tail(self) -> None:
        _img(_dt(2026, 3, 1), rating=5)
        _img(_dt(2026, 3, 2), rating=0)

        dist = timeline_queries.get_timeline_distribution(
            active_filters={}, rating_first=True, tz=ZoneInfo("UTC")
        )

        assert dist.total == 1
        assert dist.months == (timeline_queries.TimelineMonth(year=2026, month=3, count=1),)

    def test_respects_recipe_filters(self) -> None:
        provia = factories.FujifilmRecipeFactory(film_simulation="Provia")
        velvia = factories.FujifilmRecipeFactory(film_simulation="Velvia")
        _img(_dt(2026, 3, 1), recipe=provia)
        _img(_dt(2026, 3, 2), recipe=velvia)

        dist = timeline_queries.get_timeline_distribution(
            active_filters={"film_simulation": ["Velvia"]}, rating_first=False, tz=ZoneInfo("UTC")
        )

        assert dist.total == 1
        assert dist.months == (timeline_queries.TimelineMonth(year=2026, month=3, count=1),)
