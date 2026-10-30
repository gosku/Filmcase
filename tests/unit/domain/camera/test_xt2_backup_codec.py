"""
Unit tests for the X-T2 backup codec, against the committed pristine blob.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.camera import xt2_backup
from src.domain.images.dataclasses import FujifilmRecipeData

_PRISTINE = (
    Path(__file__).resolve().parents[3] / "fixtures" / "camera" / "xt2_backup_pristine.bin"
).read_bytes()


def _recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        name="Test Recipe",
        film_simulation="Classic Chrome",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Daylight",
        white_balance_red=0,
        white_balance_blue=0,
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR200",
        highlight="0",
        shadow="0",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


class TestValidateBackup:
    def test_pristine_blob_is_valid(self) -> None:
        assert xt2_backup.validate_backup(_PRISTINE).ok

    def test_wrong_size_fails(self) -> None:
        assert not xt2_backup.validate_backup(_PRISTINE[:-1]).ok

    def test_bad_magic_fails(self) -> None:
        corrupt = b"\x00" * 8 + _PRISTINE[8:]
        assert not xt2_backup.validate_backup(corrupt).ok

    def test_invalid_film_sim_byte_fails(self) -> None:
        from src.data.camera import constants_xt2 as xt2

        blob = bytearray(_PRISTINE)
        blob[xt2.SLOT0_OFFSET + xt2.OFF_FILM_SIMULATION] = 0x7F  # not a valid film-sim byte
        assert not xt2_backup.validate_backup(bytes(blob)).ok


class TestDecode:
    def test_seven_slots(self) -> None:
        states = xt2_backup.decode_slot_states(_PRISTINE)
        assert [s.index for s in states] == [1, 2, 3, 4, 5, 6, 7]

    def test_decodes_known_slot(self) -> None:
        states = xt2_backup.decode_slot_states(_PRISTINE)
        assert states[1].name == "KODACHROME 2"
        assert states[1].film_sim_name == "Classic Chrome"

    def test_decode_recipe_fields(self) -> None:
        recipe = xt2_backup.decode_slot_recipe(_PRISTINE, 2)
        assert recipe.film_simulation == "Classic Chrome"
        assert recipe.white_balance == "Auto"
        assert recipe.dynamic_range == "DR200"
        # X-T2 lacks these; they decode empty.
        assert recipe.clarity == ""
        assert recipe.color_chrome_effect == ""
        assert recipe.grain_size == ""


class TestMapRecipe:
    def test_supported_recipe_maps_with_no_drops(self) -> None:
        mapping = xt2_backup.map_recipe(_recipe())
        assert mapping.dropped == ()
        assert mapping.film_simulation == "Classic Chrome"

    def test_unsupported_fields_are_dropped_and_reported(self) -> None:
        mapping = xt2_backup.map_recipe(
            _recipe(
                clarity="2",
                color_chrome_effect="Strong",
                color_chrome_fx_blue="Weak",
                d_range_priority="Strong",
                grain_roughness="Weak",
                grain_size="Large",
            )
        )
        assert set(mapping.dropped) == {
            "Clarity",
            "Color Chrome Effect",
            "Color Chrome FX Blue",
            "D-Range Priority",
            "Grain Size",
        }

    def test_film_sim_absent_on_xt2_raises(self) -> None:
        with pytest.raises(xt2_backup.RecipeNotRepresentable) as exc:
            xt2_backup.map_recipe(_recipe(film_simulation="Eterna"))
        assert exc.value.field == "film_simulation"

    def test_wb_mode_absent_on_xt2_raises(self) -> None:
        with pytest.raises(xt2_backup.RecipeNotRepresentable) as exc:
            xt2_backup.map_recipe(_recipe(white_balance="Auto (white priority)"))
        assert exc.value.field == "white_balance"

    def test_kelvin_is_snapped_to_the_nearest_step(self) -> None:
        mapping = xt2_backup.map_recipe(_recipe(white_balance="5100K"))
        assert mapping.white_balance == "Kelvin"
        assert mapping.kelvin == 5000  # nearest X-T2 step

    def test_out_of_range_tone_raises(self) -> None:
        with pytest.raises(xt2_backup.RecipeNotRepresentable):
            xt2_backup.map_recipe(_recipe(highlight="+5"))  # X-T2 highlight max is +4


class TestApplyRecipe:
    def test_apply_then_decode_round_trips(self) -> None:
        mapping = xt2_backup.map_recipe(
            _recipe(name="ROUNDTRIP", film_simulation="Velvia", white_balance="Daylight",
                    white_balance_red=2, white_balance_blue=-3, highlight="+1", shadow="-2",
                    color="+2", sharpness="-1", high_iso_nr="+3", dynamic_range="DR400")
        )
        edited = xt2_backup.apply_recipe(_PRISTINE, 0, mapping)
        assert xt2_backup.validate_backup(edited).ok
        back = xt2_backup.decode_slot_recipe(edited, 1)
        assert back.name == "ROUNDTRIP"
        assert back.film_simulation == "Velvia"
        assert back.white_balance == "Daylight"
        assert (back.white_balance_red, back.white_balance_blue) == (2, -3)
        assert back.highlight == "+1"
        assert back.shadow == "-2"
        assert back.color == "+2"
        assert back.sharpness == "-1"
        assert back.high_iso_nr == "+3"
        assert back.dynamic_range == "DR400"


class TestFeasibility:
    def test_free_wb_entry_is_feasible(self) -> None:
        # Underwater is not used by any slot in the pristine blob.
        mapping = xt2_backup.map_recipe(_recipe(white_balance="Underwater", white_balance_red=5))
        assert xt2_backup.check_feasibility(_PRISTINE, 0, mapping).ok

    def test_shared_wb_with_different_shift_conflicts(self) -> None:
        # Several pristine slots use Auto; pushing Auto with a new shift into a
        # different slot would retune theirs.
        mapping = xt2_backup.map_recipe(_recipe(white_balance="Auto", white_balance_red=5, white_balance_blue=5))
        result = xt2_backup.check_feasibility(_PRISTINE, 0, mapping)
        assert not result.ok
        assert result.conflicts

    def test_measured_custom_wb_is_not_pushable(self) -> None:
        mapping = xt2_backup.map_recipe(_recipe(white_balance="Custom 1"))
        assert not xt2_backup.check_feasibility(_PRISTINE, 0, mapping).ok

    def test_collection_two_recipes_same_wb_different_shift_conflicts(self) -> None:
        a = xt2_backup.map_recipe(_recipe(white_balance="Underwater", white_balance_red=3))
        b = xt2_backup.map_recipe(_recipe(white_balance="Underwater", white_balance_red=-3))
        result = xt2_backup.check_collection_feasibility(_PRISTINE, [(0, a), (1, b)])
        assert not result.ok


class TestVerifyRoundTrip:
    def test_identical_passes(self) -> None:
        assert xt2_backup.verify_round_trip(_PRISTINE, _PRISTINE).ok

    def test_drift_region_difference_is_ignored(self) -> None:
        from src.data.camera import constants_xt2 as xt2

        read_back = bytearray(_PRISTINE)
        read_back[xt2.DRIFT_RANGE[0]] ^= 0xFF  # a camera-managed drift byte
        assert xt2_backup.verify_round_trip(bytes(read_back), _PRISTINE).ok

    def test_slot_counter_difference_is_ignored(self) -> None:
        from src.data.camera import constants_xt2 as xt2

        read_back = bytearray(_PRISTINE)
        read_back[xt2.SLOT0_OFFSET + xt2.SLOT_WRITE_COUNTER_OFFSET] ^= 0xFF
        assert xt2_backup.verify_round_trip(bytes(read_back), _PRISTINE).ok

    def test_slot_recipe_byte_difference_fails(self) -> None:
        from src.data.camera import constants_xt2 as xt2

        read_back = bytearray(_PRISTINE)
        read_back[xt2.SLOT0_OFFSET + xt2.OFF_FILM_SIMULATION] ^= 0x01
        assert not xt2_backup.verify_round_trip(bytes(read_back), _PRISTINE).ok
