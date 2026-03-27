from django.urls import path

from src.interfaces import views

urlpatterns = [
    path("images/", views.gallery_view, name="gallery"),
    path("images/results/", views.gallery_results_view, name="gallery-results"),
    path("images/file/<int:image_id>/", views.image_file_view, name="image-file"),
    path("images/<int:image_id>/", views.image_detail_view, name="image-detail"),
    path("images/<int:image_id>/toggle-favorite/", views.toggle_favorite_view, name="image-toggle-favorite"),
    path("recipes/<int:recipe_id>/push/<str:slot>/", views.PushRecipeToCameraView.as_view(), name="push-recipe-to-camera"),
]
