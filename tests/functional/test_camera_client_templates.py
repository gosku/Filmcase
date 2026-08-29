"""
The markup the browser-driven push clones.

In browser mode the server never renders the slot picker or the result card,
because it never talks to the camera. The shapes it would have rendered ship as
inert templates instead, so the markup stays described in one language and keeps
matching slot-card.css.
"""

import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory

TEMPLATE_IDS = [
    "camera-slot-card-template",
    "camera-slot-row-template",
    "camera-push-success-template",
    "camera-push-error-template",
    "camera-unavailable-template",
]

PAGES = ["/recipes/", "/recipes/{id}/"]


def _recipe(**kwargs):
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


def _soup(client, url):
    return BeautifulSoup(client.get(url).content, "html.parser")


@pytest.mark.django_db
class TestCameraClientTemplates:
    @pytest.mark.parametrize("page", PAGES)
    def test_absent_in_server_mode(self, client, settings, page):
        # Dead markup on every recipe page for the majority of installs, which
        # drive the camera from the server and never clone any of it.
        settings.CAMERA_TRANSPORT = "server"
        recipe = _recipe(name="Server Mode")

        content = client.get(page.format(id=recipe.id)).content.decode()

        for template_id in TEMPLATE_IDS:
            assert template_id not in content

    @pytest.mark.parametrize("page", PAGES)
    def test_present_in_browser_mode(self, client, settings, page):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        soup = _soup(client, page.format(id=recipe.id))

        for template_id in TEMPLATE_IDS:
            assert soup.find("template", id=template_id) is not None, template_id

    def test_templates_are_inert(self, client, settings):
        # A <template> is parsed but not rendered, which is what lets the card
        # markup sit on the page without appearing until it is cloned.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Inert")

        soup = _soup(client, "/recipes/")

        for template_id in TEMPLATE_IDS:
            element = soup.find("template", id=template_id)
            assert element.name == "template"

    def test_slot_card_carries_the_hooks_the_client_fills(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Hooks")

        card = _soup(client, "/recipes/").find("template", id="camera-slot-card-template")

        assert card.select_one("[data-recipe-name]") is not None
        assert card.select_one("[data-slot-rows]") is not None

    def test_slot_row_carries_the_hooks_the_client_fills(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Hooks")

        row = _soup(client, "/recipes/").find("template", id="camera-slot-row-template")

        assert row.select_one("[data-slot-index]") is not None
        assert row.select_one("[data-slot-label]") is not None
        assert row.select_one("[data-slot-name]") is not None
        assert row.select_one("[data-slot-film-sim]") is not None

    def test_result_templates_carry_their_hooks(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Hooks")

        soup = _soup(client, "/recipes/")

        success = soup.find("template", id="camera-push-success-template")
        error = soup.find("template", id="camera-push-error-template")
        assert success.select_one("[data-push-message]") is not None
        assert error.select_one("[data-push-error]") is not None
        assert error.select_one("[data-push-retry]") is not None

    def test_uses_the_same_classes_the_server_rendered_partials_use(self, client, settings):
        # Both paths are styled by slot-card.css. If these drift from the
        # partials, one path silently loses its styling and only the path
        # nobody switched to is affected.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Classes")

        soup = _soup(client, "/recipes/")

        card = soup.find("template", id="camera-slot-card-template")
        assert card.select_one(".slot-card") is not None
        assert card.select_one(".slot-card-header") is not None
        assert card.select_one(".slot-card-close") is not None

        row = soup.find("template", id="camera-slot-row-template")
        assert row.select_one(".slot-row") is not None
        assert row.select_one(".slot-badge") is not None
        assert row.select_one(".slot-film-tag") is not None

        success = soup.find("template", id="camera-push-success-template")
        assert success.select_one(".push-result-center") is not None
        assert success.select_one(".push-check-svg") is not None

        error = soup.find("template", id="camera-push-error-template")
        assert error.select_one(".push-result-err-message") is not None
        assert error.select_one(".push-retry-btn") is not None

    def test_the_film_tag_starts_hidden(self, client, settings):
        # A slot with no film simulation should show nothing rather than an
        # empty coloured pill.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Hidden")

        row = _soup(client, "/recipes/").find("template", id="camera-slot-row-template")

        assert row.select_one("[data-slot-film-sim]").has_attr("hidden")

    def test_the_unavailable_card_links_to_the_diagnostics(self, client, settings):
        # A browser that cannot do WebUSB is a different failure from a camera
        # being unplugged, and no amount of reconnecting fixes it.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Unavailable")

        card = _soup(client, "/recipes/").find("template", id="camera-unavailable-template")

        assert card.select_one("[data-unavailable-reason]") is not None
        assert card.find("a", href="/settings/camera-diagnostics/") is not None

    def test_only_the_standalone_templates_carry_a_card(self, client, settings):
        # The contract send_to_camera.js depends on, worth stating because
        # getting it wrong is invisible until a failure happens at the wrong
        # moment.
        #
        # The result and error templates are swapped INTO an existing .slot-card,
        # exactly as HTMX does on the server-rendered path, so a card of their
        # own would nest one inside another. The consequence is that a failure
        # before the picker renders has no card to swap into, and the client has
        # to make one; without that the message floats on the backdrop with no
        # background behind it.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Cards")

        soup = _soup(client, "/recipes/")

        for template_id in ["camera-slot-card-template", "camera-unavailable-template"]:
            element = soup.find("template", id=template_id)
            assert element.select_one(".slot-card") is not None, template_id

        for template_id in ["camera-push-success-template", "camera-push-error-template"]:
            element = soup.find("template", id=template_id)
            assert element.select_one(".slot-card") is None, template_id

    def test_the_card_shell_can_stand_in_for_a_picker_that_never_rendered(self, client, settings):
        # ensureCard() clones this shell when a camera lookup fails, so it needs
        # a header the client can label and a body it can replace wholesale.
        settings.CAMERA_TRANSPORT = "browser"
        _recipe(name="Shell")

        card = _soup(client, "/recipes/").find("template", id="camera-slot-card-template")

        assert card.select_one("#slot-card") is not None
        assert card.select_one("[data-recipe-name]") is not None
        assert card.select_one(".slot-card-close") is not None
