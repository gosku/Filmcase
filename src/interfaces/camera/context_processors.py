"""
Template context describing how the camera is reached.

A context processor rather than per-view context because the "Send to camera"
button lives in recipes/partials/recipe_detail.html, which is rendered both as
an HTMX fragment by RecipeDetail and as an include by two full pages.  Threading
a key through each of those would need three edits today and a fourth the next
time a page hosts the recipe overlay.
"""
from __future__ import annotations

from django import http

from src.domain.camera import device_config


def camera_transport(request: http.HttpRequest) -> dict[str, bool]:
    """
    Expose whether the browser drives the camera, as a boolean.

    A boolean rather than the raw setting so templates branch on a name instead
    of comparing against the string "browser" in three places.
    """
    return {"camera_push_from_browser": device_config.is_browser_transport()}
