"""
Unit tests for the queries that describe the camera to a client.

The browser runs a port of the same push sequence, so these queries are the
contract between the two implementations: whatever they leave out, the client
cannot know.
"""

from __future__ import annotations

import attrs
import django.conf
import pytest

from src.data.camera import constants
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries
from src.domain.images import dataclasses as image_dataclasses


def _camera_setting_names() -> set[str]:
    return {name for name in dir(django.conf.settings) if name.startswith("CAMERA_")}


class TestClientCameraSettings:
    def test_covers_every_camera_setting(self) -> None:
        # The point of the query is that both transports run on one
        # configuration.  A new CAMERA_* setting that nobody shared with the
        # client would silently give the browser different timings from the
        # server, so adding one has to be a decision rather than an oversight.
        fields = {field.name for field in attrs.fields(camera_queries.ClientCameraSettings)}

        assert fields == _camera_setting_names()

    def test_reads_the_current_setting_values(self, settings) -> None:
        settings.CAMERA_TRANSPORT = "browser"
        settings.CAMERA_MAX_RETRIES = 7
        settings.CAMERA_RETRY_BACKOFF_S = 0.25

        result = camera_queries.client_camera_settings()

        assert result.CAMERA_TRANSPORT == "browser"
        assert result.CAMERA_MAX_RETRIES == 7
        assert result.CAMERA_RETRY_BACKOFF_S == 0.25

    def test_reads_settings_at_call_time_not_import_time(self, settings) -> None:
        settings.CAMERA_PRE_WRITE_DELAY_S = 0.1
        before = camera_queries.client_camera_settings()

        settings.CAMERA_PRE_WRITE_DELAY_S = 0.2
        after = camera_queries.client_camera_settings()

        assert before.CAMERA_PRE_WRITE_DELAY_S == 0.1
        assert after.CAMERA_PRE_WRITE_DELAY_S == 0.2

    def test_is_immutable(self) -> None:
        result = camera_queries.client_camera_settings()

        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            result.CAMERA_MAX_RETRIES = 99  # type: ignore[misc]


class TestClientCameraEncodings:
    def test_carries_every_custom_slot_code(self) -> None:
        result = camera_queries.client_camera_encodings()

        assert result.custom_slot_codes == constants.CUSTOM_SLOT_CODES

    def test_write_order_covers_every_recipe_property(self) -> None:
        # A property missing from write_order is never written at all, and the
        # symptom is a slot that silently keeps its old value for that one
        # setting.  RecipePTPValues is the list of what a recipe can set, so
        # the two have to agree exactly.
        fields = {field.name for field in attrs.fields(camera_queries.RecipePTPValues)}

        assert set(camera_queries.WRITE_ORDER) == fields

    def test_write_order_puts_colour_temperature_before_the_shifts(self) -> None:
        # Writing the shifts first makes the camera zero them when the colour
        # temperature lands.  See docs/investigation/wb_shift_reset_on_kelvin.md.
        order = camera_queries.WRITE_ORDER

        assert order.index("WhiteBalanceColorTemperature") < order.index("WhiteBalanceRed")
        assert order.index("WhiteBalanceColorTemperature") < order.index("WhiteBalanceBlue")

    def test_write_order_has_no_duplicates(self) -> None:
        assert len(camera_queries.WRITE_ORDER) == len(set(camera_queries.WRITE_ORDER))

    def test_every_write_order_name_has_a_ptp_code(self) -> None:
        missing = set(camera_queries.WRITE_ORDER) - set(constants.CUSTOM_SLOT_CODES)

        assert missing == set()

    def test_carries_the_value_tables(self) -> None:
        result = camera_queries.client_camera_encodings()

        assert result.film_simulation_to_ptp == constants.FILM_SIMULATION_TO_PTP
        assert result.white_balance_to_ptp == constants.WHITE_BALANCE_TO_PTP
        assert result.drange_mode_to_ptp == constants.DRANGE_MODE_TO_PTP
        assert result.camera_custom_slot_counts == constants.CAMERA_CUSTOM_SLOT_COUNTS

    def test_carries_the_inverted_tables_keyed_by_domain_value(self) -> None:
        result = camera_queries.client_camera_encodings()

        assert result.dr_priority_to_ptp["Off"] == 0
        assert result.cce_to_ptp["Off"] == 1
        assert result.cce_to_ptp["Strong"] == 3
        assert result.cfx_to_ptp["Weak"] == 2
        # Non-linear, so worth pinning both ends rather than trusting the shape.
        assert result.nr_to_ptp[0] == 0x2000
        assert result.nr_to_ptp[4] == 0x5000
        assert result.nr_to_ptp[-4] == 0x8000

    def test_flattens_the_tuple_keyed_grain_table_by_nesting(self) -> None:
        result = camera_queries.client_camera_encodings()

        assert result.grain_to_ptp["Weak"]["Small"] == 2
        assert result.grain_to_ptp["Strong"]["Small"] == 3
        assert result.grain_to_ptp["Weak"]["Large"] == 4
        assert result.grain_to_ptp["Strong"]["Large"] == 5

    def test_carries_the_grain_off_sentinel(self) -> None:
        # The nested table's ("Off", "Off") entry is the inverse of the read
        # table and would write a size the recipe never asked for.  A client
        # writing grain Off has to use the sentinel instead, so it is served
        # rather than left for the client to hardcode.
        result = camera_queries.client_camera_encodings()

        assert result.grain_off_sentinel == camera_queries.GRAIN_OFF_SENTINEL
        assert result.grain_off_sentinel != result.grain_to_ptp["Off"]["Off"]

    def test_nested_grain_table_covers_the_flat_one(self) -> None:
        result = camera_queries.client_camera_encodings()

        flattened = {
            (roughness, size): value
            for roughness, sizes in result.grain_to_ptp.items()
            for size, value in sizes.items()
        }

        assert flattened == camera_queries._GRAIN_TO_PTP

    def test_carries_the_property_codes_and_vendor_id(self) -> None:
        result = camera_queries.client_camera_encodings()

        assert result.vendor_id == ptp_device.FUJIFILM_VENDOR_ID
        assert result.prop_ping == constants.PROP_PING
        assert result.prop_slot_cursor == constants.PROP_SLOT_CURSOR
        assert result.prop_slot_name == constants.PROP_SLOT_NAME
        assert result.recipe_name_max_len == image_dataclasses.RECIPE_NAME_MAX_LEN
