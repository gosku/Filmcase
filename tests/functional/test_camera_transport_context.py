"""
The transport flag has to reach every page that can host the recipe overlay.

These are functional rather than unit tests on purpose: the value of a context
processor is that it arrives without each view asking for it, and only a real
render proves that.
"""

import pytest

from tests.factories import FujifilmRecipeFactory


def _recipe(**kwargs):
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


@pytest.mark.django_db
class TestCameraTransportContext:
    @pytest.mark.parametrize(
        "url_for",
        [
            pytest.param(lambda recipe: "/recipes/", id="recipes-explorer"),
            pytest.param(lambda recipe: f"/recipes/{recipe.id}/", id="recipe-detail"),
        ],
    )
    def test_flag_reaches_every_page_hosting_the_recipe_overlay(self, client, url_for):
        recipe = _recipe(name="Anywhere")

        response = client.get(url_for(recipe))

        assert response.status_code == 200
        assert "camera_push_from_browser" in response.context

    def test_flag_is_false_in_server_mode(self, client, settings):
        settings.CAMERA_TRANSPORT = "server"
        recipe = _recipe(name="Server Mode")

        response = client.get(f"/recipes/{recipe.id}/")

        assert response.context["camera_push_from_browser"] is False

    def test_flag_is_true_in_browser_mode(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        response = client.get(f"/recipes/{recipe.id}/")

        assert response.context["camera_push_from_browser"] is True

    def test_unrecognised_transport_is_not_browser_mode(self, client, settings):
        # Anything other than "browser" leaves the server driving the camera,
        # so a typo in the environment degrades to today's behaviour rather
        # than to a page whose button does nothing.
        settings.CAMERA_TRANSPORT = "brower"
        recipe = _recipe(name="Typo")

        response = client.get(f"/recipes/{recipe.id}/")

        assert response.context["camera_push_from_browser"] is False
