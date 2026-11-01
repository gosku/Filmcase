"""
Integration tests for X-T2 recipe compatibility through the camera use cases.

The X-T2 is driven by the backup-blob strategy. These assert the application
layer end to end, not the codec in isolation: a stored recipe with fields the
X-T2 has no control for pushes with those fields dropped (and the drop reported
by the slot read), while a recipe the X-T2 cannot represent at all is refused
with nothing written.

Uses FakePTPDevice with a committed pristine X-T2 backup via settings.PTP_DEVICE.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.usecases.camera import get_camera_slots as get_camera_slots_uc
from src.application.usecases.camera import push_recipe as push_recipe_uc
from src.data import models
from src.domain.camera import xt2_backup
from tests.factories import FujifilmRecipeFactory
from tests.fakes import FakePTPDevice

_PRISTINE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _xt2_device(**kwargs: object) -> FakePTPDevice:
    # Underwater is a WB entry no pristine slot uses, so a push to any slot is
    # feasible by default: the drop/representability behaviour is what is under test.
    return FakePTPDevice(camera_name="X-T2", backup=_PRISTINE, **kwargs)


def _recipe_with_unsupported_fields() -> models.FujifilmRecipe:
    """A recipe whose film sim the X-T2 has, but carrying five fields it lacks."""
    return FujifilmRecipeFactory(
        name="XT2",
        film_simulation="Classic Chrome",
        white_balance="Underwater",
        # Real grain, so grain_size is not normalized away: the X-T2 has grain
        # strength (Weak is representable) but no grain-size control, so the size
        # is the field that gets dropped.
        grain_roughness="Weak",
        grain_size="Large",
        dynamic_range="DR100",
        clarity=Decimal("3"),
        color_chrome_effect="Strong",
        color_chrome_fx_blue="Strong",
        d_range_priority="Strong",
        white_balance_red=0,
        white_balance_blue=0,
        color=Decimal("0"),
        sharpness=Decimal("0"),
        high_iso_nr=Decimal("0"),
        highlight=Decimal("0"),
        shadow=Decimal("0"),
    )


@pytest.mark.django_db
class TestUnsupportedFieldsAreDroppedAndReported:
    def test_slot_read_reports_the_dropped_fields(self, settings):
        settings.PTP_DEVICE = _xt2_device
        recipe = _recipe_with_unsupported_fields()

        result = get_camera_slots_uc.get_camera_slots(recipe=recipe)

        assert result.dropped_fields == (
            "Clarity",
            "Color Chrome Effect",
            "Color Chrome FX Blue",
            "D-Range Priority",
            "Grain Size",
        )
        # None of the dropped fields make the recipe infeasible for any slot.
        assert all(f.feasible for f in result.feasibility)

    def test_push_succeeds_and_lands_the_supported_fields(self, settings):
        device = _xt2_device()
        settings.PTP_DEVICE = lambda: device
        recipe = _recipe_with_unsupported_fields()

        push_recipe_uc.push_recipe_to_camera(recipe, slot_index=1)

        assert len(device.restored_blobs) == 1
        stored = xt2_backup.decode_slot_recipe(device.restored_blobs[0], 1)
        assert stored.name == "XT2"
        assert stored.film_simulation == "Classic Chrome"


@pytest.mark.django_db
class TestUnrepresentableRecipeIsRefused:
    def test_absent_film_sim_raises_and_writes_nothing(self, settings):
        device = _xt2_device()
        settings.PTP_DEVICE = lambda: device
        recipe = FujifilmRecipeFactory(
            name="ETERNA",
            film_simulation="Eterna",  # the X-T2 has no Eterna
            white_balance="Daylight",
            grain_roughness="Off",
            dynamic_range="DR100",
        )

        with pytest.raises(push_recipe_uc.RecipeNotRepresentable) as exc_info:
            push_recipe_uc.push_recipe_to_camera(recipe, slot_index=1)

        assert exc_info.value.field == "film_simulation"
        assert exc_info.value.value == "Eterna"
        assert device.restored_blobs == []
