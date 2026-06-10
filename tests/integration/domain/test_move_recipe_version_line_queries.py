import pytest

from src.domain.recipes.queries import (
    RecipeMoveCandidate,
    RecipeNotInVersionLineError,
    VersionLineGroupNotFoundError,
    get_simulated_version_line_members,
    search_recipes_for_version_line_move,
)
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory


@pytest.mark.django_db
class TestSearchRecipesForVersionLineMove:

    def test_returns_empty_tuple_for_blank_name_search(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Velvia Classic")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="",
        )

        assert result == ()

    def test_returns_empty_tuple_for_whitespace_only_name_search(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Velvia Classic")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="   ",
        )

        assert result == ()

    def test_returns_matching_recipes_from_other_groups(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Velvia Classic")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Velvia Street")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Velvia",
        )

        recipe_ids = [c.recipe_id for c in result]
        assert dest_recipe.pk in recipe_ids

    def test_excludes_recipes_in_source_group(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Velvia Classic")
        sibling_recipe = FujifilmRecipeFactory(name="Velvia Lush")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)
        RecipeGroupMemberFactory(group=source_group, recipe=sibling_recipe, position=2)

        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Velvia Street")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Velvia",
        )

        recipe_ids = [c.recipe_id for c in result]
        assert source_recipe.pk not in recipe_ids
        assert sibling_recipe.pk not in recipe_ids
        assert dest_recipe.pk in recipe_ids

    def test_search_is_case_insensitive(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Eterna Cinema")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Eterna Street")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="eterna",
        )

        assert any(c.recipe_id == dest_recipe.pk for c in result)

    def test_returns_candidate_with_correct_group_id(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Classic Neg")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Classic Neg v2")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Classic",
        )

        candidate = next(c for c in result if c.recipe_id == dest_recipe.pk)
        assert candidate.group_id == dest_group.pk

    def test_returns_candidate_with_group_member_count(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Provia Film")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory(name="Provia Film A")
        dest_r2 = FujifilmRecipeFactory(name="Provia Film B")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r2, position=2)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Provia",
        )

        for candidate in result:
            assert candidate.group_member_count == 2

    def test_returns_results_ordered_by_recipe_name(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Acros")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        recipe_beta = FujifilmRecipeFactory(name="Provia Beta")
        recipe_alpha = FujifilmRecipeFactory(name="Provia Alpha")
        RecipeGroupMemberFactory(group=dest_group, recipe=recipe_beta, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=recipe_alpha, position=2)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Provia",
        )

        names = [c.name for c in result]
        assert names == sorted(names)

    def test_raises_when_source_recipe_not_in_version_line(self) -> None:
        recipe = FujifilmRecipeFactory(name="Provia Classic")

        with pytest.raises(RecipeNotInVersionLineError) as exc_info:
            search_recipes_for_version_line_move(
                source_recipe_id=recipe.pk,
                name_search="Provia",
            )

        assert exc_info.value.recipe_id == recipe.pk

    def test_returns_at_most_30_results(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Zebra")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        for i in range(35):
            grp = RecipeGroupFactory()
            recipe = FujifilmRecipeFactory(name=f"Provia {i:02d}")
            RecipeGroupMemberFactory(group=grp, recipe=recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Provia",
        )

        assert len(result) == 30

    def test_returns_tuple_of_recipe_move_candidates(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Eterna")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        dest_group = RecipeGroupFactory()
        dest_recipe = FujifilmRecipeFactory(name="Eterna v2")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_recipe, position=1)

        result = search_recipes_for_version_line_move(
            source_recipe_id=source_recipe.pk,
            name_search="Eterna",
        )

        assert isinstance(result, tuple)
        assert all(isinstance(c, RecipeMoveCandidate) for c in result)


@pytest.mark.django_db
class TestGetSimulatedVersionLineMembers:

    def test_returns_version_line_result_with_source_recipe_appended_by_default(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory(name="Provia A")
        dest_r2 = FujifilmRecipeFactory(name="Provia B")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r2, position=2)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Provia C")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        recipe_ids = [vr.recipe_id for vr in result.recipes]
        assert recipe_ids == [dest_r1.pk, dest_r2.pk, source_recipe.pk]

    def test_source_recipe_inserted_at_given_position(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory(name="Provia A")
        dest_r2 = FujifilmRecipeFactory(name="Provia B")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r2, position=2)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Provia C")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
            position=2,
        )

        recipe_ids = [vr.recipe_id for vr in result.recipes]
        assert recipe_ids == [dest_r1.pk, source_recipe.pk, dest_r2.pk]

    def test_source_recipe_inserted_at_first_position(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory(name="Velvia A")
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory(name="Velvia B")
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
            position=1,
        )

        recipe_ids = [vr.recipe_id for vr in result.recipes]
        assert recipe_ids == [source_recipe.pk, dest_r1.pk]

    def test_positions_are_contiguous_after_insertion(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory()
        dest_r2 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r2, position=2)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
            position=2,
        )

        positions = [vr.position for vr in result.recipes]
        assert positions == [1, 2, 3]

    def test_source_recipe_is_marked_is_current(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        current_ids = [vr.recipe_id for vr in result.recipes if vr.is_current]
        assert current_ids == [source_recipe.pk]

    def test_destination_members_are_not_is_current(self) -> None:
        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory()
        dest_r2 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r2, position=2)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        result = get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        non_current = [vr for vr in result.recipes if vr.recipe_id != source_recipe.pk]
        assert all(not vr.is_current for vr in non_current)

    def test_does_not_modify_database(self) -> None:
        from src.data import models

        dest_group = RecipeGroupFactory()
        dest_r1 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=dest_group, recipe=dest_r1, position=1)

        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        get_simulated_version_line_members(
            source_recipe_id=source_recipe.pk,
            destination_group_id=dest_group.pk,
        )

        assert models.RecipeGroupMember.objects.filter(
            recipe_id=source_recipe.pk, group=source_group
        ).exists()

    def test_raises_when_destination_group_has_no_members(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        empty_group = RecipeGroupFactory()

        with pytest.raises(VersionLineGroupNotFoundError) as exc_info:
            get_simulated_version_line_members(
                source_recipe_id=source_recipe.pk,
                destination_group_id=empty_group.pk,
            )

        assert exc_info.value.group_id == empty_group.pk

    def test_raises_when_destination_group_does_not_exist(self) -> None:
        source_group = RecipeGroupFactory()
        source_recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=source_group, recipe=source_recipe, position=1)

        with pytest.raises(VersionLineGroupNotFoundError) as exc_info:
            get_simulated_version_line_members(
                source_recipe_id=source_recipe.pk,
                destination_group_id=99999,
            )

        assert exc_info.value.group_id == 99999
