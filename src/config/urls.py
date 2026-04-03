from django.urls import path

from src.interfaces import views

urlpatterns = [
    path("images/", views.gallery_view, name="gallery"),
    path("images/results/", views.gallery_results_view, name="gallery-results"),
    path("images/file/<int:image_id>/", views.image_file_view, name="image-file"),
    path("images/<int:image_id>/", views.image_detail_view, name="image-detail"),
    path("images/<int:image_id>/set-rating/", views.set_image_rating_view, name="image-set-rating"),
    path("recipes/", views.recipes_explorer_view, name="recipes-explorer"),
    path("recipes/graph/<int:recipe_id>/", views.recipe_graph_view, name="recipe-graph"),
    path("recipes/<int:recipe_id>/set-name/", views.SetRecipeName.as_view(), name="set-recipe-name"),
    path("recipes/<int:recipe_id>/push/", views.SelectSlot.as_view(), name="select-push-slot"),
    path("recipes/<int:recipe_id>/push/<str:slot>/", views.PushRecipeToCamera.as_view(), name="push-recipe-to-camera"),
]
