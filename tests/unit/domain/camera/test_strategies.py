"""
Unit tests for camera strategies and the strategy registry.
"""
from __future__ import annotations

import pytest

from src.data.camera import constants
from src.domain.camera import profiles
from src.domain.camera import strategies
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.camera.validation import RecipeValidationError
from src.domain.images.dataclasses import FujifilmRecipeData
from tests.fakes import FakePTPDevice

_FILM_SIM_CODE = constants.CUSTOM_SLOT_CODES["FilmSimulation"]


def _make_recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        name="Test Recipe",
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


class TestGetStrategy:
    def test_known_model_resolves_to_per_property_strategy(self) -> None:
        strategy = strategies.get_strategy("X-S10")
        assert isinstance(strategy, strategies.PerPropertyStrategy)
        assert strategy.profile is profiles.PER_PROPERTY_PROFILE

    def test_unknown_model_resolves_to_per_property_strategy(self) -> None:
        strategy = strategies.get_strategy("NOT-A-CAMERA")
        assert isinstance(strategy, strategies.PerPropertyStrategy)


class TestPerPropertyStrategyReadSlots:
    def _strategy(self) -> strategies.PerPropertyStrategy:
        return strategies.PerPropertyStrategy(profile=profiles.PER_PROPERTY_PROFILE)

    def test_returns_one_state_per_slot_in_order(self) -> None:
        states = self._strategy().read_slots(FakePTPDevice(), slot_count=4)
        assert [s.index for s in states] == [1, 2, 3, 4]

    def test_reads_name_and_film_sim(self) -> None:
        device = FakePTPDevice(
            string_values={constants.PROP_SLOT_NAME: "My Slot"},
            int_values={_FILM_SIM_CODE: 11},
        )
        states = self._strategy().read_slots(device, slot_count=2)
        assert all(s.name == "My Slot" and s.film_sim_ptp == 11 for s in states)

    def test_empty_when_no_slots(self) -> None:
        assert self._strategy().read_slots(FakePTPDevice(), slot_count=0) == []

    def test_raises_connection_error_when_read_fails(self) -> None:
        device = FakePTPDevice(default_get_error=CameraConnectionError("USB timeout"))
        with pytest.raises(CameraConnectionError):
            self._strategy().read_slots(device, slot_count=1)


class TestPerPropertyStrategyValidateRecipe:
    def _strategy(self) -> strategies.PerPropertyStrategy:
        return strategies.PerPropertyStrategy(profile=profiles.PER_PROPERTY_PROFILE)

    def test_valid_recipe_passes(self) -> None:
        self._strategy().validate_recipe(_make_recipe())

    def test_invalid_recipe_raises(self) -> None:
        with pytest.raises(RecipeValidationError):
            self._strategy().validate_recipe(_make_recipe(film_simulation="Unknown Film"))


class TestPerPropertyStrategyPushRecipe:
    def _strategy(self) -> strategies.PerPropertyStrategy:
        return strategies.PerPropertyStrategy(profile=profiles.PER_PROPERTY_PROFILE)

    def test_writes_film_simulation_to_slot(self) -> None:
        device = FakePTPDevice()
        self._strategy().push_recipe(device, _make_recipe(film_simulation="Velvia"), slot_index=1)
        # Velvia is PTP value 2; a successful push leaves it in the slot store.
        assert device.get_property_int(_FILM_SIM_CODE) == constants.FILM_SIMULATION_TO_PTP["Velvia"]

    def test_raises_recipe_write_error_when_camera_rejects_property(self) -> None:
        # The camera rejects the film-sim write (non-zero rc, no transport error);
        # the push continues but reports the failed property.
        device = FakePTPDevice(set_rejection_codes={_FILM_SIM_CODE: 0x2005})
        with pytest.raises(strategies.RecipeWriteError) as exc_info:
            self._strategy().push_recipe(device, _make_recipe(), slot_index=1)
        assert "FilmSimulation" in exc_info.value.failed_properties

    def test_cursor_rejection_becomes_connection_error(self) -> None:
        device = FakePTPDevice(set_rejection_codes={constants.PROP_SLOT_CURSOR: 0x2005})
        with pytest.raises(CameraConnectionError):
            self._strategy().push_recipe(device, _make_recipe(), slot_index=1)


