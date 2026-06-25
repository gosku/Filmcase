from django.urls import path

from src.interfaces.camera import views

urlpatterns = [
    path("recipes/<int:recipe_id>/push/", views.SelectSlot.as_view(), name="select-push-slot"),
    path("recipes/<int:recipe_id>/push/<str:slot>/", views.PushRecipeToCamera.as_view(), name="push-recipe-to-camera"),
]
