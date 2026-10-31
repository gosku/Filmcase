"""
Integration tests for the push_collection_to_camera use case.

Covers both transports: a per-property body (X-S10) writes each assigned slot in
turn, and a backup-blob body (X-T2) edits one settings backup and restores it
once. Uses FakePTPDevice via settings.PTP_DEVICE.
"""
from pathlib import Path

import pytest

from src.application.usecases.camera import push_collection as push_collection_uc
from src.data.camera import constants
from src.domain.camera import xt2_backup
from tests.factories import FujifilmRecipeFactory
from tests.factories import RecipeCollectionFactory
from tests.factories import RecipeCollectionMemberFactory
from tests.fakes import FakePTPDevice

_PRISTINE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()
_FILM_SIM_CODE = constants.CUSTOM_SLOT_CODES["FilmSimulation"]


def _collection_with(*recipes) -> int:
    group = RecipeCollectionFactory(name="Set")
    for position, recipe in enumerate(recipes):
        RecipeCollectionMemberFactory(group=group, recipe=recipe, position=position)
    return group.pk


@pytest.mark.django_db
class TestPerPropertyCollectionPush:
    def test_writes_the_collection_without_error(self, settings):
        device = FakePTPDevice(camera_name="X-S10")
        settings.PTP_DEVICE = lambda: device
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="One", film_simulation="Provia"),
            FujifilmRecipeFactory(name="Two", film_simulation="Velvia"),
        )

        push_collection_uc.push_collection_to_camera(collection_id=collection_id)

        # A per-property body stores by code (last write wins), so this confirms
        # the loop ran and wrote the film simulation.
        assert device.get_property_int(_FILM_SIM_CODE) != 0


@pytest.mark.django_db
class TestBackupBlobCollectionPush:
    def _xt2_device(self) -> FakePTPDevice:
        return FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)

    def test_restores_the_backup_once_with_every_assignment(self, settings):
        device = self._xt2_device()
        settings.PTP_DEVICE = lambda: device
        # Two WB entries no pristine slot uses, and different from each other, so
        # the push is feasible.
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="First", film_simulation="Classic Chrome",
                                  white_balance="Underwater"),
            FujifilmRecipeFactory(name="Second", film_simulation="Provia",
                                  white_balance="Fluorescent 3"),
        )

        push_collection_uc.push_collection_to_camera(collection_id=collection_id)

        assert len(device.restored_blobs) == 1
        blob = device.restored_blobs[0]
        assert xt2_backup.decode_slot_recipe(blob, 1).name == "First"
        assert xt2_backup.decode_slot_recipe(blob, 2).name == "Second"

    def test_shared_wb_conflict_refuses_and_writes_nothing(self, settings):
        device = self._xt2_device()
        settings.PTP_DEVICE = lambda: device
        # Auto is shared by pristine slots; retuning its shift would change them.
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="Clash", film_simulation="Provia",
                                  white_balance="Auto", white_balance_red=5, white_balance_blue=5),
        )

        with pytest.raises(push_collection_uc.PushNotFeasibleError):
            push_collection_uc.push_collection_to_camera(collection_id=collection_id)

        assert device.restored_blobs == []


@pytest.mark.django_db
class TestCollectionNotFound:
    def test_missing_collection_raises_before_touching_the_camera(self, settings):
        device = FakePTPDevice(camera_name="X-S10")
        settings.PTP_DEVICE = lambda: device

        with pytest.raises(push_collection_uc.CollectionNotFound):
            push_collection_uc.push_collection_to_camera(collection_id=999999)
