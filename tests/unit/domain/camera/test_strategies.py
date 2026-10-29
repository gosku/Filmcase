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
