import pytest

from src.data import models
from src.domain.recipes.queries import (
    RecipeNotInVersionLineError,
    VersionLineResult,
    get_recipes_in_version_line,
)
from tests.factories import (
    FujifilmRecipeFactory,
    RecipeGroupFactory,
    RecipeGroupMemberFactory,
)


@pytest.mark.django_db
class TestGetRecipesInVersionLine:
    def test_raises_when_recipe_has_no_version_group(self):
        recipe = FujifilmRecipeFactory()

        with pytest.raises(RecipeNotInVersionLineError) as exc_info:
            get_recipes_in_version_line(recipe_id=recipe.pk)

        assert exc_info.value.recipe_id == recipe.pk

    def test_raises_error_carries_the_queried_recipe_id(self):
        recipe = FujifilmRecipeFactory()

        with pytest.raises(RecipeNotInVersionLineError) as exc_info:
            get_recipes_in_version_line(recipe_id=recipe.pk)

        assert exc_info.value.recipe_id == recipe.pk

    def test_returns_version_line_result(self):
        recipe = FujifilmRecipeFactory()
        group = RecipeGroupFactory()
        RecipeGroupMemberFactory(group=group, recipe=recipe, position=1)

        result = get_recipes_in_version_line(recipe_id=recipe.pk)

        assert isinstance(result, VersionLineResult)

    def test_returns_all_members_ordered_by_position(self):
        group = RecipeGroupFactory()
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        recipe_v3 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=group, recipe=recipe_v1, position=1)
        RecipeGroupMemberFactory(group=group, recipe=recipe_v2, position=2)
        RecipeGroupMemberFactory(group=group, recipe=recipe_v3, position=3)

        result = get_recipes_in_version_line(recipe_id=recipe_v2.pk)

        assert [vr.recipe_id for vr in result.recipes] == [recipe_v1.pk, recipe_v2.pk, recipe_v3.pk]

    def test_marks_is_current_true_only_for_the_requested_recipe_id(self):
        group = RecipeGroupFactory()
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=group, recipe=recipe_v1, position=1)
        RecipeGroupMemberFactory(group=group, recipe=recipe_v2, position=2)

        result = get_recipes_in_version_line(recipe_id=recipe_v2.pk)

        current_flags = {vr.recipe_id: vr.is_current for vr in result.recipes}
        assert current_flags[recipe_v1.pk] is False
        assert current_flags[recipe_v2.pk] is True

    def test_label_matches_position(self):
        group = RecipeGroupFactory()
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=group, recipe=recipe_v1, position=1)
        RecipeGroupMemberFactory(group=group, recipe=recipe_v2, position=2)

        result = get_recipes_in_version_line(recipe_id=recipe_v1.pk)

        assert result.recipes[0].label == "v1"
        assert result.recipes[1].label == "v2"

    def test_name_field_matches_recipe_name(self):
        group = RecipeGroupFactory()
        recipe = FujifilmRecipeFactory(name="Superia Xtra 400")
        RecipeGroupMemberFactory(group=group, recipe=recipe, position=1)

        result = get_recipes_in_version_line(recipe_id=recipe.pk)

        assert result.recipes[0].name == "Superia Xtra 400"

    def test_does_not_include_members_from_other_groups(self):
        group_a = RecipeGroupFactory()
        group_b = RecipeGroupFactory()
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(group=group_a, recipe=recipe_a, position=1)
        RecipeGroupMemberFactory(group=group_b, recipe=recipe_b, position=1)

        result = get_recipes_in_version_line(recipe_id=recipe_a.pk)

        assert len(result.recipes) == 1
        assert result.recipes[0].recipe_id == recipe_a.pk

    def test_raises_when_recipe_is_only_in_family_group_not_version_line(self):
        family_group = RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_FAMILY)
        recipe = FujifilmRecipeFactory()
        RecipeGroupMemberFactory(
            group=family_group,
            recipe=recipe,
            group_type=models.RecipeGroup.GROUP_TYPE_FAMILY,
            position=None,
        )

        with pytest.raises(RecipeNotInVersionLineError):
            get_recipes_in_version_line(recipe_id=recipe.pk)
