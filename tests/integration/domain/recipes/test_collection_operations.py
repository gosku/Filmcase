import pytest

from src.data import models
from src.domain.recipes.operations import (
    CollectionNameTaken,
    RecipeNotFound,
    create_collection,
    delete_collection,
    update_collection,
)
from src.domain.recipes.queries import CollectionNotFound
from tests.factories import (
    FujifilmRecipeFactory,
    RecipeCollectionFactory,
    RecipeCollectionMemberFactory,
)


def _member_recipe_ids_in_order(group_id: int) -> list[int]:
    return list(
        models.RecipeGroupMember.objects
        .filter(group_id=group_id)
        .order_by("position")
        .values_list("recipe_id", flat=True)
    )


@pytest.mark.django_db
class TestCreateCollection:
    def test_creates_a_collection_group_with_the_name(self):
        group = create_collection(name="Street Mono", recipe_ids=[])

        assert group.group_type == models.RecipeGroup.GROUP_TYPE_COLLECTION
        assert group.name == "Street Mono"

    def test_creates_members_in_order_from_zero(self):
        r1 = FujifilmRecipeFactory()
        r2 = FujifilmRecipeFactory()

        group = create_collection(name="Set", recipe_ids=[r2.pk, r1.pk])

        assert _member_recipe_ids_in_order(group.pk) == [r2.pk, r1.pk]
        positions = list(
            models.RecipeGroupMember.objects
            .filter(group_id=group.pk).order_by("position").values_list("position", flat=True)
        )
        assert positions == [0, 1]

    def test_members_carry_the_collection_group_type(self):
        recipe = FujifilmRecipeFactory()

        group = create_collection(name="Set", recipe_ids=[recipe.pk])

        member = models.RecipeGroupMember.objects.get(group_id=group.pk)
        assert member.group_type == models.RecipeGroup.GROUP_TYPE_COLLECTION

    def test_deduplicates_repeated_recipe_ids(self):
        recipe = FujifilmRecipeFactory()

        group = create_collection(name="Set", recipe_ids=[recipe.pk, recipe.pk])

        assert _member_recipe_ids_in_order(group.pk) == [recipe.pk]

    def test_raises_recipe_not_found_for_a_missing_recipe(self):
        with pytest.raises(RecipeNotFound) as exc_info:
            create_collection(name="Set", recipe_ids=[123456])

        assert exc_info.value.recipe_id == 123456

    def test_does_not_create_a_group_when_a_recipe_is_missing(self):
        with pytest.raises(RecipeNotFound):
            create_collection(name="Set", recipe_ids=[123456])

        assert not models.RecipeGroup.objects.filter(
            group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION
        ).exists()

    def test_raises_when_name_collides_case_insensitively(self):
        create_collection(name="Street Mono", recipe_ids=[])

        with pytest.raises(CollectionNameTaken) as exc_info:
            create_collection(name="street mono", recipe_ids=[])

        assert exc_info.value.name == "street mono"


@pytest.mark.django_db
class TestUpdateCollection:
    def test_raises_when_collection_missing(self):
        with pytest.raises(CollectionNotFound) as exc_info:
            update_collection(collection_id=999, name="X", recipe_ids=[])

        assert exc_info.value.collection_id == 999

    def test_renames_the_collection(self):
        group = RecipeCollectionFactory(name="Old")

        update_collection(collection_id=group.pk, name="New", recipe_ids=[])

        group.refresh_from_db()
        assert group.name == "New"

    def test_replaces_membership_and_order(self):
        group = RecipeCollectionFactory(name="Set")
        kept = FujifilmRecipeFactory()
        dropped = FujifilmRecipeFactory()
        added = FujifilmRecipeFactory()
        RecipeCollectionMemberFactory(group=group, recipe=kept, position=0)
        RecipeCollectionMemberFactory(group=group, recipe=dropped, position=1)

        update_collection(collection_id=group.pk, name="Set", recipe_ids=[added.pk, kept.pk])

        assert _member_recipe_ids_in_order(group.pk) == [added.pk, kept.pk]

    def test_keeping_the_same_name_is_not_a_collision(self):
        group = RecipeCollectionFactory(name="Set")

        update_collection(collection_id=group.pk, name="Set", recipe_ids=[])

        group.refresh_from_db()
        assert group.name == "Set"

    def test_raises_when_renaming_onto_another_collections_name(self):
        RecipeCollectionFactory(name="Taken")
        group = RecipeCollectionFactory(name="Mine")

        with pytest.raises(CollectionNameTaken):
            update_collection(collection_id=group.pk, name="taken", recipe_ids=[])

    def test_raises_recipe_not_found_for_a_missing_recipe(self):
        group = RecipeCollectionFactory(name="Set")

        with pytest.raises(RecipeNotFound):
            update_collection(collection_id=group.pk, name="Set", recipe_ids=[123456])


@pytest.mark.django_db
class TestDeleteCollection:
    def test_raises_when_collection_missing(self):
        with pytest.raises(CollectionNotFound) as exc_info:
            delete_collection(collection_id=999)

        assert exc_info.value.collection_id == 999

    def test_deletes_the_group_and_its_members(self):
        group = RecipeCollectionFactory(name="Set")
        RecipeCollectionMemberFactory(group=group)

        delete_collection(collection_id=group.pk)

        assert not models.RecipeGroup.objects.filter(pk=group.pk).exists()
        assert not models.RecipeGroupMember.objects.filter(group_id=group.pk).exists()

    def test_does_not_delete_the_recipes(self):
        group = RecipeCollectionFactory(name="Set")
        recipe = FujifilmRecipeFactory()
        RecipeCollectionMemberFactory(group=group, recipe=recipe)

        delete_collection(collection_id=group.pk)

        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()
