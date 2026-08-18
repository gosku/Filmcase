import json

import attrs

from src.data.camera import constants
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries

URL = "/camera/client-config.json"


class TestCameraClientConfig:
    def test_serves_the_settings_and_encodings(self, client):
        response = client.get(URL)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        payload = json.loads(response.content)
        assert set(payload) == {"settings", "encodings"}

    def test_settings_keys_are_the_django_setting_names_verbatim(self, client):
        # The browser runs a port of the same push sequence, so a reader
        # comparing the two should find the same names on both sides.
        payload = json.loads(client.get(URL).content)

        expected = {field.name for field in attrs.fields(camera_queries.ClientCameraSettings)}
        assert set(payload["settings"]) == expected
        assert "CAMERA_PRE_WRITE_DELAY_S" in payload["settings"]

    def test_settings_values_track_the_current_configuration(self, client, settings):
        settings.CAMERA_TRANSPORT = "browser"
        settings.CAMERA_MAX_RETRIES = 5
        settings.CAMERA_VERIFY_WRITES = True

        payload = json.loads(client.get(URL).content)

        assert payload["settings"]["CAMERA_TRANSPORT"] == "browser"
        assert payload["settings"]["CAMERA_MAX_RETRIES"] == 5
        assert payload["settings"]["CAMERA_VERIFY_WRITES"] is True

    def test_delays_are_served_in_seconds(self, client, settings):
        # Seconds, not milliseconds, so the value reads the same on both sides
        # and the conversion happens once, in the client's sleep helper.
        settings.CAMERA_PRE_WRITE_DELAY_S = 0.05

        payload = json.loads(client.get(URL).content)

        assert payload["settings"]["CAMERA_PRE_WRITE_DELAY_S"] == 0.05

    def test_encodings_carry_the_write_order(self, client):
        payload = json.loads(client.get(URL).content)

        assert payload["encodings"]["write_order"] == list(camera_queries.WRITE_ORDER)

    def test_encodings_carry_every_custom_slot_code(self, client):
        payload = json.loads(client.get(URL).content)

        assert payload["encodings"]["custom_slot_codes"] == constants.CUSTOM_SLOT_CODES

    def test_encodings_carry_the_vendor_id_for_the_device_picker(self, client):
        payload = json.loads(client.get(URL).content)

        assert payload["encodings"]["vendor_id"] == ptp_device.FUJIFILM_VENDOR_ID

    def test_encodings_nest_the_grain_table_rather_than_joining_its_keys(self, client):
        # The Python table is keyed by (roughness, size), which JSON cannot
        # express; nesting avoids inventing a join-key format for the client.
        payload = json.loads(client.get(URL).content)

        assert payload["encodings"]["grain_to_ptp"]["Weak"]["Small"] == 2

    def test_encodings_carry_the_grain_off_sentinel(self, client):
        payload = json.loads(client.get(URL).content)

        assert payload["encodings"]["grain_off_sentinel"] == camera_queries.GRAIN_OFF_SENTINEL

    def test_nr_table_keys_arrive_as_strings(self, client):
        # Documented deliberately: JSON object keys are always strings, so a
        # client indexing or inverting this table has to convert them back.
        payload = json.loads(client.get(URL).content)

        assert set(payload["encodings"]["nr_to_ptp"]) == {"-4", "-3", "-2", "-1", "0", "1", "2", "3", "4"}

    def test_is_not_cached(self, client):
        # Timing values are tuning an operator may change between requests, and
        # a stale copy would have the browser writing on delays the server has
        # stopped using.
        response = client.get(URL)

        assert response["Cache-Control"] == "no-store"

    def test_needs_no_camera_attached(self, client, settings):
        # The endpoint describes configuration, not hardware; it must answer on
        # a machine that has never seen a camera.
        settings.PTP_DEVICE = None

        assert client.get(URL).status_code == 200
