"""
Drift guards for the X-T2 backup constants.

The X-T2 value maps are keyed to the app's canonical domain names so the codec
can convert a blob byte straight to a FujifilmRecipeData field. These tests fail
if a name drifts out of the per-property tables it must agree with.
"""
from __future__ import annotations

from src.data.camera import constants
from src.data.camera import constants_xt2


class TestDomainNameConsistency:
    def test_film_simulations_are_known_domain_names(self) -> None:
        assert set(constants_xt2.FILM_SIMULATION_BY_BYTE.values()) <= set(
            constants.FILM_SIMULATION_TO_PTP
        )

    def test_white_balance_modes_are_known_domain_names(self) -> None:
        assert set(constants_xt2.WHITE_BALANCE_BY_SELECTOR.values()) <= set(
            constants.WHITE_BALANCE_TO_PTP
        )

    def test_dynamic_ranges_are_known_domain_names(self) -> None:
        assert set(constants_xt2.DYNAMIC_RANGE_BY_BYTE.values()) <= set(
            constants.DRANGE_MODE_TO_PTP
        )

    def test_wb_shift_table_covers_every_wb_entry(self) -> None:
        assert set(constants_xt2.WB_SHIFT_TABLE_INDEX) == set(
            constants_xt2.WHITE_BALANCE_BY_SELECTOR.values()
        )


class TestLayout:
    def test_fifteen_film_simulations(self) -> None:
        assert len(constants_xt2.FILM_SIMULATION_BY_BYTE) == 15

    def test_seven_slots(self) -> None:
        assert constants_xt2.SLOT_COUNT == 7

    def test_wb_shift_table_has_twelve_entries(self) -> None:
        assert constants_xt2.WB_SHIFT_ENTRIES == len(constants_xt2.WB_SHIFT_TABLE_INDEX)
