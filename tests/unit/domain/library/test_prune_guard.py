import pytest

from src.domain.library.operations import prune_guard_trips


@pytest.fixture(autouse=True)
def _default_thresholds(settings):
    settings.LIBRARY_PRUNE_GUARD_FRACTION = 0.5
    settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 20


class TestPruneGuardTrips:
    @pytest.mark.parametrize(
        ("missing", "total"),
        [
            (21, 40),  # over both thresholds
            (25, 25),  # the whole of a folder large enough to matter
            (5000, 5000),
        ],
    )
    def test_trips_when_both_thresholds_are_exceeded(self, missing, total):
        assert prune_guard_trips(missing=missing, total=total) is True

    @pytest.mark.parametrize(
        ("missing", "total"),
        [
            (20, 40),  # exactly at the minimum, so not over it
            (15, 15),  # a small folder emptied entirely is an ordinary cleanup
            (0, 100),
        ],
    )
    def test_stays_clear_when_too_few_images_would_go(self, missing, total):
        assert prune_guard_trips(missing=missing, total=total) is False

    @pytest.mark.parametrize(
        ("missing", "total"),
        [
            (21, 100),  # well under the fraction
            (50, 100),  # exactly at the fraction, so not over it
        ],
    )
    def test_stays_clear_when_the_share_is_not_exceeded(self, missing, total):
        assert prune_guard_trips(missing=missing, total=total) is False

    def test_stays_clear_for_a_folder_with_no_catalogued_images(self):
        assert prune_guard_trips(missing=0, total=0) is False

    def test_honours_a_reconfigured_fraction(self, settings):
        settings.LIBRARY_PRUNE_GUARD_FRACTION = 0.9
        settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1

        assert prune_guard_trips(missing=60, total=100) is False
        assert prune_guard_trips(missing=95, total=100) is True
