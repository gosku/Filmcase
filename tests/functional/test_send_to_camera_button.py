"""
The "Send to camera" button, in both transports.

The button is the one place a user notices which transport is configured, and
it must commit to exactly one: a button carrying both the HTMX attributes and
the client hooks would fire a server-side push and a browser-side push at once.
"""

import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory


def _recipe(**kwargs):
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


def _button(client, recipe):
    """
    The Send to camera button, whichever variant is rendered.

    Selected by its label rather than by class: the disabled variant shown for
    an unnamed recipe carries action-btn--disabled and not send-to-camera-btn,
    so a class selector finds nothing and the test passes for the wrong reason.
    """
    soup = BeautifulSoup(client.get(f"/recipes/{recipe.id}/").content, "html.parser")
    buttons = [b for b in soup.find_all("button") if b.get_text(strip=True) == "Send to camera"]
    assert len(buttons) == 1, f"expected one button, found {len(buttons)}"
    return buttons[0]


@pytest.mark.django_db
class TestSendToCameraButtonInServerMode:
    def test_asks_the_server_for_the_slot_picker(self, client, settings):
        settings.CAMERA_TRANSPORT = "server"
        recipe = _recipe(name="Server Mode")

        button = _button(client, recipe)

        assert button["hx-get"] == f"/recipes/{recipe.id}/push/"
        assert button["hx-target"] == "#slot-overlay"

    def test_carries_no_client_hooks(self, client, settings):
        # Both sets of attributes on one button would start two pushes.
        settings.CAMERA_TRANSPORT = "server"
        recipe = _recipe(name="Server Mode")

        button = _button(client, recipe)

        assert not button.has_attr("data-camera-push")
        assert not button.has_attr("data-payload-url")

    def test_does_not_load_the_client_module(self, client, settings):
        settings.CAMERA_TRANSPORT = "server"
        recipe = _recipe(name="Server Mode")

        content = client.get(f"/recipes/{recipe.id}/").content.decode()

        assert "send_to_camera.js" not in content


@pytest.mark.django_db
class TestSendToCameraButtonInBrowserMode:
    def test_carries_the_client_hooks(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        button = _button(client, recipe)

        assert button.has_attr("data-camera-push")
        assert button["data-payload-url"] == f"/recipes/{recipe.id}/camera-payload.json"

    def test_does_not_ask_the_server_for_the_slot_picker(self, client, settings):
        # The server has no route to the camera in this mode, so a request to
        # it would only produce the 400 guard.
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        button = _button(client, recipe)

        assert not button.has_attr("hx-get")

    def test_loads_the_client_module(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        content = client.get(f"/recipes/{recipe.id}/").content.decode()

        assert '<script type="module" src="/static/js/camera/interfaces/send_to_camera.js">' in content

    def test_tells_the_client_where_its_configuration_is(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        soup = BeautifulSoup(client.get(f"/recipes/{recipe.id}/").content, "html.parser")

        element = soup.find(id="camera-client-config")
        assert element["data-url"] == "/camera/client-config.json"


@pytest.mark.django_db
class TestSendToCameraButtonWithoutAName:
    @pytest.mark.parametrize("transport", ["server", "browser"])
    def test_is_disabled_in_either_transport(self, client, settings, transport):
        # A slot needs a label, and validation rejects a blank name before any
        # write, so the button would fail whichever path it took.
        settings.CAMERA_TRANSPORT = transport
        recipe = _recipe(name="")

        button = _button(client, recipe)

        assert button.has_attr("disabled")
        assert not button.has_attr("data-camera-push")
        assert not button.has_attr("hx-get")


@pytest.mark.django_db
class TestClientModuleAssets:
    @pytest.mark.parametrize(
        "path",
        [
            "/static/js/camera/interfaces/send_to_camera.js",
            "/static/js/camera/application/usecases/push_recipe.js",
            "/static/js/camera/application/usecases/get_camera_slots.js",
            "/static/js/camera/domain/queries.js",
            "/static/js/camera/domain/validation.js",
            "/static/js/camera/domain/operations.js",
            "/static/js/camera/vendor/client_config.js",
            "/static/js/camera/vendor/recipe_payload.js",
            "/static/js/camera/vendor/ptp_device.js",
            "/static/js/camera/vendor/ptp_usb_device.js",
            "/static/js/camera/vendor/events.js",
        ],
    )
    def test_every_module_in_the_import_graph_is_served(self, client, path):
        # One 404 anywhere in the graph makes the whole feature silently inert:
        # a module that fails to load throws in the console and the button then
        # does nothing at all.
        assert client.get(path).status_code == 200, path


@pytest.mark.django_db
class TestNoLeakedTemplateSyntax:
    """
    Django's {# #} comment is single-line only. Spanning two lines makes it
    render as visible text rather than failing, which is how a note meant for
    the next developer ended up on the page above the button.

    {% comment %} is the multi-line form. This catches the mistake wherever it
    is made rather than only where it was made once.
    """

    @pytest.mark.parametrize("transport", ["server", "browser"])
    @pytest.mark.parametrize("page", ["/recipes/", "/recipes/{id}/"])
    def test_pages_render_no_template_syntax(self, client, settings, transport, page):
        settings.CAMERA_TRANSPORT = transport
        recipe = _recipe(name="No Leaks")

        content = client.get(page.format(id=recipe.id)).content.decode()

        for token in ("{#", "#}", "{%", "%}"):
            assert token not in content, f"{token} reached the page in {transport} mode"
