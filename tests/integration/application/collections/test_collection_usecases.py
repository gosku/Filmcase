import pytest

from src.application.usecases.collections import create_collection as create_uc
from src.application.usecases.collections import delete_collection as delete_uc
from src.application.usecases.collections import update_collection as update_uc
from src.data import models
from tests.factories import (
    FujifilmRecipeFactory,
    RecipeCollectionFactory,
    RecipeCollectionMemberFactory,
)


@pytest.mark.django_db
class TestCreateCollectionUseCase:
    def test_creates_a_collection(self):
        recipe = FujifilmRecipeFactory()

        result = create_uc.create_collection(name="Street Mono", recipe_ids=[recipe.pk])

        group = models.RecipeGroup.objects.get(pk=result.collection_id)
        assert group.name == "Street Mono"
        assert group.group_type == models.RecipeGroup.GROUP_TYPE_COLLECTION
        assert models.RecipeGroupMember.objects.filter(group_id=group.pk).count() == 1

    def test_raises_name_taken(self):
        create_uc.create_collection(name="Set", recipe_ids=[])

        with pytest.raises(create_uc.CollectionNameTaken):
            create_uc.create_collection(name="set", recipe_ids=[])


@pytest.mark.django_db
class TestUpdateCollectionUseCase:
    def test_renames_and_reorders(self):
        group = RecipeCollectionFactory(name="Old")
        first = FujifilmRecipeFactory()
        second = FujifilmRecipeFactory()
        RecipeCollectionMemberFactory(group=group, recipe=first, position=0)

        update_uc.update_collection(
            collection_id=group.pk, name="New", recipe_ids=[second.pk, first.pk]
        )

        group.refresh_from_db()
        assert group.name == "New"
        order = list(
            models.RecipeGroupMember.objects
            .filter(group_id=group.pk).order_by("position").values_list("recipe_id", flat=True)
        )
        assert order == [second.pk, first.pk]

    def test_raises_collection_not_found(self):
        with pytest.raises(update_uc.CollectionNotFound):
            update_uc.update_collection(collection_id=999, name="X", recipe_ids=[])


@pytest.mark.django_db
class TestDeleteCollectionUseCase:
    def test_deletes_a_collection(self):
        group = RecipeCollectionFactory(name="Set")

        delete_uc.delete_collection(collection_id=group.pk)

        assert not models.RecipeGroup.objects.filter(pk=group.pk).exists()

    def test_raises_collection_not_found(self):
        with pytest.raises(delete_uc.CollectionNotFound):
            delete_uc.delete_collection(collection_id=999)
