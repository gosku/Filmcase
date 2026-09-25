from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.collections import create_collection as create_uc
from src.application.usecases.collections import delete_collection as delete_uc
from src.application.usecases.collections import update_collection as update_uc
from src.domain.recipes.operations import CollectionNameTaken as DomainCollectionNameTaken
from src.domain.recipes.operations import RecipeNotFound as DomainRecipeNotFound
from src.domain.recipes.queries import CollectionNotFound as DomainCollectionNotFound

_CREATE = "src.application.usecases.collections.create_collection.domain_operations.create_collection"
_UPDATE = "src.application.usecases.collections.update_collection.domain_operations.update_collection"
_DELETE = "src.application.usecases.collections.delete_collection.domain_operations.delete_collection"


class TestCreateCollection:
    def test_returns_collection_data_on_success(self) -> None:
        group = MagicMock(pk=7)
        group.name = "Set"
        with patch(_CREATE, return_value=group):
            result = create_uc.create_collection(name="Set", recipe_ids=[1, 2])
        assert result.collection_id == 7
        assert result.name == "Set"

    def test_translates_name_taken(self) -> None:
        with patch(_CREATE, side_effect=DomainCollectionNameTaken(name="Set")):
            with pytest.raises(create_uc.CollectionNameTaken) as exc_info:
                create_uc.create_collection(name="Set", recipe_ids=[])
        assert exc_info.value.name == "Set"

    def test_translates_recipe_not_found(self) -> None:
        with patch(_CREATE, side_effect=DomainRecipeNotFound(recipe_id=9)):
            with pytest.raises(create_uc.RecipeNotFound) as exc_info:
                create_uc.create_collection(name="Set", recipe_ids=[9])
        assert exc_info.value.recipe_id == 9


class TestUpdateCollection:
    def test_returns_collection_data_on_success(self) -> None:
        group = MagicMock(pk=3)
        group.name = "New"
        with patch(_UPDATE, return_value=group):
            result = update_uc.update_collection(collection_id=3, name="New", recipe_ids=[1])
        assert result.collection_id == 3

    def test_translates_collection_not_found(self) -> None:
        with patch(_UPDATE, side_effect=DomainCollectionNotFound(collection_id=3)):
            with pytest.raises(update_uc.CollectionNotFound) as exc_info:
                update_uc.update_collection(collection_id=3, name="X", recipe_ids=[])
        assert exc_info.value.collection_id == 3

    def test_translates_name_taken(self) -> None:
        with patch(_UPDATE, side_effect=DomainCollectionNameTaken(name="Taken")):
            with pytest.raises(update_uc.CollectionNameTaken):
                update_uc.update_collection(collection_id=3, name="Taken", recipe_ids=[])

    def test_translates_recipe_not_found(self) -> None:
        with patch(_UPDATE, side_effect=DomainRecipeNotFound(recipe_id=9)):
            with pytest.raises(update_uc.RecipeNotFound):
                update_uc.update_collection(collection_id=3, name="X", recipe_ids=[9])


class TestDeleteCollection:
    def test_calls_the_domain_operation(self) -> None:
        with patch(_DELETE) as mock_delete:
            delete_uc.delete_collection(collection_id=5)
        mock_delete.assert_called_once_with(collection_id=5)

    def test_translates_collection_not_found(self) -> None:
        with patch(_DELETE, side_effect=DomainCollectionNotFound(collection_id=5)):
            with pytest.raises(delete_uc.CollectionNotFound) as exc_info:
                delete_uc.delete_collection(collection_id=5)
        assert exc_info.value.collection_id == 5
