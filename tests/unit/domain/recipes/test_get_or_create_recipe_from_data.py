from unittest.mock import MagicMock, patch

import pytest

from src.domain.recipes import operations

_MODULE = "src.domain.recipes.operations"


class TestGetOrCreateRecipeFromDataVersionLine:
    def test_raises_version_line_group_not_found_error_when_group_id_is_invalid(self) -> None:
        mock_recipe = MagicMock()
        mock_data = MagicMock()

        with (
            patch("django.db.transaction.Atomic.__enter__", return_value=None),
            patch("django.db.transaction.Atomic.__exit__", return_value=False),
            patch(f"{_MODULE}.recipe_normalization.normalize_recipe_data", return_value=mock_data),
            patch(f"{_MODULE}.recipe_validation.validate_recipe_data"),
            patch(f"{_MODULE}._parse_numeric", return_value=None),
            patch(f"{_MODULE}.models.FujifilmRecipe.get_or_create", return_value=(mock_recipe, True)),
            patch(
                f"{_MODULE}.add_recipe_to_version_line",
                side_effect=operations.VersionLineGroupNotFoundError(group_id=99),
            ),
            pytest.raises(operations.VersionLineGroupNotFoundError),
        ):
            operations.get_or_create_recipe_from_data(data=mock_data, group_id=99)
