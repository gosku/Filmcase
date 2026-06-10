from unittest.mock import patch

import pytest

from src.application.usecases.recipes.get_move_preview_distribution import (
    InvalidDurationError,
    RecipeDistributionContext,
    VersionLineGroupNotFoundError,
    get_move_preview_distribution,
)
from src.domain.recipes import queries as recipe_queries
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory

_USE_CASE = "src.application.usecases.recipes.get_move_preview_distribution"


@pytest.mark.django_db
class TestGetMovePreviewDistributionHappyPath:

    def test_returns_recipe_distribution_context(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Provia A")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Provia B")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_move_preview_distribution(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        assert isinstance(result, RecipeDistributionContext)

    def test_source_recipe_is_current_in_result(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Provia A")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Provia B")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_move_preview_distribution(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        current_versions = [v for v in result.versions if v.is_current]
        assert len(current_versions) == 1
        assert current_versions[0].recipe_id == source_recipe.pk

    def test_context_recipe_id_is_source_recipe(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Acros A")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Acros B")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_move_preview_distribution(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        assert result.recipe_id == source_recipe.pk

    def test_destination_recipes_included_in_versions(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Eterna A")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Eterna B")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_move_preview_distribution(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        version_ids = {v.recipe_id for v in result.versions}
        assert dest_recipe.pk in version_ids
        assert source_recipe.pk in version_ids


class TestGetMovePreviewDistributionErrors:

    def test_raises_invalid_duration_error_for_bad_duration(self) -> None:
        with pytest.raises(InvalidDurationError) as exc_info:
            get_move_preview_distribution(
                source_recipe_id=1,
                destination_group_id=1,
                duration="bad_duration",
            )

        assert exc_info.value.duration == "bad_duration"

    def test_translates_version_line_group_not_found_error(self) -> None:
        exc = recipe_queries.VersionLineGroupNotFoundError(group_id=99)
        with (
            patch(
                f"{_USE_CASE}.recipe_queries.get_simulated_version_line_members",
                side_effect=exc,
            ),
            pytest.raises(VersionLineGroupNotFoundError) as exc_info,
        ):
            get_move_preview_distribution(
                source_recipe_id=1,
                destination_group_id=99,
            )

        assert exc_info.value.group_id == 99
