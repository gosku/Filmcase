# This module has been superseded by src.domain.recipes.queries.
# Re-exported here to avoid breaking the compare_recipes management command.
from src.domain.recipes.queries import (  # noqa: F401
    RECIPE_FIELDS,
    RecipeComparisonResult,
    RecipeUsageStats,
    get_recipe_comparison,
)
