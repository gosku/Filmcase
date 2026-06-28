from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView
from django.views.static import serve as static_serve

from src.interfaces.camera.urls import urlpatterns as camera_urlpatterns
from src.interfaces.images.urls import urlpatterns as image_urlpatterns
from src.interfaces.library.urls import urlpatterns as library_urlpatterns
from src.interfaces.recipes.urls import urlpatterns as recipe_urlpatterns

urlpatterns = [
    path("static/<path:path>", static_serve, {"document_root": settings.STATIC_FILES_DIR}),
    path("", RedirectView.as_view(pattern_name="recipes-explorer"), name="root"),
] + image_urlpatterns + recipe_urlpatterns + camera_urlpatterns + library_urlpatterns
