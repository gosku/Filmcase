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
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

    def test_success_returns_saved_message(self, client):
        recipe = _recipe(name="My Recipe")
        # autouse fixture → FakePTPDevice → all writes succeed

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
        assert "Camera connection error" in response.json()["error"]

    def test_recipe_write_error_returns_500_with_failed_properties(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = client.post(f"/recipes/{recipe.id}/push/C3/")

        assert response.status_code == 500
        data = response.json()
        assert "Recipe write failed" in data["error"]
        assert "SlotName" in data["error"]

    def test_camera_write_error_returns_500(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraWriteError(constants.PROP_SLOT_CURSOR, 1, 0x2005)}
        )

        response = client.post(f"/recipes/{recipe.id}/push/C1/")

        assert response.status_code == 500
        assert "Camera write error" in response.json()["error"]

    def test_unexpected_error_returns_500_with_generic_message(self, client, settings):
        recipe = _recipe()

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = client.post(f"/recipes/{recipe.id}/push/C1/")

        assert response.status_code == 500
        assert response.json() == {"error": "Unexpected error happened"}


@pytest.mark.django_db
class TestPushRecipeToCameraViewHtmx:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

    def _post(self, client, recipe_id, slot):
        return client.post(f"/recipes/{recipe_id}/push/{slot}/", HTTP_HX_REQUEST="true")

    def test_success_renders_partial_with_success_message(self, client):
        recipe = _recipe(name="My Recipe")

        response = self._post(client, recipe.id, "C4")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result--ok") is not None
        assert "C4" in soup.get_text()

    def test_recipe_write_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_NAME: 0x2005}
        )

        response = self._post(client, recipe.id, "C1")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result--err") is not None
        assert "Recipe write failed" in soup.get_text()

    def test_camera_connection_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005}
        )

        response = self._post(client, recipe.id, "C2")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result--err") is not None
        assert "Camera connection error" in soup.get_text()

    def test_camera_write_error_renders_partial_with_error(self, client, settings):
        recipe = _recipe()
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraWriteError(constants.PROP_SLOT_CURSOR, 1, 0x2005)}
        )

        response = self._post(client, recipe.id, "C3")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result--err") is not None
        assert "Camera write error" in soup.get_text()

    def test_unexpected_error_renders_partial_with_generic_message(self, client, settings):
        recipe = _recipe()

        def raise_runtime_error():
            raise RuntimeError("Unexpected boom")

        settings.PTP_DEVICE = raise_runtime_error

        response = self._post(client, recipe.id, "C1")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="push-result--err") is not None
        assert "Unexpected error happened" in soup.get_text()
