"""
Unit tests for camera capability profiles.
"""
from __future__ import annotations

from src.data.camera import constants
from src.domain.camera import profiles


class TestGetProfile:
    def test_known_model_resolves_to_per_property_profile(self) -> None:
        assert profiles.get_profile("X-S10") is profiles.PER_PROPERTY_PROFILE

    def test_unknown_model_falls_back_to_per_property_profile(self) -> None:
        # PR 1: every model, known or not, is assumed to use the per-property
        # interface, matching the pre-refactor behaviour.
        assert profiles.get_profile("NOT-A-CAMERA") is profiles.PER_PROPERTY_PROFILE


class TestPerPropertyProfile:
    def test_interface_is_per_property(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.interface is profiles.CameraInterface.PER_PROPERTY

    def test_film_simulations_match_write_side_constants(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.supported_film_simulations == frozenset(
            constants.FILM_SIMULATION_TO_PTP
        )

    def test_white_balance_modes_match_write_side_constants(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.supported_white_balance_modes == frozenset(
            constants.WHITE_BALANCE_TO_PTP
        )

    def test_dynamic_ranges_match_write_side_constants(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.supported_dynamic_ranges == frozenset(
            constants.DRANGE_MODE_TO_PTP
        )

    def test_nr_values_match_decode_table(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.supported_high_iso_nr_values == frozenset(
            constants.CUSTOM_SLOT_NR_DECODE.values()
        )

    def test_grain_roughnesses(self) -> None:
        assert profiles.PER_PROPERTY_PROFILE.supported_grain_roughnesses == frozenset(
            ("Off", "Weak", "Strong")
        )


class TestXt2Profile:
    def test_x_t2_resolves_to_the_backup_blob_profile(self) -> None:
        assert profiles.get_profile("X-T2") is profiles.XT2_PROFILE

    def test_interface_is_backup_blob(self) -> None:
        assert profiles.XT2_PROFILE.interface is profiles.CameraInterface.BACKUP_BLOB

    def test_film_simulations_are_the_fifteen_value_subset(self) -> None:
        from src.data.camera import constants_xt2

        assert profiles.XT2_PROFILE.supported_film_simulations == frozenset(
            constants_xt2.FILM_SIMULATION_BY_BYTE.values()
        )
        assert len(profiles.XT2_PROFILE.supported_film_simulations) == 15

    def test_lacks_color_chrome_and_dr_priority(self) -> None:
        assert profiles.XT2_PROFILE.supported_color_chrome_effects == frozenset(("Off",))
        assert profiles.XT2_PROFILE.supported_dr_priorities == frozenset(("Off",))

    def test_other_models_still_default_to_per_property(self) -> None:
        assert profiles.get_profile("X-T3") is profiles.PER_PROPERTY_PROFILE