# ---------------------------------------------------------------------------
# BackupBlobStrategy (X-T2) and the collection / feasibility surface
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from src.data.camera import constants_xt2  # noqa: E402
from src.domain.camera import xt2_backup  # noqa: E402
from src.domain.camera.ptp_device import RestoreAckTimeout  # noqa: E402

_PRISTINE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _xt2_recipe(**overrides: object) -> FujifilmRecipeData:
    # Underwater is a WB entry no pristine slot uses, so a push to any slot is
    # feasible by default; override white_balance to force a conflict.
    base: dict[str, object] = {"film_simulation": "Classic Chrome", "white_balance": "Underwater"}
    base.update(overrides)
    return _make_recipe(**base)


def _xt2_device(**kwargs: object) -> FakePTPDevice:
    return FakePTPDevice(camera_name="X-T2", backup=_PRISTINE, **kwargs)


class TestGetStrategyBackupBlob:
    def test_x_t2_resolves_to_backup_blob_strategy(self) -> None:
        assert isinstance(strategies.get_strategy("X-T2"), strategies.BackupBlobStrategy)

    def test_other_models_stay_per_property(self) -> None:
        assert isinstance(strategies.get_strategy("X-S10"), strategies.PerPropertyStrategy)


class TestBackupBlobReadSlots:
    def test_reads_seven_slots_from_the_backup(self) -> None:
        strategy = strategies.get_strategy("X-T2")
        states = strategy.read_slots(_xt2_device(), slot_count=7)
        assert [s.index for s in states] == [1, 2, 3, 4, 5, 6, 7]
        assert states[1].name == "KODACHROME 2"


