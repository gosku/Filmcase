from datetime import datetime, timezone as tz

import pytest

from src.application.usecases.recipes.get_recipe_distribution import (
    InvalidDurationError,
    RecipeDistributionContext,
    RecipeNotFoundError,
    RecipeNotInVersionLineError,
    _CURRENT_COLOR,
    get_recipe_distribution,
)
from src.domain.images.queries import Duration
from tests.factories import (
    FujifilmRecipeFactory,
    ImageFactory,
    RecipeGroupFactory,
    RecipeGroupMemberFactory,
)


def _make_version_line(recipes_with_names):
    group = RecipeGroupFactory()
    members = []
    for i, (recipe, name) in enumerate(recipes_with_names, start=1):
        recipe.name = name
        recipe.save()
        members.append(RecipeGroupMemberFactory(group=group, recipe=recipe, position=i))
    return group, members


@pytest.mark.django_db
class TestGetRecipeDistribution:
    def test_returns_recipe_distribution_context(self):
        recipe = FujifilmRecipeFactory()
        _make_version_line([(recipe, "v1 name")])

        result = get_recipe_distribution(recipe_id=recipe.pk)

        assert isinstance(result, RecipeDistributionContext)

    def test_current_version_gets_current_color(self):
        recipe = FujifilmRecipeFactory()
        _make_version_line([(recipe, "")])

        result = get_recipe_distribution(recipe_id=recipe.pk)

        current = next(v for v in result.versions if v.is_current)
        assert current.color == _CURRENT_COLOR

    def test_other_versions_get_non_current_color(self):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        _make_version_line([(recipe_v1, "v1"), (recipe_v2, "v2")])

        result = get_recipe_distribution(recipe_id=recipe_v2.pk)

        non_current = next(v for v in result.versions if not v.is_current)
        assert non_current.color != _CURRENT_COLOR

    def test_buckets_span_all_recipes_in_version_line(self):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        _make_version_line([(recipe_v1, "v1"), (recipe_v2, "v2")])
        ImageFactory(fujifilm_recipe=recipe_v1, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe_v2, taken_at=datetime(2024, 3, 1, tzinfo=tz.utc))

        result = get_recipe_distribution(recipe_id=recipe_v2.pk)

        all_labels = {b.label for b in result.buckets}
        assert len(all_labels) == 2  # Jan and Mar buckets

    def test_total_images_sums_across_all_versions(self):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        _make_version_line([(recipe_v1, "v1"), (recipe_v2, "v2")])
        ImageFactory(fujifilm_recipe=recipe_v1, taken_at=datetime(2024, 1, 1, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe_v1, taken_at=datetime(2024, 1, 2, tzinfo=tz.utc))
        ImageFactory(fujifilm_recipe=recipe_v2, taken_at=datetime(2024, 2, 1, tzinfo=tz.utc))

        result = get_recipe_distribution(recipe_id=recipe_v1.pk)

        assert result.total_images == 3

    def test_scale_is_preserved_on_returned_context(self):
        recipe = FujifilmRecipeFactory()
        _make_version_line([(recipe, "")])

        result = get_recipe_distribution(recipe_id=recipe.pk, duration="week")

        assert result.scale == Duration.WEEK

    def test_default_scale_is_month_when_duration_is_none(self):
        recipe = FujifilmRecipeFactory()
        _make_version_line([(recipe, "")])

        result = get_recipe_distribution(recipe_id=recipe.pk)

        assert result.scale == Duration.MONTH

    def test_recipe_id_is_preserved_on_returned_context(self):
        recipe = FujifilmRecipeFactory()
        _make_version_line([(recipe, "")])

        result = get_recipe_distribution(recipe_id=recipe.pk)

        assert result.recipe_id == recipe.pk

    def test_versions_contain_correct_labels(self):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        _make_version_line([(recipe_v1, ""), (recipe_v2, "")])

        result = get_recipe_distribution(recipe_id=recipe_v1.pk)

        labels = [v.label for v in result.versions]
        assert labels == ["v1", "v2"]


@pytest.mark.django_db
class TestGetRecipeDistributionExceptions:
    def test_raises_invalid_duration_error_for_unrecognised_duration(self):
        recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(recipe=recipe, position=1)

        with pytest.raises(InvalidDurationError) as exc_info:
            get_recipe_distribution(recipe_id=recipe.pk, duration="daily")

        assert exc_info.value.duration == "daily"

    def test_raises_recipe_not_found_error_when_recipe_does_not_exist(self):
        with pytest.raises(RecipeNotFoundError) as exc_info:
            get_recipe_distribution(recipe_id=99999)

        assert exc_info.value.recipe_id == 99999

    def test_raises_recipe_not_in_version_line_error_when_recipe_has_no_group(self):
        recipe = FujifilmRecipeFactory()

        with pytest.raises(RecipeNotInVersionLineError) as exc_info:
            get_recipe_distribution(recipe_id=recipe.pk)

        assert exc_info.value.recipe_id == recipe.pk
