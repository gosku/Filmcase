from datetime import datetime, timezone

import pytest
from django.test import override_settings
from django.urls import reverse

from src.domain.images import timeline_queries
from tests.factories import FujifilmRecipeFactory, ImageFactory

pytestmark = pytest.mark.django_db


def _dt(year: int, month: int, day: int = 15) -> datetime:
    return datetime(year, month, day, 12, tzinfo=timezone.utc)


class TestGalleryPageDateState:
    def test_full_page_load_with_a_date_lands_on_that_month(self, client):
        target = ImageFactory(taken_at=_dt(2020, 12, 10))
        newer = ImageFactory(taken_at=_dt(2026, 1))

        content = client.get(reverse("gallery"), {"to_date": "2020-12"}).content.decode()

        assert f'data-pk="{target.pk}"' in content
        assert f'data-pk="{newer.pk}"' not in content  # newer is above, reachable by scrolling up
        assert '"focus": "2020-12"' in content
        assert 'id="to-date-input"' in content
        assert 'value="2020-12"' in content
        assert "sentinel-newer" in content  # there are newer photos to scroll up into

    def test_full_page_load_with_a_filter_and_a_date(self, client):
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        target = ImageFactory(taken_at=_dt(2023, 6, 5), fujifilm_recipe=velvia)
        ImageFactory(taken_at=_dt(2023, 6, 5), fujifilm_recipe=provia)  # same month, filtered out

        content = client.get(
            reverse("gallery"), {"film_simulation": "Velvia", "to_date": "2023-06"}
        ).content.decode()

        assert f'data-pk="{target.pk}"' in content
        assert '"focus": "2023-06"' in content
        assert '"total": 1' in content  # rail scoped to the Velvia set

    def test_invalid_date_falls_back_to_newest_without_erroring(self, client):
        newest = ImageFactory(taken_at=_dt(2026, 5))

        response = client.get(reverse("gallery"), {"to_date": "banana"})

        assert response.status_code == 200
        content = response.content.decode()
        assert f'data-pk="{newest.pk}"' in content
        assert '"focus": null' in content
        assert 'id="to-date-input"' in content
        assert 'value=""' in content


class TestGalleryRendersTimeline:
    def test_renders_the_rail_and_distribution_data(self, client):
        ImageFactory(taken_at=_dt(2026, 3))
        ImageFactory(taken_at=_dt(2026, 1))

        content = client.get(reverse("gallery")).content.decode()

        assert 'id="timeline-rail"' in content
        assert 'id="timeline-data"' in content
        assert "gallery-timeline.js" in content
        assert '"months"' in content

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_shows_an_older_sentinel_but_no_newer_at_the_newest_page(self, client):
        for month in (1, 2, 3):
            ImageFactory(taken_at=_dt(2026, month))

        content = client.get(reverse("gallery")).content.decode()

        assert 'id="load-older-sentinel"' in content
        assert 'id="load-newer-sentinel"' in content
        assert '"direction": "older"' in content
        # At the newest page there is nothing newer, so no active newer trigger.
        assert "sentinel-newer" not in content


class TestGalleryResultsKeyset:
    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_scroll_older_returns_the_next_older_page(self, client):
        newest = ImageFactory(taken_at=_dt(2026, 3))
        middle = ImageFactory(taken_at=_dt(2026, 2))
        oldest = ImageFactory(taken_at=_dt(2026, 1))
        cursor = timeline_queries.encode_cursor(image=newest)

        content = client.get(
            reverse("gallery-results"), {"direction": "older", "cursor": cursor}
        ).content.decode()

        assert f'data-pk="{middle.pk}"' in content
        assert f'data-pk="{oldest.pk}"' in content
        assert f'data-pk="{newest.pk}"' not in content
        assert 'hx-swap-oob="beforeend:#gallery-results"' in content

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_scroll_newer_prepends_newer_rows(self, client):
        newest = ImageFactory(taken_at=_dt(2026, 3))
        oldest = ImageFactory(taken_at=_dt(2026, 1))
        cursor = timeline_queries.encode_cursor(image=oldest)

        content = client.get(
            reverse("gallery-results"), {"direction": "newer", "cursor": cursor}
        ).content.decode()

        assert f'data-pk="{newest.pk}"' in content
        assert 'hx-swap-oob="afterbegin:#gallery-results"' in content

    def test_invalid_cursor_is_rejected(self, client):
        response = client.get(reverse("gallery-results"), {"direction": "older", "cursor": "garbage!!"})

        assert response.status_code == 400

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_scroll_pages_from_the_cursor_even_when_a_date_is_present(self, client):
        # The scroll sentinels include the whole filter-form, so to_date rides
        # along; it must not re-land the jump — the cursor must win.
        newest = ImageFactory(taken_at=_dt(2026, 3))
        middle = ImageFactory(taken_at=_dt(2026, 2))
        oldest = ImageFactory(taken_at=_dt(2026, 1))
        cursor = timeline_queries.encode_cursor(image=newest)

        content = client.get(
            reverse("gallery-results"),
            {"direction": "older", "cursor": cursor, "to_date": "2026-03"},
        ).content.decode()

        # Paged from the cursor (older than `newest`), not re-landed at 2026-03.
        assert f'data-pk="{middle.pk}"' in content
        assert f'data-pk="{oldest.pk}"' in content
        assert 'hx-swap-oob="beforeend:#gallery-results"' in content


class TestGalleryResultsJump:
    def test_jump_lands_on_the_target_month_and_resets_sentinels(self, client):
        target = ImageFactory(taken_at=_dt(2020, 12, 10))
        newer = ImageFactory(taken_at=_dt(2026, 1))

        content = client.get(reverse("gallery-results"), {"to_date": "2020-12"}).content.decode()

        assert f'data-pk="{target.pk}"' in content
        assert f'data-pk="{newer.pk}"' not in content
        # Both sentinels reset out-of-band; newer is active (there are newer photos).
        assert 'id="load-older-sentinel" hx-swap-oob="true"' in content
        assert 'id="load-newer-sentinel" hx-swap-oob="true"' in content
        assert "sentinel-newer" in content

    def test_invalid_to_date_is_rejected(self, client):
        response = client.get(reverse("gallery-results"), {"to_date": "not-a-month"})

        assert response.status_code == 400


class TestTimelineTracksFilters:
    def test_filter_change_recomputes_the_distribution(self, client):
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(taken_at=_dt(2026, 3), fujifilm_recipe=velvia)
        ImageFactory(taken_at=_dt(2020, 1), fujifilm_recipe=provia)

        content = client.get(
            reverse("gallery"),
            {"film_simulation": "Velvia"},
            HTTP_HX_REQUEST="true",
        ).content.decode()

        # OOB rail refresh, scoped to the Velvia-filtered set (one image, March 2026).
        assert 'id="timeline-rail"' in content
        assert 'hx-swap-oob="true"' in content
        assert '"total": 1' in content
        assert '"month": 3' in content
