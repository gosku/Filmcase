from unittest.mock import MagicMock

import pytest

from src.domain.camera.operations import push_recipe
from src.domain.camera.ptp_device import CameraConnectionError
from src.domain.images.dataclasses import FujifilmRecipeData


def _make_recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        film_simulation="Provia",
        dynamic_range="DR100",
        d_range_priority="Off",
        grain_roughness="Off",
        grain_size="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        highlight="0",
        shadow="0",
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        monochromatic_color_warm_cool="N/A",
        monochromatic_color_magenta_green="N/A",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


def _make_device(*, verify_values=None):
    """Build a mock PTPDevice.

    Args:
        verify_values: If given, a dict mapping PTP code → value that
            get_property_int returns during the verification phase.
            If None, read-back matches whatever was written.
    """
    device = MagicMock()
    device.set_property_uint16.return_value = 0
    device.set_property_int.return_value = 0
    device.set_property_string.return_value = 0
    device.ping.return_value = 0
    device.get_property_string.return_value = ""

    if verify_values is not None:
        device.get_property_int.side_effect = lambda code: verify_values.get(code, 0)
    else:
        # Track written values so read-back matches.
        written: dict[int, int] = {}

        def _set(code, value):
            written[code] = value
            return 0

        device.set_property_int.side_effect = _set
        device.get_property_int.side_effect = lambda code: written.get(code, 0)

    return device


class TestPushRecipeVerification:
    def test_verification_passes_when_readback_matches(self):
        device = _make_device()
        recipe = _make_recipe()

        failed = push_recipe(device, recipe, slot_index=1)
        assert failed == []

        # Verify that get_property_int was called (verification reads).
        assert device.get_property_int.call_count > 0

    def test_verification_detects_mismatched_readback(self):
        recipe = _make_recipe(film_simulation="Provia")
        # FilmSimulation (0xD192) was written as 1, but camera reports 99.
        device = _make_device(verify_values={0xD192: 99})

        failed = push_recipe(device, recipe, slot_index=1)
        assert 0xD192 in failed

    def test_verification_detects_name_mismatch(self, caplog):
        device = _make_device()
        device.get_property_string.return_value = "Wrong Name"

        push_recipe(device, _make_recipe(), slot_index=1, slot_name="My Recipe")

        assert any("Slot name verification failed" in rec.message for rec in caplog.records)

    def test_verification_handles_read_error_gracefully(self):
        device = _make_device()
        device.get_property_int.side_effect = CameraConnectionError("USB read failed")

        # Written values are tracked, but reads fail — all become mismatched.
        recipe = _make_recipe()
        failed = push_recipe(device, recipe, slot_index=1)
        assert len(failed) > 0