class TestBackupBlobPushRecipe:
    def _strategy(self) -> strategies.BackupBlobStrategy:
        return strategies.BackupBlobStrategy(profile=profiles.XT2_PROFILE)

    def test_feasible_push_restores_once_and_verifies(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        device = _xt2_device()
        self._strategy().push_recipe(device, _xt2_recipe(name="NEW"), slot_index=1)
        assert len(device.restored_blobs) == 1
        # The restored blob has the recipe in C1.
        assert xt2_backup.decode_slot_recipe(device.restored_blobs[0], 1).name == "NEW"

    def test_infeasible_wb_conflict_raises_before_writing(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        device = _xt2_device()
        # Auto is shared by pristine slots; a new Auto shift would retune them.
        recipe = _make_recipe(white_balance="Auto", white_balance_red=5, white_balance_blue=5)
        with pytest.raises(strategies.PushNotFeasibleError):
            self._strategy().push_recipe(device, recipe, slot_index=1)
        assert device.restored_blobs == []

    def test_unrepresentable_film_sim_raises(self) -> None:
        device = _xt2_device()
        with pytest.raises(xt2_backup.RecipeNotRepresentable):
            self._strategy().push_recipe(device, _xt2_recipe(film_simulation="Eterna"), slot_index=1)
        assert device.restored_blobs == []

    def test_invalid_backup_refuses_to_write(self) -> None:
        device = FakePTPDevice(camera_name="X-T2", backup=b"\x00" * 5660)
        with pytest.raises(strategies.BackupValidationError):
            self._strategy().push_recipe(device, _xt2_recipe(), slot_index=1)
        assert device.restored_blobs == []

    def test_verify_mismatch_raises_recipe_write_error(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        # The camera "stores" a different film-sim byte in C1 than was pushed.
        drift = {constants_xt2.SLOT0_OFFSET + constants_xt2.OFF_FILM_SIMULATION: 0x00}
        device = _xt2_device(restore_drift=drift)
        with pytest.raises(strategies.RecipeWriteError):
            self._strategy().push_recipe(device, _xt2_recipe(film_simulation="Velvia"), slot_index=1)

    def test_lost_ack_with_verify_confirms_by_readback(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        device = _xt2_device(restore_ack_times_out=True)
        # The fake stores the blob before raising, so the read-back matches.
        self._strategy().push_recipe(device, _xt2_recipe(name="OK"), slot_index=1)

    def test_lost_ack_without_verify_raises(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = False
        device = _xt2_device(restore_ack_times_out=True)
        with pytest.raises(RestoreAckTimeout):
            self._strategy().push_recipe(device, _xt2_recipe(), slot_index=1)


class TestBackupBlobPushCollection:
    def _strategy(self) -> strategies.BackupBlobStrategy:
        return strategies.BackupBlobStrategy(profile=profiles.XT2_PROFILE)

    def test_pushes_all_in_one_restore(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        device = _xt2_device()
        # Underwater and Fluorescent 3 are WB entries no kept slot uses.
        assignments = [
            (1, _xt2_recipe(name="A", white_balance="Underwater")),
            (2, _xt2_recipe(name="B", white_balance="Fluorescent 3")),
        ]
        self._strategy().push_collection(device, assignments)
        assert len(device.restored_blobs) == 1  # one blob, one restore

    def test_conflicting_collection_raises(self, settings) -> None:
        settings.CAMERA_VERIFY_WRITES = True
        device = _xt2_device()
        assignments = [
            (1, _xt2_recipe(white_balance="Underwater", white_balance_red=3)),
            (2, _xt2_recipe(white_balance="Underwater", white_balance_red=-3)),
        ]
        with pytest.raises(strategies.PushNotFeasibleError):
            self._strategy().push_collection(device, assignments)
        assert device.restored_blobs == []


class TestBackupBlobSlotFeasibility:
    def _strategy(self) -> strategies.BackupBlobStrategy:
        return strategies.BackupBlobStrategy(profile=profiles.XT2_PROFILE)

    def test_free_wb_is_feasible_for_every_slot(self) -> None:
        result = self._strategy().plan_feasibility(_xt2_device(), _xt2_recipe(), slot_count=7)
        assert all(f.feasible for f in result.slots)

    def test_shared_wb_conflict_marks_slots_infeasible_with_a_reason(self) -> None:
        recipe = _make_recipe(white_balance="Auto", white_balance_red=5, white_balance_blue=5)
        result = self._strategy().plan_feasibility(_xt2_device(), recipe, slot_count=7)
        infeasible = [f for f in result.slots if not f.feasible]
        assert infeasible
        assert all(f.reason for f in infeasible)

    def test_unrepresentable_recipe_greys_out_all_slots(self) -> None:
        recipe = _xt2_recipe(film_simulation="Eterna")
        result = self._strategy().plan_feasibility(_xt2_device(), recipe, slot_count=7)
        assert all(not f.feasible for f in result.slots)

    def test_reports_fields_the_x_t2_drops(self) -> None:
        recipe = _xt2_recipe(clarity="3", color_chrome_effect="Strong")
        result = self._strategy().plan_feasibility(_xt2_device(), recipe, slot_count=7)
        assert all(f.feasible for f in result.slots)
        assert result.dropped_fields == ("Clarity", "Color Chrome Effect")


class TestPerPropertyCollectionAndFeasibility:
    def _strategy(self) -> strategies.PerPropertyStrategy:
        return strategies.PerPropertyStrategy(profile=profiles.PER_PROPERTY_PROFILE)

    def test_push_collection_writes_each_assignment(self) -> None:
        device = FakePTPDevice()
        self._strategy().push_collection(device, [(1, _make_recipe()), (2, _make_recipe())])
        # The last write landed; a FakePTPDevice stores by code, so this just
        # confirms the loop ran without error and wrote the film simulation.
        assert device.get_property_int(_FILM_SIM_CODE) != 0

    def test_plan_feasibility_all_feasible_and_drops_nothing(self) -> None:
        result = self._strategy().plan_feasibility(FakePTPDevice(), _make_recipe(), slot_count=4)
        assert [f.slot_index for f in result.slots] == [1, 2, 3, 4]
        assert all(f.feasible for f in result.slots)
        assert result.dropped_fields == ()
