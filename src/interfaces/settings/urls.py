from django.urls import include, path
from django.views.generic import RedirectView

from src.interfaces.camera import views as camera_views
from src.interfaces.library.urls import urlpatterns as library_urlpatterns

urlpatterns = [
    # The settings landing has no page of its own yet, so it opens on the first tab.
    path("settings/", RedirectView.as_view(pattern_name="library-list"), name="settings"),
    # Mounted without a namespace so the library URL names stay flat and every
    # existing {% url %} / reverse() reference keeps resolving unchanged.
    path("settings/library/", include(library_urlpatterns)),
    # The diagnostics page is a settings tab; the rest of the camera routes are
    # not settings pages and stay under /camera/ and /recipes/.
    path("settings/camera-diagnostics/", camera_views.CameraDiagnostics.as_view(), name="camera-diagnostics"),
]
