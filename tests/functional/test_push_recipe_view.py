import pytest
from bs4 import BeautifulSoup

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from tests.factories import FujifilmRecipeFactory
from tests.fakes import FakePTPDevice


def _recipe(**kwargs):
    """Create a recipe with all fields required by recipe_from_db and push_recipe_to_camera."""
    kwargs.setdefault("name", "Test")
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


@pytest.mark.django_db
class TestPushRecipeToCameraView:
    def test_success_returns_saved_message(self, client):
        recipe = _recipe(name="My Recipe")

        response = client.post(f"/recipes/{recipe.id}/push/C4/")

        assert response.status_code == 200
        assert response.json() == {"message": "Recipe saved in C4"}

    def test_success_message_reflects_slot(self, client):
        recipe = _recipe(name="Slot Test")

        response = client.post(f"/recipes/{recipe.id}/push/C7/")

        assert response.status_code == 200
        assert response.json()["message"] == "Recipe saved in C7"

    def test_recipe_not_found_returns_404(self, client):
        response = client.post("/recipes/99999/push/C1/")

        assert response.status_code == 404

    def test_invalid_slot_returns_404(self, client):
        recipe = _recipe()

        response = client.post(f"/recipes/{recipe.id}/push/INVALID/")

        assert response.status_code == 404

    def test_camera_connection_error_returns_503(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        response = client.post(f"/recipes/{recipe.id}/push/C2/")

        assert response.status_code == 503
        assert "No camera found" in response.json()["error"]

    def test_recipe_write_error_returns_500_with_failed_properties(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = client.post(f"/recipes/{recipe.id}/push/C3/")

        assert response.status_code == 500
        data = response.json()
        assert "couldn't be saved" in data["error"]
        assert "SlotName" in data["error"]

    def test_camera_write_error_returns_500(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraWriteError(constants.PROP_SLOT_CURSOR, 1, 0x2005)}
        )

        response = client.post(f"/recipes/{recipe.id}/push/C1/")

        assert response.status_code == 500
        assert "rejected a write" in response.json()["error"]

    def test_unexpected_error_returns_500_with_generic_message(self, client, settings):
        recipe = _recipe()

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = client.post(f"/recipes/{recipe.id}/push/C1/")

        assert response.status_code == 500
        assert response.json() == {"error": "An unexpected error occurred. Please try again."}


@pytest.mark.django_db
class TestPushRecipeToCameraViewHtmx:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

    def _post(self, client, recipe_id, slot):
        return client.post(f"/recipes/{recipe_id}/push/{slot}/", HTTP_HX_REQUEST="true")

    # ------------------------------------------------------------------
    # Success state
    # ------------------------------------------------------------------

    def test_success_renders_animated_check(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._post(client, recipe.id, "C4")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-check-svg") is not None

    def test_success_renders_big_message_with_slot(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._post(client, recipe.id, "C4")

        soup = BeautifulSoup(response.content, "html.parser")
        message = soup.find(class_="push-result-message")
        assert message is not None
        assert "C4" in message.get_text()

    def test_success_result_has_no_slot_buttons(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._post(client, recipe.id, "C4")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.select(".slot-btn") == []

    # ------------------------------------------------------------------
    # Error state
    # ------------------------------------------------------------------

    def test_error_result_has_no_slot_buttons(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C1")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.select(".slot-btn") == []

    def test_error_result_shows_friendly_message(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C1")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result-err-message") is not None

    def test_error_result_does_not_expose_raw_exception(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("raw internal detail")}
        )

        response = self._post(client, recipe.id, "C2")

        assert "raw internal detail" not in response.content.decode()

    def test_error_result_shows_retry_button(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C3")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-retry-btn") is not None

    def test_error_retry_button_posts_to_same_endpoint(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C3")

        soup = BeautifulSoup(response.content, "html.parser")
        retry_btn = soup.find(class_="push-retry-btn")
        assert retry_btn["hx-post"] == f"/recipes/{recipe.id}/push/C3/"

    def test_error_retry_button_targets_slot_card(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C3")

        soup = BeautifulSoup(response.content, "html.parser")
        retry_btn = soup.find(class_="push-retry-btn")
        assert retry_btn["hx-target"] == "#slot-card"

    def test_error_retry_button_label_includes_slot(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C5")

        soup = BeautifulSoup(response.content, "html.parser")
        retry_btn = soup.find(class_="push-retry-btn")
        assert "C5" in retry_btn.get_text()

    # ------------------------------------------------------------------
    # Error messages per exception type
    # ------------------------------------------------------------------

    def test_camera_connection_error_renders_no_camera_message(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        response = self._post(client, recipe.id, "C2")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result-err-message") is not None
        assert "No camera found" in soup.get_text()

    def test_recipe_write_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C1")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result-err-message") is not None
        assert "couldn't be saved" in soup.get_text()

    def test_camera_write_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraWriteError(constants.PROP_SLOT_CURSOR, 1, 0x2005)}
        )

        response = self._post(client, recipe.id, "C3")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result-err-message") is not None
        assert "rejected a write" in soup.get_text()

    def test_unexpected_error_renders_partial_with_generic_message(self, client, settings):
        recipe = _recipe()

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = self._post(client, recipe.id, "C1")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result-err-message") is not None
        assert "unexpected error" in soup.get_text().lower()


@pytest.mark.django_db
class TestPushRecipeToCameraInBrowserTransport:
    def test_declines_with_400_when_the_browser_owns_the_transport(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe()

        response = client.post(f"/recipes/{recipe.id}/push/C1/")

        assert response.status_code == 400
        assert "from your browser" in response.json()["error"]

    def test_htmx_gets_the_error_partial_with_a_working_retry_target(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        recipe = _recipe()

        response = client.post(
            f"/recipes/{recipe.id}/push/C2/", headers={"HX-Request": "true"}
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        retry = soup.select_one(".push-retry-btn")
        assert retry is not None
        assert retry["hx-post"] == f"/recipes/{recipe.id}/push/C2/"

    def test_never_touches_the_camera(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"

        def _explode():
            raise AssertionError("the camera must not be touched in browser mode")

        settings.PTP_DEVICE = _explode
        recipe = _recipe()

        assert client.post(f"/recipes/{recipe.id}/push/C1/").status_code == 400
