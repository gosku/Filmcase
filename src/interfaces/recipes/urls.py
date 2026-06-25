from django.urls import path

from src.interfaces.recipes import views

urlpatterns = [
    path("recipes/", views.RecipesExplorer.as_view(), name="recipes-explorer"),
    path("recipes/create/", views.CreateRecipe.as_view(), name="create-recipe"),
    path("recipes/<int:recipe_id>/edit/", views.EditRecipe.as_view(), name="edit-recipe"),
    path("recipes/<int:recipe_id>/create-version/", views.CreateRecipeVersion.as_view(), name="create-recipe-version"),
    path("recipes/delete/", views.RemoveRecipes.as_view(), name="recipes-delete"),
    path("recipes/cards/batch/", views.CreateRecipeCardsBatch.as_view(), name="recipes-create-cards-batch"),
    path("recipes/cards/zip/<str:filename>/", views.RecipeCardZipDownload.as_view(), name="recipes-card-zip-download"),
    path("recipes/import/", views.ImportRecipesFromUploadedFiles.as_view(), name="recipes-import"),
    path("recipes/import-qr-cards/", views.ImportRecipesFromUploadedQrCards.as_view(), name="recipes-import-qr-cards"),
    path("recipes/partial/results/", views.RecipesExplorerResults.as_view(), name="recipes-explorer-partial-results"),
    path("recipes/graph/", views.RecipesGraph.as_view(), name="recipes-graph"),
    path("recipes/graph/<int:recipe_id>/", views.RecipeGraph.as_view(), name="recipe-graph"),
    path("recipes/<int:recipe_id>/distribution/", views.RecipeDistribution.as_view(), name="recipe-distribution"),
    path("recipes/<int:recipe_id>/", views.RecipeDetail.as_view(), name="recipe-detail"),
    path("recipes/<int:recipe_id>/images/", views.RecipeImages.as_view(), name="recipe-images"),
    path("recipes/<int:recipe_id>/images/<int:image_id>/", views.RecipeCompareImage.as_view(), name="recipe-compare-image"),
    path("recipes/path-deltas/", views.RecipePathDeltas.as_view(), name="recipe-path-deltas"),
    path("recipes/<int:recipe_id>/set-name/", views.SetRecipeName.as_view(), name="set-recipe-name"),
    path("recipes/<int:recipe_id>/set-cover-image/<int:image_id>/", views.SetRecipeCoverImage.as_view(), name="set-recipe-cover-image"),
    path("recipes/<int:recipe_id>/card/partial/modal/", views.RecipeCardModal.as_view(), name="recipe-card-modal"),
    path("recipes/<int:recipe_id>/card/partial/preview/", views.RecipeCardPreview.as_view(), name="recipe-card-preview"),
    path("recipes/<int:recipe_id>/card/preview/file/", views.RecipeCardPreviewFile.as_view(), name="recipe-card-preview-file"),
    path("recipes/<int:recipe_id>/card/partial/create/", views.CreateRecipeCard.as_view(), name="create-recipe-card"),
    path("recipes/card/<int:card_id>/file/", views.RecipeCardFile.as_view(), name="recipe-card-file"),
    path("recipes/<int:recipe_id>/move-version-line/", views.MoveRecipeToVersionLine.as_view(), name="move-recipe-version-line"),
    path("recipes/<int:recipe_id>/move-version-line/search/", views.MoveRecipeToVersionLineSearch.as_view(), name="move-recipe-version-line-search"),
    path("recipes/<int:recipe_id>/move-version-line/preview/", views.MoveRecipeToVersionLinePreview.as_view(), name="move-recipe-version-line-preview"),
]
