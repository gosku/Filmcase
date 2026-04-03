# This module has been superseded by src.domain.recipes.graph.
# Re-exported here only to avoid breaking callers during the transition.
from src.domain.recipes.graph import (  # noqa: F401
    RecipeEdge,
    RecipeGraphData,
    RecipeNode,
    build_recipe_graph,
    hamming_distance,
)
