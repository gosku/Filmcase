from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from tests.factories import FujifilmRecipeFactory
from tests.fakes import FakePTPDevice

_PRISTINE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _recipe(**kwargs):
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


@pytest.mark.django_db
class TestSelectSlotView:
    def test_success_renders_recipe_name_and_slots(self, client):
        recipe = _recipe(name="Kodak Portra")
        # autouse fixture → FakePTPDevice(camera_name="X-S10") → 4 slots

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(string="Kodak Portra") is not None
        slot_labels = [el.get_text(strip=True) for el in soup.select(".slot-badge")]
        assert slot_labels == ["C1", "C2", "C3", "C4"]

    def test_each_slot_form_posts_to_push_view(self, client):
        recipe = _recipe(name="My Recipe")

        response = client.get(f"/recipes/{recipe.id}/push/")

        soup = BeautifulSoup(response.content, "html.parser")
        forms = soup.select("form[action]")
        assert len(forms) == 4
        for form, slot in zip(forms, ["C1", "C2", "C3", "C4"]):
            assert form["action"] == f"/recipes/{recipe.id}/push/{slot}/"
            assert form["method"] == "post"

    def test_recipe_not_found_returns_404(self, client):
        response = client.get("/recipes/99999/push/")

        assert response.status_code == 404

    def test_recipe_without_name_returns_404(self, client):
        recipe = _recipe(name="")

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 404

    def test_camera_connection_error_returns_503(self, client, settings):
        recipe = _recipe(name="My Recipe")
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
        )

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 503
        assert "Camera connection error" in response.json()["error"]

    def test_camera_write_error_returns_500(self, client, settings):
        recipe = _recipe(name="My Recipe")
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 500
        assert "Camera write error" in response.json()["error"]

    def test_unexpected_error_returns_500_with_generic_message(self, client, settings):
        recipe = _recipe(name="My Recipe")

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 500
        assert response.json() == {"error": "Unexpected error happened"}


