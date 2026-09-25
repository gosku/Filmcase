import pytest
from bs4 import BeautifulSoup

from src.data.camera import constants
from src.domain.camera.ptp_device import CameraConnectionError
from tests.factories import (
    FujifilmRecipeFactory,
    RecipeCollectionFactory,
    RecipeCollectionMemberFactory,
)
from tests.fakes import FakePTPDevice


def _recipe(name):
    return FujifilmRecipeFactory(name=name, sharpness=0, high_iso_nr=0, clarity=0)


def _collection_with(names):
    collection = RecipeCollectionFactory()
    for position, name in enumerate(names):
        RecipeCollectionMemberFactory(group=collection, recipe=_recipe(name), position=position)
    return collection


def _get(client, collection_id):
    return client.get(f"/recipes/collections/{collection_id}/push/", HTTP_HX_REQUEST="true")


@pytest.mark.django_db
class TestSelectCollectionSlotsView:
    def test_renders_camera_model_and_slot_count(self, client, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T5")  # 7 slots
        collection = _collection_with(["Portra warm", "Chrome soft"])

        response = _get(client, collection.id)

        assert response.status_code == 200
        text = BeautifulSoup(response.content, "html.parser").get_text()
        assert "X-T5" in text
        assert "7 slots" in text

    def test_fewer_recipes_than_slots_assigns_leading_and_keeps_the_rest(self, client):
        # autouse fixture → FakePTPDevice(camera_name="X-S10") → 4 slots
        collection = _collection_with(["First", "Second"])

        response = _get(client, collection.id)

        soup = BeautifulSoup(response.content, "html.parser")
        target_badges = [b.get_text(strip=True) for b in soup.select(".cpush-badge--target")]
        kept_badges = [b.get_text(strip=True) for b in soup.select(".cpush-badge--kept")]
        assert target_badges == ["C1", "C2"]
        assert kept_badges == ["C3", "C4"]
        assert soup.select(".cpush-row--dropped") == []

    def test_more_recipes_than_slots_drops_the_surplus(self, client):
        collection = _collection_with(["r1", "r2", "r3", "r4", "r5"])

        response = _get(client, collection.id)

        soup = BeautifulSoup(response.content, "html.parser")
        target_badges = [b.get_text(strip=True) for b in soup.select(".cpush-badge--target")]
        dropped = soup.select(".cpush-row--dropped")
        assert target_badges == ["C1", "C2", "C3", "C4"]
        assert len(dropped) == 1
        assert "r5" in dropped[0].get_text()

    def test_assignment_rows_target_the_single_push_payload(self, client):
        collection = _collection_with(["Only"])

        response = _get(client, collection.id)

        soup = BeautifulSoup(response.content, "html.parser")
        row = soup.select_one(".cpush-row[data-recipe-id]")
        recipe_id = row["data-recipe-id"]
        assert row["data-payload-url"] == f"/recipes/{recipe_id}/camera-payload.json"

    def test_collection_not_found_returns_404(self, client):
        response = _get(client, 99999)

        assert response.status_code == 404

    def test_camera_connection_error_renders_partial_with_error(self, client, settings):
        collection = _collection_with(["First"])
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
        )

        response = _get(client, collection.id)

        assert response.status_code == 200
        assert "Camera connection error" in BeautifulSoup(response.content, "html.parser").get_text()

    def test_camera_connection_error_returns_503_without_htmx(self, client, settings):
        collection = _collection_with(["First"])
        settings.PTP_DEVICE = lambda: FakePTPDevice(
            set_errors={constants.PROP_SLOT_CURSOR: CameraConnectionError("USB timeout")}
        )

        response = client.get(f"/recipes/collections/{collection.id}/push/")

        assert response.status_code == 503


@pytest.mark.django_db
class TestSelectCollectionSlotsInBrowserTransport:
    def test_declines_with_400_when_the_browser_owns_the_transport(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        collection = _collection_with(["First"])

        response = client.get(f"/recipes/collections/{collection.id}/push/")

        assert response.status_code == 400
        assert "from your browser" in response.json()["error"]

    def test_never_touches_the_camera(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"

        def _explode():
            raise AssertionError("the camera must not be touched in browser mode")

        settings.PTP_DEVICE = _explode
        collection = _collection_with(["First"])

        assert client.get(f"/recipes/collections/{collection.id}/push/").status_code == 400
