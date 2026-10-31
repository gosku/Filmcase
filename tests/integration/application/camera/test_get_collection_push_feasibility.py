"""
Integration tests for the get_collection_push_feasibility use case.

Uses FakePTPDevice with a committed pristine X-T2 backup via settings.PTP_DEVICE.
"""
from pathlib import Path

import pytest

from src.application.usecases.camera import get_collection_push_feasibility as feasibility_uc
from tests.factories import FujifilmRecipeFactory
from tests.factories import RecipeCollectionFactory
from tests.factories import RecipeCollectionMemberFactory
from tests.fakes import FakePTPDevice

_PRISTINE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _collection_with(*recipes) -> int:
    group = RecipeCollectionFactory(name="Set")
    for position, recipe in enumerate(recipes):
        RecipeCollectionMemberFactory(group=group, recipe=recipe, position=position)
    return group.pk


def _run(collection_id: int):
    return feasibility_uc.get_collection_push_feasibility(collection_id=collection_id)


@pytest.mark.django_db
class TestPerPropertyCollectionFeasibility:
    def test_always_feasible_and_reads_the_slots(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-S10")
        collection_id = _collection_with(FujifilmRecipeFactory(name="One"))

        result = _run(collection_id)

        assert result.camera_model == "X-S10"
        assert result.ok
        assert result.dropped_fields == ()
        assert result.unrepresentable == ()
        assert len(result.slots) == 4


@pytest.mark.django_db
class TestBackupBlobCollectionFeasibility:
    def test_feasible_collection_is_ok(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="First", film_simulation="Classic Chrome",
                                  white_balance="Underwater"),
            FujifilmRecipeFactory(name="Second", film_simulation="Provia",
                                  white_balance="Fluorescent 3"),
        )

        result = _run(collection_id)

        assert result.camera_model == "X-T2"
        assert result.ok
        assert result.conflicts == ()
        assert result.unrepresentable == ()

    def test_unrepresentable_recipe_is_reported_by_id(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        bad = FujifilmRecipeFactory(name="Eterna", film_simulation="Eterna", white_balance="Daylight")
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="Good", film_simulation="Provia", white_balance="Underwater"),
            bad,
        )

        result = _run(collection_id)

        assert not result.ok
        assert [u.recipe_id for u in result.unrepresentable] == [bad.pk]
        assert result.unrepresentable[0].field == "film_simulation"
        assert result.unrepresentable[0].value == "Eterna"

    def test_shared_wb_conflict_is_reported(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T2", backup=_PRISTINE)
        collection_id = _collection_with(
            FujifilmRecipeFactory(name="Clash", film_simulation="Provia",
                                  white_balance="Auto", white_balance_red=5, white_balance_blue=5),
        )

        result = _run(collection_id)

        assert not result.ok
        assert result.conflicts


@pytest.mark.django_db
class TestCollectionNotFound:
    def test_missing_collection_raises(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-S10")

        with pytest.raises(feasibility_uc.CollectionNotFound):
            _run(999999)