@pytest.mark.django_db
class TestSelectSlotViewXT2:
    def _xt2(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)

    def test_dropped_fields_are_announced(self, client, settings):
        self._xt2(settings)
        recipe = FujifilmRecipeFactory(name="XT2", film_simulation="Classic Chrome",
                                       white_balance="Underwater", sharpness=0, high_iso_nr=0,
                                       clarity=3)

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 200
        assert "Clarity" in BeautifulSoup(response.content, "html.parser").get_text()

    def test_conflicting_slots_are_disabled(self, client, settings):
        self._xt2(settings)
        # A new Auto shift would retune the pristine slots that share Auto.
        recipe = _recipe(name="Clash", film_simulation="Classic Chrome",
                         white_balance="Auto", white_balance_red=5, white_balance_blue=5)

        response = client.get(f"/recipes/{recipe.id}/push/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.select("button.slot-row[disabled]")

    def test_shared_wb_conflict_shows_one_note_with_expandable_detail(self, client, settings):
        self._xt2(settings)
        # Auto is shared by two pristine slots, so no slot is free: the summary
        # says so, and the full reason sits behind the (i).
        recipe = _recipe(name="Clash", film_simulation="Classic Chrome",
                         white_balance="Auto", white_balance_red=5, white_balance_blue=5)

        response = client.get(f"/recipes/{recipe.id}/push/")

        soup = BeautifulSoup(response.content, "html.parser")
        notes = soup.select("details.slot-conflict")
        assert len(notes) == 1
        assert "can't be pushed to any slot" in notes[0].select_one(".slot-conflict-summary").get_text()
        assert "white balance" in notes[0].select_one(".slot-conflict-detail").get_text().lower()
        # The reason no longer repeats inside every greyed slot.
        assert soup.select(".slot-reason") == []

    def test_sole_wb_user_conflict_offers_to_replace_that_slot(self, client, settings):
        self._xt2(settings)
        # Shade is used by exactly one pristine slot (C3), so the recipe can go
        # there and nowhere else; the summary points at that slot.
        recipe = _recipe(name="Shady", film_simulation="Classic Chrome",
                         white_balance="Shade", white_balance_red=5, white_balance_blue=5)

        response = client.get(f"/recipes/{recipe.id}/push/")

        soup = BeautifulSoup(response.content, "html.parser")
        note = soup.select_one("details.slot-conflict .slot-conflict-summary")
        assert note.get_text(strip=True).startswith("This recipe can only replace C3")

    def test_unrepresentable_recipe_greys_every_slot_with_no_note(self, client, settings):
        self._xt2(settings)
        # Classic Negative is not a film simulation the X-T2 has at all. An
        # incompatible recipe needs no explanation, so no note is shown.
        recipe = _recipe(name="Superia", film_simulation="Classic Negative")

        response = client.get(f"/recipes/{recipe.id}/push/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.select(".slot-conflict") == []
        assert soup.select(".slot-dropped-note") == []
        assert not soup.select("button.slot-row:not([disabled])")


@pytest.mark.django_db
class TestSelectSlotViewHtmx:
    def _get(self, client, recipe_id):
        return client.get(f"/recipes/{recipe_id}/push/", HTTP_HX_REQUEST="true")

    def test_success_renders_partial_with_recipe_name_and_slots(self, client):
        recipe = _recipe(name="Kodak Portra")

        response = self._get(client, recipe.id)

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(string="Kodak Portra") is not None
        slot_labels = [el.get_text(strip=True) for el in soup.select(".slot-badge")]
        assert slot_labels == ["C1", "C2", "C3", "C4"]

    def test_success_slot_buttons_have_hx_post_to_push_view(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._get(client, recipe.id)

        soup = BeautifulSoup(response.content, "html.parser")
        buttons = soup.select(".slot-row")
        assert len(buttons) == 4
        for btn, slot in zip(buttons, ["C1", "C2", "C3", "C4"]):
            assert btn["hx-post"] == f"/recipes/{recipe.id}/push/{slot}/"

    def test_success_slot_buttons_target_slot_card(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._get(client, recipe.id)

        soup = BeautifulSoup(response.content, "html.parser")
        for btn in soup.select(".slot-btn"):
            assert btn["hx-target"] == "#slot-card"

    def test_camera_connection_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe(name="My Recipe")
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
        )

        response = self._get(client, recipe.id)

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Camera connection error" in soup.get_text()

    def test_camera_write_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe(name="My Recipe")
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        response = self._get(client, recipe.id)

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Camera write error" in soup.get_text()

    def test_unexpected_error_renders_partial_with_generic_message(self, client, settings):
        recipe = _recipe(name="My Recipe")

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = self._get(client, recipe.id)

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Unexpected error happened" in soup.get_text()


@pytest.mark.django_db
class TestSelectSlotViewInBrowserTransport:
    def test_declines_with_400_when_the_browser_owns_the_transport(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        response = client.get(f"/recipes/{recipe.id}/push/")

        assert response.status_code == 400
        assert "from your browser" in response.json()["error"]

    def test_htmx_gets_the_error_partial_so_the_overlay_can_show_it(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe(name="Browser Mode")

        response = client.get(f"/recipes/{recipe.id}/push/", headers={"HX-Request": "true"})

        # 200 so HTMX swaps the message in, matching how this view already
        # reports a camera connection failure.
        assert response.status_code == 200
        assert "from your browser" in response.content.decode()

    def test_never_touches_the_camera(self, client, settings):
        # The point of the guard: a headless server must not open USB looking
        # for a camera that is plugged into someone else's machine.
        settings.CAMERA_TRANSPORT = "browser"

        def _explode():
            raise AssertionError("the camera must not be touched in browser mode")

        settings.PTP_DEVICE = _explode
        recipe = _recipe(name="Browser Mode")

        assert client.get(f"/recipes/{recipe.id}/push/").status_code == 400
