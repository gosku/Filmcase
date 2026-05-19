from unittest.mock import patch

import pytest

from datetime import datetime

from src.application.usecases.recipes.get_recipe_distribution import (
    _CURRENT_COLOR,
    _VERSION_COLORS,
    InvalidDurationError,
    RecipeNotFoundError,
    RecipeNotInVersionLineError,
    _align_counts,
    _build_versions,
    _ordered_buckets,
    get_recipe_distribution,
)
from src.data import models
from src.domain.images import queries as image_queries
from src.domain.images.queries import Duration
from src.domain.recipes import queries as recipe_queries


class TestGetRecipeDistributionExceptions:
    def test_raises_invalid_duration_error_for_unrecognised_duration_string(self):
        with pytest.raises(InvalidDurationError) as exc_info:
            get_recipe_distribution(recipe_id=1, duration="daily")

        assert exc_info.value.duration == "daily"

    def test_raises_recipe_not_found_error_when_recipe_detail_raises_does_not_exist(self):
        with patch("src.application.usecases.recipes.get_recipe_distribution.recipe_queries") as mock_rq:
            mock_rq.get_recipe_detail.side_effect = models.FujifilmRecipe.DoesNotExist

            with pytest.raises(RecipeNotFoundError) as exc_info:
                get_recipe_distribution(recipe_id=99)

        assert exc_info.value.recipe_id == 99

    def test_raises_recipe_not_in_version_line_error_when_version_line_query_raises(self):
        with patch("src.application.usecases.recipes.get_recipe_distribution.recipe_queries") as mock_rq:
            mock_rq.get_recipe_detail.return_value = object()
            mock_rq.get_recipes_in_version_line.side_effect = (
                recipe_queries.RecipeNotInVersionLineError(recipe_id=7)
            )

            with pytest.raises(RecipeNotInVersionLineError) as exc_info:
                get_recipe_distribution(recipe_id=7)

        assert exc_info.value.recipe_id == 7

    def test_image_query_not_called_when_duration_is_invalid(self):
        with patch("src.application.usecases.recipes.get_recipe_distribution.image_queries") as mock_iq:
            with pytest.raises(InvalidDurationError):
                get_recipe_distribution(recipe_id=1, duration="bad")

        mock_iq.get_number_images_aggregated_by.assert_not_called()

    def test_default_duration_is_month_when_none_is_passed(self):
        with patch("src.application.usecases.recipes.get_recipe_distribution.recipe_queries") as mock_rq:
            mock_rq.get_recipe_detail.side_effect = models.FujifilmRecipe.DoesNotExist

            with pytest.raises(RecipeNotFoundError):
                get_recipe_distribution(recipe_id=1, duration=None)

        # The fact that recipe_queries.get_recipe_detail was called proves duration
        # validation passed (i.e. Duration.MONTH was used as default).
        mock_rq.get_recipe_detail.assert_called_once_with(recipe_id=1)


def _version_recipe(recipe_id, position, is_current):
    return recipe_queries.VersionLineRecipe(
        recipe_id=recipe_id,
        position=position,
        label=f"v{position}",
        name=f"Recipe {recipe_id}",
        is_current=is_current,
    )


def _distribution(recipe_id, buckets):
    return image_queries.RecipeImageDistribution(
        recipe_id=recipe_id,
        buckets=tuple(
            image_queries.BucketCount(bucket=label, bucket_dt=dt, count=count)
            for dt, label, count in buckets
        ),
    )


class TestBuildVersions:
    def test_current_recipe_gets_the_highlight_colour(self):
        versions = _build_versions(
            version_recipes=[_version_recipe(10, 1, is_current=True)],
            distributions=[],
        )

        assert versions[0].color == _CURRENT_COLOR

    def test_non_current_versions_cycle_the_palette_without_current_consuming_a_slot(self):
        versions = _build_versions(
            version_recipes=[
                _version_recipe(10, 1, is_current=False),
                _version_recipe(20, 2, is_current=True),
                _version_recipe(30, 3, is_current=False),
            ],
            distributions=[],
        )

        assert [v.color for v in versions] == [
            _VERSION_COLORS[0],
            _CURRENT_COLOR,
            _VERSION_COLORS[1],
        ]

    def test_image_count_sums_the_versions_buckets(self):
        dt = datetime(2024, 1, 1)
        versions = _build_versions(
            version_recipes=[_version_recipe(10, 1, is_current=False)],
            distributions=[_distribution(10, [(dt, "Jan 24", 3), (dt, "Feb 24", 5)])],
        )

        assert versions[0].image_count == 8

    def test_image_count_is_zero_when_version_has_no_distribution(self):
        versions = _build_versions(
            version_recipes=[_version_recipe(10, 1, is_current=False)],
            distributions=[],
        )

        assert versions[0].image_count == 0


class TestOrderedBuckets:
    def test_deduplicates_and_sorts_periods_chronologically_across_versions(self):
        jan = datetime(2023, 1, 1)
        jun = datetime(2024, 6, 1)
        dec = datetime(2025, 12, 1)
        ordered = _ordered_buckets([
            _distribution(10, [(jun, "Jun 24", 2), (jan, "Jan 23", 1)]),
            _distribution(20, [(dec, "Dec 25", 4), (jun, "Jun 24", 7)]),
        ])

        assert ordered == ((jan, "Jan 23"), (jun, "Jun 24"), (dec, "Dec 25"))

    def test_returns_empty_for_no_distributions(self):
        assert _ordered_buckets([]) == ()


class TestAlignCounts:
    def test_fills_zero_for_recipes_and_buckets_without_images(self):
        jan = datetime(2023, 1, 1)
        feb = datetime(2023, 2, 1)
        distributions = [
            _distribution(10, [(jan, "Jan 23", 4)]),
            _distribution(20, [(feb, "Feb 23", 9)]),
        ]

        buckets = _align_counts(
            ordered_buckets=[(jan, "Jan 23"), (feb, "Feb 23")],
            distributions=distributions,
            recipe_ids=[10, 20],
        )

        assert [(b.label, b.counts) for b in buckets] == [
            ("Jan 23", {10: 4, 20: 0}),
            ("Feb 23", {10: 0, 20: 9}),
        ]

    def test_preserves_bucket_order_and_includes_every_recipe_id(self):
        jan = datetime(2023, 1, 1)

        buckets = _align_counts(
            ordered_buckets=[(jan, "Jan 23")],
            distributions=[_distribution(10, [(jan, "Jan 23", 1)])],
            recipe_ids=[10, 20, 30],
        )

        assert buckets[0].counts == {10: 1, 20: 0, 30: 0}
