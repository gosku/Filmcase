from unittest.mock import patch

import pytest

from src.data import models
from src.domain.recipes.queries import RecipeNotInVersionLineError, get_recipes_in_version_line


class TestGetRecipesInVersionLine:
    def test_raises_when_recipe_group_member_does_not_exist(self):
        with patch("src.domain.recipes.queries.models.RecipeGroupMember.objects") as mock_objects:
            mock_objects.get.side_effect = models.RecipeGroupMember.DoesNotExist

            with pytest.raises(RecipeNotInVersionLineError) as exc_info:
                get_recipes_in_version_line(recipe_id=42)

        assert exc_info.value.recipe_id == 42
