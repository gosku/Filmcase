from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView
from django.views.static import serve as static_serve

from src.interfaces import views

urlpatterns = [
    path("static/<path:path>", static_serve, {"document_root": settings.STATIC_FILES_DIR}),
    path("", RedirectView.as_view(pattern_name="gallery"), name="root"),
    path("images/", views.gallery_view, name="gallery"),
    path("images/results/", views.gallery_results_view, name="gallery-results"),
    path("images/file/<int:image_id>/", views.image_file_view, name="image-file"),
    path("images/<int:image_id>/", views.image_detail_view, name="image-detail"),
    path("images/<int:image_id>/set-rating/", views.set_image_rating_view, name="image-set-rating"),
    path("recipes/", views.recipes_explorer_view, name="recipes-explorer"),
    path("recipes/import/", views.import_recipes_from_uploaded_files_view, name="recipes-import"),
    path("recipes/partial/results/", views.recipes_explorer_results_view, name="recipes-explorer-partial-results"),
    path("recipes/graph/", views.recipes_graph_view, name="recipes-graph"),
    path("recipes/graph/<int:recipe_id>/", views.recipe_graph_view, name="recipe-graph"),
    path("recipes/<int:recipe_id>/", views.recipe_detail_view, name="recipe-detail"),
    path("recipes/<int:recipe_id>/images/", views.recipe_images_view, name="recipe-images"),
    path("recipes/<int:recipe_id>/images/<int:image_id>/", views.recipe_compare_image_view, name="recipe-compare-image"),
    path("recipes/path-deltas/", views.recipe_path_deltas_view, name="recipe-path-deltas"),
    path("recipes/<int:recipe_id>/set-name/", views.SetRecipeName.as_view(), name="set-recipe-name"),
    path("recipes/<int:recipe_id>/set-cover-image/<int:image_id>/", views.SetRecipeCoverImage.as_view(), name="set-recipe-cover-image"),
    path("recipes/<int:recipe_id>/push/", views.SelectSlot.as_view(), name="select-push-slot"),
    path("recipes/<int:recipe_id>/push/<str:slot>/", views.PushRecipeToCamera.as_view(), name="push-recipe-to-camera"),
    path("recipes/<int:recipe_id>/card/preview/file/", views.recipe_card_preview_file_view, name="recipe-card-preview-file"),
]
