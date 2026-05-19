from datetime import datetime, timezone as tz

import pytest

from src.domain.images.queries import (
    BucketCount,
    Duration,
    RecipeImageDistribution,
    get_number_images_aggregated_by,
)
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetNumberImagesAggregatedBy:
    def test_returns_empty_tuple_when_recipe_ids_is_empty(self):
        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[])

        assert result == ()

    def test_returns_single_entry_with_empty_buckets_when_recipe_has_no_images(self):
        recipe = FujifilmRecipeFactory()

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe.pk])

        assert len(result) == 1
        assert result[0].recipe_id == recipe.pk
        assert result[0].buckets == ()

    def test_returns_correct_count_for_single_recipe_bucketed_by_month(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 10, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 25, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 4, 5, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe.pk])

        assert len(result) == 1
        buckets = result[0].buckets
        assert len(buckets) == 2
        assert buckets[0].count == 2  # March
        assert buckets[1].count == 1  # April

    def test_returns_correct_count_for_single_recipe_bucketed_by_year(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2023, 6, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 12, 31, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.YEAR, recipe_ids=[recipe.pk])

        buckets = result[0].buckets
        assert len(buckets) == 2
        assert buckets[0].count == 1  # 2023
        assert buckets[1].count == 2  # 2024

    def test_returns_correct_count_for_single_recipe_bucketed_by_week(self):
        recipe = FujifilmRecipeFactory()
        # ISO week 10 of 2024 starts 2024-03-04
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 4, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 5, tzinfo=tz.utc))
        # ISO week 11 starts 2024-03-11
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 11, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.WEEK, recipe_ids=[recipe.pk])

        buckets = result[0].buckets
        assert len(buckets) == 2
        assert buckets[0].count == 2
        assert buckets[1].count == 1

    def test_returns_one_entry_per_recipe_id_when_multiple_recipes_given(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_a, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe_b, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(
            duration=Duration.MONTH, recipe_ids=[recipe_a.pk, recipe_b.pk]
        )

        assert len(result) == 2
        assert {r.recipe_id for r in result} == {recipe_a.pk, recipe_b.pk}

    def test_excludes_images_where_taken_at_is_null(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, taken_at=None)
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe.pk])

        assert result[0].buckets[0].count == 1

    def test_buckets_are_ordered_chronologically(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 6, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe.pk])

        dts = [bc.bucket_dt for bc in result[0].buckets]
        assert dts == sorted(dts)

    def test_images_from_other_recipes_do_not_pollute_counts(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_a, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe_b, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe_a.pk])

        assert result[0].buckets[0].count == 1

    def test_preserves_recipe_id_order_in_result(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()

        result = get_number_images_aggregated_by(
            duration=Duration.MONTH, recipe_ids=[recipe_a.pk, recipe_b.pk]
        )

        assert result[0].recipe_id == recipe_a.pk
        assert result[1].recipe_id == recipe_b.pk

    def test_bucket_count_has_correct_type(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))

        result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[recipe.pk])

        assert isinstance(result[0], RecipeImageDistribution)
        assert isinstance(result[0].buckets[0], BucketCount)
