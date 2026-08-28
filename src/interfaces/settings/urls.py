from django.urls import include, path
from django.views.generic import RedirectView

from src.interfaces.library.urls import urlpatterns as library_urlpatterns

urlpatterns = [
    # The settings landing has no page of its own yet, so it opens on the first tab.
    path("settings/", RedirectView.as_view(pattern_name="library-list"), name="settings"),
    # Mounted without a namespace so the library URL names stay flat and every
    # existing {% url %} / reverse() reference keeps resolving unchanged.
    path("settings/library/", include(library_urlpatterns)),
]
