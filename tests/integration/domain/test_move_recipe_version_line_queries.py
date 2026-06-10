import pytest

from src.domain.recipes.queries import (
    RecipeMoveCandidate,
    RecipeNotInVersionLineError,
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
