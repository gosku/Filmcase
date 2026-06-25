from django.urls import path

from src.interfaces.images import views

urlpatterns = [
    path("images/", views.Gallery.as_view(), name="gallery"),
    path("images/results/", views.GalleryResults.as_view(), name="gallery-results"),
    path("images/file/<int:image_id>/", views.ImageFile.as_view(), name="image-file"),
    path("images/<int:image_id>/", views.ImageDetail.as_view(), name="image-detail"),
    path("images/<int:image_id>/set-rating/", views.SetImageRating.as_view(), name="image-set-rating"),
]
