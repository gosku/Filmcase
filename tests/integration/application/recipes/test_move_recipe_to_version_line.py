from unittest.mock import patch

import pytest

from src.application.usecases.recipes.move_recipe_to_version_line import (
    CannotMoveToSameGroupError,
    InvalidVersionLinePositionError,
    RecipeNotInVersionLineError,
    VersionLineGroupNotFoundError,
    move_recipe_to_version_line,
)
from src.data import models
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import queries as recipe_queries
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory

_USE_CASE = "src.application.usecases.recipes.move_recipe_to_version_line"


@pytest.mark.django_db
class TestMoveRecipeToVersionLineHappyPath:

    def test_recipe_appears_in_destination_group(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk)

        assert models.RecipeGroupMember.objects.filter(
            recipe_id=recipe_x.pk, group=dest
        ).exists()

    def test_recipe_appears_at_given_position(self) -> None:
        source = RecipeGroupFactory()
        dest = RecipeGroupFactory()
        recipe_x = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source, recipe=recipe_x, position=1)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=dest, recipe=recipe_b, position=2)

        move_recipe_to_version_line(recipe_id=recipe_x.pk, destination_group_id=dest.pk, position=2)

        member = models.RecipeGroupMember.objects.get(recipe_id=recipe_x.pk, group=dest)
        assert member.position == 2


class TestMoveRecipeToVersionLineErrorTranslation:

    def test_translates_recipe_not_in_version_line_error(self) -> None:
        exc = recipe_queries.RecipeNotInVersionLineError(recipe_id=42)
        with (
            patch(f"{_USE_CASE}.recipe_operations.move_recipe_to_version_line", side_effect=exc),
            pytest.raises(RecipeNotInVersionLineError) as exc_info,
        ):
            move_recipe_to_version_line(recipe_id=42, destination_group_id=1)

        assert exc_info.value.recipe_id == 42

    def test_translates_version_line_group_not_found_error(self) -> None:
        exc = recipe_operations.VersionLineGroupNotFoundError(group_id=99)
        with (
            patch(f"{_USE_CASE}.recipe_operations.move_recipe_to_version_line", side_effect=exc),
            pytest.raises(VersionLineGroupNotFoundError) as exc_info,
        ):
            move_recipe_to_version_line(recipe_id=1, destination_group_id=99)

        assert exc_info.value.group_id == 99

    def test_translates_cannot_move_to_same_group_error(self) -> None:
        exc = recipe_operations.CannotMoveToSameGroupError(group_id=7)
        with (
            patch(f"{_USE_CASE}.recipe_operations.move_recipe_to_version_line", side_effect=exc),
            pytest.raises(CannotMoveToSameGroupError) as exc_info,
        ):
            move_recipe_to_version_line(recipe_id=1, destination_group_id=7)

        assert exc_info.value.group_id == 7

    def test_translates_invalid_version_line_position_error(self) -> None:
        exc = recipe_operations.InvalidVersionLinePositionError(position=10, max_position=3)
        with (
            patch(f"{_USE_CASE}.recipe_operations.move_recipe_to_version_line", side_effect=exc),
            pytest.raises(InvalidVersionLinePositionError) as exc_info,
        ):
            move_recipe_to_version_line(recipe_id=1, destination_group_id=2, position=10)

        assert exc_info.value.position == 10
        assert exc_info.value.max_position == 3
