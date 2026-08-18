from django.urls import path

from src.interfaces.camera import views

urlpatterns = [
    path("recipes/<int:recipe_id>/push/", views.SelectSlot.as_view(), name="select-push-slot"),
    path("recipes/<int:recipe_id>/push/<str:slot>/", views.PushRecipeToCamera.as_view(), name="push-recipe-to-camera"),
    path("camera/diagnostics/", views.CameraDiagnostics.as_view(), name="camera-diagnostics"),
    path("camera/client-config.json", views.CameraClientConfig.as_view(), name="camera-client-config"),
    path("recipes/<int:recipe_id>/camera-payload.json", views.RecipeCameraPayload.as_view(), name="recipe-camera-payload"),
]
