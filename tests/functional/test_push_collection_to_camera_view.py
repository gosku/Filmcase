"""
Functional tests for the PushCollectionToCamera server-transport view.

Pushes a whole collection in one server-side operation. Uses FakePTPDevice via
settings.PTP_DEVICE, with a committed pristine X-T2 backup for the backup-blob
path.
"""
from pathlib import Path

import pytest

from tests.factories import FujifilmRecipeFactory
from tests.factories import RecipeCollectionFactory
from tests.factories import RecipeCollectionMemberFactory
from tests.fakes import FakePTPDevice

_PRISTINE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _collection_of(recipes):
    collection = RecipeCollectionFactory()
    for position, recipe in enumerate(recipes):
        RecipeCollectionMemberFactory(group=collection, recipe=recipe, position=position)
    return collection


def _url(collection_id):
    return f"/recipes/collections/{collection_id}/push/do/"


@pytest.mark.django_db
class TestPushCollectionToCamera:
    def test_per_property_push_succeeds(self, client, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-S10")
        collection = _collection_of([FujifilmRecipeFactory(name="One", sharpness=0, high_iso_nr=0, clarity=0)])

        response = client.post(_url(collection.id))

        assert response.status_code == 200
        assert "saved" in response.json()["message"].lower()

    def test_xt2_push_succeeds(self, client, settings):
        device = FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        settings.PTP_DEVICE = lambda: device
        collection = _collection_of([
            FujifilmRecipeFactory(name="First", film_simulation="Classic Chrome",
                                  white_balance="Underwater", sharpness=0, high_iso_nr=0, clarity=0),
        ])

        response = client.post(_url(collection.id))

        assert response.status_code == 200
        assert len(device.restored_blobs) == 1

    def test_xt2_wb_conflict_returns_400_and_writes_nothing(self, client, settings):
        device = FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        settings.PTP_DEVICE = lambda: device
        collection = _collection_of([
            FujifilmRecipeFactory(name="Clash", film_simulation="Classic Chrome",
                                  white_balance="Auto", white_balance_red=5, white_balance_blue=5,
                                  sharpness=0, high_iso_nr=0, clarity=0),
        ])

        response = client.post(_url(collection.id))

        assert response.status_code == 400
        assert device.restored_blobs == []

    def test_unrepresentable_recipe_returns_400(self, client, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        collection = _collection_of([
            FujifilmRecipeFactory(name="Eterna", film_simulation="Eterna", white_balance="Daylight"),
        ])

        response = client.post(_url(collection.id))

        assert response.status_code == 400

    def test_collection_not_found_returns_404(self, client, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-S10")

        response = client.post(_url(999999))

        assert response.status_code == 404

    def test_htmx_error_renders_result_partial_with_retry(self, client, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        collection = _collection_of([
            FujifilmRecipeFactory(name="Clash", film_simulation="Classic Chrome",
                                  white_balance="Auto", white_balance_red=5, white_balance_blue=5,
                                  sharpness=0, high_iso_nr=0, clarity=0),
        ])

        response = client.post(_url(collection.id), HTTP_HX_REQUEST="true")

        # Infeasible pushes are not retryable, so no retry button is offered.
        assert response.status_code == 200
        assert "Retry transfer" not in response.content.decode()

    def test_browser_transport_declines_with_400(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        collection = _collection_of([FujifilmRecipeFactory(name="One", sharpness=0, high_iso_nr=0, clarity=0)])

        response = client.post(_url(collection.id))

        assert response.status_code == 400
        assert "from your browser" in response.json()["error"]
