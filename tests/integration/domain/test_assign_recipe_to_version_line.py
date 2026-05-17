import time_machine
import pytest

from src.data import models
from src.domain.recipes.operations import (
    VersionLineGroupNotFoundError,
    add_recipe_to_version_line,
)
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory


@pytest.mark.django_db
class TestAddRecipeToVersionLine:

    # ── No group given: creates a new group ──────────────────────────────────

    def test_creates_new_version_line_group_when_no_group_given(self) -> None:
        recipe = FujifilmRecipeFactory()

        add_recipe_to_version_line(recipe=recipe, group_id=None)

        assert models.RecipeGroup.objects.filter(
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE
        ).count() == 1

    def test_member_is_at_position_1_when_no_group_given(self) -> None:
        recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=recipe, group_id=None)

        assert member.position == 1

    def test_member_group_type_matches_group(self) -> None:
        recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=recipe, group_id=None)

        assert member.group_type == member.group.group_type

    def test_returns_the_created_member(self) -> None:
        recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=recipe, group_id=None)

        assert isinstance(member, models.RecipeGroupMember)
        assert member.pk is not None
        assert member.recipe_id == recipe.pk

    @time_machine.travel("2026-05-15 12:00:00", tick=False)
    def test_added_at_is_set_to_current_time(self) -> None:
        from django.utils import timezone

        recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=recipe, group_id=None)

        assert member.added_at == timezone.now()

    # ── Group given: appends to existing group ────────────────────────────────

    def test_appends_to_existing_group_when_group_id_given(self) -> None:
        reference_member = RecipeGroupMemberFactory(position=1)
        new_recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=new_recipe, group_id=reference_member.group_id)

        assert member.group_id == reference_member.group_id

    def test_new_member_position_is_one_after_the_current_latest(self) -> None:
        reference_member = RecipeGroupMemberFactory(position=1)
        new_recipe = FujifilmRecipeFactory()

        member = add_recipe_to_version_line(recipe=new_recipe, group_id=reference_member.group_id)

        assert member.position == 2

    def test_next_position_follows_the_latest_member_not_the_first(self) -> None:
        group = RecipeGroupFactory()
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        recipe_v3 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=group, recipe=recipe_v1, position=1)
        RecipeGroupMemberFactory(group=group, recipe=recipe_v2, position=2)

        member = add_recipe_to_version_line(recipe=recipe_v3, group_id=group.pk)

        assert member.position == 3

    def test_no_new_group_is_created_when_group_id_given(self) -> None:
        reference_member = RecipeGroupMemberFactory(position=1)
        new_recipe = FujifilmRecipeFactory()

        add_recipe_to_version_line(recipe=new_recipe, group_id=reference_member.group_id)

        assert models.RecipeGroup.objects.count() == 1

    # ── Error: group not found ────────────────────────────────────────────────

    def test_raises_when_group_id_does_not_exist(self) -> None:
        recipe = FujifilmRecipeFactory()

        with pytest.raises(VersionLineGroupNotFoundError) as exc_info:
            add_recipe_to_version_line(recipe=recipe, group_id=99999)

        assert exc_info.value.group_id == 99999

    def test_raises_when_group_is_a_family_group_not_a_version_line(self) -> None:
        family_group = RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_FAMILY)
        recipe = FujifilmRecipeFactory()

        with pytest.raises(VersionLineGroupNotFoundError):
            add_recipe_to_version_line(recipe=recipe, group_id=family_group.pk)
