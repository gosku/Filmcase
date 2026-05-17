import pytest

from src.application.usecases.recipes.create_recipe_version import (
    RecipeAlreadyExistsError,
    VersionLineGroupNotFoundError,
    create_recipe_version,
)
from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    base: dict[str, object] = dict(
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
        color="0",
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


@pytest.mark.django_db
class TestCreateRecipeVersionPersistence:
    def test_returns_the_newly_created_recipe(self) -> None:
        group = RecipeGroupFactory()

        recipe = create_recipe_version(data=_make_data(), group_id=group.pk)

        assert recipe.pk is not None
        assert isinstance(recipe, models.FujifilmRecipe)

    def test_new_recipe_is_added_to_the_version_line_group(self) -> None:
        group = RecipeGroupFactory()

        recipe = create_recipe_version(data=_make_data(), group_id=group.pk)

        assert models.RecipeGroupMember.objects.filter(
            recipe=recipe,
            group=group,
        ).exists()

    def test_new_recipe_follows_existing_members_in_position(self) -> None:
        source = FujifilmRecipeFactory()
        group = RecipeGroupFactory()
        RecipeGroupMemberFactory(group=group, recipe=source, position=1)

        recipe = create_recipe_version(data=_make_data(), group_id=group.pk)

        member = models.RecipeGroupMember.objects.get(recipe=recipe)
        assert member.position == 2


@pytest.mark.django_db
class TestCreateRecipeVersionErrors:
    def test_raises_already_exists_when_settings_match_existing_recipe(self) -> None:
        group = RecipeGroupFactory()
        create_recipe_version(data=_make_data(), group_id=group.pk)

        with pytest.raises(RecipeAlreadyExistsError) as exc_info:
            create_recipe_version(data=_make_data(), group_id=group.pk)

        assert exc_info.value.name is not None

    def test_raises_version_line_group_not_found_for_nonexistent_group(self) -> None:
        with pytest.raises(VersionLineGroupNotFoundError) as exc_info:
            create_recipe_version(data=_make_data(), group_id=99999)

        assert exc_info.value.group_id == 99999

    def test_raises_version_line_group_not_found_for_family_group(self) -> None:
        family_group = RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_FAMILY)

        with pytest.raises(VersionLineGroupNotFoundError):
            create_recipe_version(data=_make_data(), group_id=family_group.pk)
