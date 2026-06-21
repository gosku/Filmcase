from django.urls import path

from src.interfaces.images import views

urlpatterns = [
    path("images/", views.gallery_view, name="gallery"),
    path("images/results/", views.gallery_results_view, name="gallery-results"),
    path("images/file/<int:image_id>/", views.image_file_view, name="image-file"),
    path("images/<int:image_id>/", views.image_detail_view, name="image-detail"),
    path("images/<int:image_id>/set-rating/", views.set_image_rating_view, name="image-set-rating"),
]
